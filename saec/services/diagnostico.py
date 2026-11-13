"""DIAGNÓSTICO SITUACIONAL AUTOMÁTICO.

Genera, con un solo clic (o al iniciar sesión), el diagnóstico de la población objetivo:
magnitud de cada enfermedad, perfil por edad, sexo y estrato, tendencia 2020-2026, instituciones con mayor
carga, pruebas estadísticas, priorización y acciones sugeridas.

Es un diagnóstico POBLACIONAL (de salud pública) para apoyar decisiones. NO es un diagnóstico clínico de
pacientes individuales y no reemplaza el criterio médico.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime

import numpy as np
import pandas as pd

from ..models import ENFERMEDADES, GRUPOS_EDAD, Filtro
from .estadistica import chi_cuadrado, clasificar_tendencia, fuerza_asociacion, tendencia

ACCIONES = {
    "DIABETES": [
        "Tamizaje de glucemia / HbA1c en adultos con factores de riesgo (sobrepeso, antecedentes familiares).",
        "Programas de alimentación saludable y actividad física en los grupos y estratos priorizados.",
        "Seguimiento de adherencia al tratamiento y control periódico de pacientes ya diagnosticados.",
    ],
    "EPOC": [
        "Espirometría en adultos mayores de 40 años con exposición a tabaco o humo.",
        "Programas de cesación de tabaquismo y reducción de exposición a contaminantes.",
        "Vacunación contra influenza y neumococo y acceso a rehabilitación pulmonar.",
    ],
    "ASMA": [
        "Educación en técnica de uso de inhaladores y planes de acción escritos.",
        "Identificación y control de desencadenantes ambientales (humedad, ácaros, contaminación).",
        "Seguimiento de pacientes con consultas repetidas por urgencias.",
    ],
}
NOMBRE = {"EPOC": "EPOC", "ASMA": "asma", "DIABETES": "diabetes"}


def cap(enf: str) -> str:
    n = NOMBRE[enf]
    return n if n.isupper() else n.capitalize()


def unir(items: list[str]) -> str:
    items = list(items)
    if len(items) <= 1:
        return "".join(items)
    return ", ".join(items[:-1]) + " y " + items[-1]


def fmt(n: float, dec: int = 0) -> str:
    """Número con separador de miles colombiano."""
    s = f"{n:,.{dec}f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


def pct(n: float, dec: int = 1) -> str:
    return fmt(n, dec) + " %"


@dataclass
class Seccion:
    titulo: str
    hallazgos: list[str] = field(default_factory=list)
    tabla: pd.DataFrame | None = None
    grafico: str | None = None  # clave del gráfico en services.graficos


@dataclass
class Diagnostico:
    generado: datetime
    filtro: str
    fuente: str
    total: int
    kpis: dict
    secciones: list[Seccion]
    prioridades: list[dict]
    conclusion: str
    advertencias: list[str]
    datos: pd.DataFrame
    series: dict = field(default_factory=dict)

    def resumen_texto(self) -> str:
        return self.conclusion

    def a_dict(self) -> dict:
        return {
            "generado": self.generado.isoformat(timespec="seconds"), "filtro": self.filtro, "fuente": self.fuente,
            "total": self.total, "kpis": self.kpis, "prioridades": self.prioridades,
            "conclusion": self.conclusion, "advertencias": self.advertencias,
            "secciones": [{"titulo": s.titulo, "hallazgos": s.hallazgos} for s in self.secciones],
        }

    def texto(self) -> str:
        """Versión en texto plano (consola / portapapeles)."""
        out = [f"DIAGNÓSTICO SITUACIONAL — {self.generado:%Y-%m-%d %H:%M}", self.filtro, f"Fuente: {self.fuente}", ""]
        for a in self.advertencias:
            out.append(f"⚠ {a}")
        out.append("")
        for s in self.secciones:
            out.append(s.titulo.upper())
            out += [f"  • {h}" for h in s.hallazgos]
            out.append("")
        out.append("PRIORIZACIÓN")
        for p in self.prioridades:
            out.append(f"  {p['orden']}. {p['enfermedad']} — prioridad {p['nivel']} (puntaje {p['puntaje']:.2f})")
            out += [f"     - {r}" for r in p["razones"]]
        out += ["", "CONCLUSIÓN", self.conclusion]
        return "\n".join(out)


# ---------------------------------------------------------------------------
def diagnosticar(df: pd.DataFrame, filtro: Filtro | None = None, contexto: dict | None = None,
                 hoy: date | None = None) -> Diagnostico:
    """Calcula el diagnóstico a partir de las filas de mv_casos_resumen (columna 'casos').

    contexto (opcional): personas_unicas, estrato_localidades, calidad, origenes.
    """
    filtro = filtro or Filtro()
    contexto = contexto or {}
    hoy = hoy or date.today()
    adv: list[str] = []
    secciones: list[Seccion] = []
    df = df.copy()
    if df.empty or df["casos"].sum() == 0:
        return Diagnostico(datetime.now(), filtro.descripcion(), "sin datos", 0, {}, [], [],
                           "No hay datos cargados para los filtros seleccionados. Ejecute el proceso ETL o "
                           "amplíe los filtros.", ["Sin datos para analizar."], df)
    df["casos"] = df["casos"].astype(int)
    total = int(df["casos"].sum())
    origenes = sorted(df["origen"].dropna().unique()) if "origen" in df else []
    fuente = {("INDIVIDUAL",): "Registros individuales de atención",
              ("AGREGADO",): "RIPS público agregado (Datos Abiertos Bogotá)"}.get(tuple(origenes),
                                                                               "Registros individuales + RIPS agregado")
    if contexto.get("demo"):
        adv.append("Los datos provienen de archivos de DEMOSTRACIÓN (sintéticos): los resultados sirven para probar "
                   "el software y no describen la población real. Cargue los datasets oficiales en Proceso ETL.")
    if len(origenes) > 1:
        adv.append("Se mezclan registros individuales y RIPS agregado: puede haber doble conteo. "
                   "Seleccione una sola fuente en el filtro para un análisis más preciso.")

    # ---------------- 1. Magnitud ----------------
    por_enf = df.groupby("enfermedad")["casos"].sum().reindex(ENFERMEDADES, fill_value=0)
    part = por_enf / total * 100
    orden = por_enf.sort_values(ascending=False)
    principal = orden.index[0]
    anios = sorted(int(a) for a in df["anio"].unique())
    kpis = {"total": total, "por_enfermedad": {k: int(v) for k, v in por_enf.items()},
            "participacion": {k: round(float(v), 1) for k, v in part.items()},
            "periodo": f"{anios[0]}–{anios[-1]}", "principal": principal}
    s1 = Seccion("1. Magnitud del problema", grafico="frecuencia")
    s1.hallazgos.append(f"Se analizaron {fmt(total)} atenciones de pacientes de {filtro.edad_min} a {filtro.edad_max} "
                        f"años entre {anios[0]} y {anios[-1]}.")
    s1.hallazgos.append(f"La enfermedad con mayor número de atenciones es {NOMBRE[principal]} con {fmt(orden.iloc[0])} "
                        f"({pct(part[principal])}), seguida de {NOMBRE[orden.index[1]]} ({pct(part[orden.index[1]])}) "
                        f"y {NOMBRE[orden.index[2]]} ({pct(part[orden.index[2]])}).")
    if contexto.get("personas_unicas"):
        pu = contexto["personas_unicas"]
        conc = total / pu if pu else 0
        kpis["personas"] = pu
        kpis["concentracion"] = round(conc, 2)
        s1.hallazgos.append(f"Las atenciones corresponden a {fmt(pu)} personas distintas: en promedio "
                            f"{fmt(conc, 1)} atenciones por persona en el periodo.")
    s1.tabla = pd.DataFrame({"Enfermedad": por_enf.index, "Atenciones": por_enf.values.astype(int),
                             "Participación (%)": part.round(1).values})
    secciones.append(s1)

    # ---------------- 2. Edad ----------------
    ct_edad = df.pivot_table(index="enfermedad", columns="grupo_edad", values="casos", aggfunc="sum",
                             fill_value=0).reindex(index=ENFERMEDADES, columns=GRUPOS_EDAD, fill_value=0)
    s2 = Seccion("2. Comportamiento por grupo de edad", grafico="edad")
    for enf in ENFERMEDADES:
        fila = ct_edad.loc[enf]
        if fila.sum() == 0:
            continue
        g = fila.idxmax()
        dist = fila / fila.sum() * 100
        corr = np.corrcoef(np.arange(len(fila)), fila.to_numpy(dtype=float))[0, 1] if fila.std() > 0 else 0
        patron = ("aumenta con la edad" if corr > 0.8 else "disminuye con la edad" if corr < -0.8
                  else "no sigue un patrón lineal con la edad")
        s2.hallazgos.append(f"{cap(enf)}: el grupo de {g} años concentra el {pct(dist[g])} de sus atenciones; "
                            f"la carga {patron}.")
    comp = ct_edad.div(ct_edad.sum(axis=0).replace(0, np.nan), axis=1) * 100
    for g in GRUPOS_EDAD:
        if ct_edad[g].sum():
            top = comp[g].idxmax()
            s2.hallazgos.append(f"Entre los {g} años predomina {NOMBRE[top]} ({pct(comp.loc[top, g])} de las atenciones del grupo).")
    chi = chi_cuadrado(ct_edad)
    if chi:
        s2.hallazgos.append(_texto_chi("la enfermedad", "el grupo de edad", chi))
    s2.tabla = ct_edad.reset_index().rename(columns={"enfermedad": "Enfermedad"})
    secciones.append(s2)

    # ---------------- 3. Estrato ----------------
    s3 = Seccion("3. Comportamiento por estrato socioeconómico", grafico="estrato")
    con_estrato = df[df["estrato"].notna()]
    cobertura = con_estrato["casos"].sum() / total * 100
    kpis["cobertura_estrato"] = round(float(cobertura), 1)
    if con_estrato.empty:
        s3.grafico = None
        s3.hallazgos.append("Los datos cargados no incluyen el estrato de los pacientes (el RIPS público se publica "
                            "agregado por localidad), por lo que no es posible comparar las enfermedades por estrato.")
        loc_est = contexto.get("estrato_localidades") or {}
        locs = sorted(df["localidad"].dropna().unique())
        info = [f"{l.title()}: estrato predominante {loc_est[l]}" for l in locs if l in loc_est]
        if info:
            s3.hallazgos.append("Contexto socioeconómico del área (estrato predominante de las manzanas): " + "; ".join(info) + ".")
        s3.hallazgos.append("Para este análisis cargue registros individuales con estrato (plantilla del manual).")
    else:
        if cobertura < 99:
            adv.append(f"Solo el {pct(cobertura)} de las atenciones tiene estrato; el análisis por estrato usa ese subconjunto.")
        con_estrato = con_estrato.assign(estrato=con_estrato["estrato"].astype(int))
        ct_est = con_estrato.pivot_table(index="enfermedad", columns="estrato", values="casos", aggfunc="sum",
                                         fill_value=0).reindex(index=ENFERMEDADES, fill_value=0)
        ct_est = ct_est.reindex(columns=sorted(ct_est.columns))
        dist_enf = ct_est.div(ct_est.sum(axis=1).replace(0, np.nan), axis=0) * 100   # % de cada enfermedad por estrato
        comp_est = ct_est.div(ct_est.sum(axis=0).replace(0, np.nan), axis=1) * 100  # composición dentro del estrato
        tot_est = ct_est.sum(axis=0)
        s3.hallazgos.append("Distribución de atenciones por estrato: " + ", ".join(
            f"estrato {e}: {fmt(tot_est[e])} ({pct(tot_est[e] / tot_est.sum() * 100)})" for e in tot_est.index) + ".")
        for enf in ENFERMEDADES:
            if ct_est.loc[enf].sum() == 0:
                continue
            e_max = dist_enf.loc[enf].idxmax()
            s3.hallazgos.append(f"{cap(enf)}: el estrato {e_max} concentra el {pct(dist_enf.loc[enf, e_max])} de sus atenciones.")
        if 1 in comp_est.columns and 3 in comp_est.columns:
            for enf in ENFERMEDADES:
                a, b = comp_est.loc[enf, 1], comp_est.loc[enf, 3]
                if b and b > 0 and abs(a / b - 1) >= 0.10:
                    rel = a / b
                    s3.hallazgos.append(f"El peso de {NOMBRE[enf]} dentro de las atenciones del estrato 1 es "
                                        f"{fmt(rel, 2)} veces el del estrato 3 ({pct(a)} frente a {pct(b)}).")
        chi = chi_cuadrado(ct_est)
        if chi:
            s3.hallazgos.append(_texto_chi("la enfermedad", "el estrato", chi))
        s3.hallazgos.append("Nota: son proporciones de atenciones, no tasas de prevalencia; para tasas se requiere la "
                            "población de cada estrato como denominador.")
        tabla = ct_est.copy()
        tabla.columns = [f"Estrato {c}" for c in tabla.columns]
        s3.tabla = tabla.reset_index().rename(columns={"enfermedad": "Enfermedad"})
    secciones.append(s3)

    # ---------------- 4. Sexo ----------------
    s4 = Seccion("4. Distribución por sexo")
    ct_sexo = df[df["sexo"].isin(["F", "M"])].pivot_table(index="enfermedad", columns="sexo", values="casos",
                                                        aggfunc="sum", fill_value=0).reindex(index=ENFERMEDADES, fill_value=0)
    for c in ("F", "M"):
        if c not in ct_sexo:
            ct_sexo[c] = 0
    for enf in ENFERMEDADES:
        t = ct_sexo.loc[enf].sum()
        if t:
            f_ = ct_sexo.loc[enf, "F"] / t * 100
            s4.hallazgos.append(f"{cap(enf)}: {pct(f_)} mujeres y {pct(100 - f_)} hombres.")
    chi = chi_cuadrado(ct_sexo[["F", "M"]])
    if chi:
        s4.hallazgos.append(_texto_chi("la enfermedad", "el sexo", chi))
    secciones.append(s4)

    # ---------------- 5. Tendencia ----------------
    s5 = Seccion("5. Tendencia 2020–2026", grafico="tendencia")
    serie = df.pivot_table(index="anio", columns="enfermedad", values="casos", aggfunc="sum",
                           fill_value=0).reindex(columns=ENFERMEDADES, fill_value=0).sort_index()
    serie_tend = serie.copy()
    ultimo = int(serie.index.max())
    if ultimo >= hoy.year and len(serie) > 1:
        serie_tend = serie_tend.drop(index=ultimo)
        adv.append(f"El año {ultimo} está en curso (datos incompletos): se excluye del cálculo de tendencia.")
    elif len(serie) > 2 and serie.loc[ultimo].sum() < 0.6 * serie.iloc[-2].sum():
        serie_tend = serie_tend.drop(index=ultimo)
        adv.append(f"El año {ultimo} tiene muchas menos atenciones que el anterior (posible corte incompleto): "
                   "se excluye del cálculo de tendencia.")
    efecto_pandemia = (2020 in serie_tend.index and 2021 in serie_tend.index
                       and serie_tend.loc[2020].sum() < 0.85 * serie_tend.loc[2021].sum())
    if efecto_pandemia:
        s5.hallazgos.append("En 2020 se registraron menos atenciones que en 2021, lo que es coherente con la menor "
                            "consulta durante la pandemia de COVID-19; conviene tenerlo en cuenta al leer la tendencia.")
    tend_info = {}
    for enf in ENFERMEDADES:
        t = tendencia(serie_tend[enf])
        if t:
            t["clase"] = clasificar_tendencia(t["cambio_anual_pct"])
            tend_info[enf] = t
            s5.hallazgos.append(f"{cap(enf)}: tendencia {t['clase']} ({'+' if t['cambio_anual_pct'] >= 0 else ''}"
                                f"{fmt(t['cambio_anual_pct'], 1)} % promedio anual entre {t['desde']} y {t['hasta']}; "
                                f"pasó de {fmt(t['valor_inicial'])} a {fmt(t['valor_final'])} atenciones).")
    # alertas de salto interanual
    for enf in ENFERMEDADES:
        sv = serie_tend[enf]
        for a in sv.index[1:]:
            if efecto_pandemia and a == 2021:
                continue  # rebote posterior a la pandemia, no es una alerta
            prev = sv.get(a - 1, 0)
            if prev >= 30 and sv[a] / prev - 1 >= 0.25:
                s5.hallazgos.append(f"Alerta: {NOMBRE[enf]} aumentó {pct((sv[a] / prev - 1) * 100, 0)} entre {a - 1} y {a}.")
    t5 = serie.reset_index().rename(columns={"anio": "Año"})
    s5.tabla = t5
    secciones.append(s5)

    # ---------------- 6. Instituciones ----------------
    s6 = Seccion("6. Instituciones con mayor carga")
    con_ips = df[df["institucion"].notna()]
    if con_ips.empty:
        s6.hallazgos.append("Los datos no identifican la institución (IPS) de cada atención.")
        if df["localidad"].nunique() > 1:
            pl = df.groupby("localidad")["casos"].sum().sort_values(ascending=False)
            s6.hallazgos.append("Atenciones por localidad: " + ", ".join(f"{l.title()} {fmt(v)}" for l, v in pl.items()) + ".")
    else:
        pi = con_ips.groupby("institucion")["casos"].sum().sort_values(ascending=False)
        tot_ips = pi.sum()
        top3 = pi.head(3)
        s6.hallazgos.append("Las tres IPS con más atenciones concentran el "
                            f"{pct(top3.sum() / tot_ips * 100)} del total: " +
                            "; ".join(f"{n.title()} ({fmt(v)})" for n, v in top3.items()) + ".")
        s6.tabla = pi.reset_index().rename(columns={"institucion": "IPS", "casos": "Atenciones"}).head(10)
    secciones.append(s6)

    # ---------------- 7. Grupos prioritarios ----------------
    s7 = Seccion("7. Grupos poblacionales prioritarios")
    claves = ["grupo_edad", "sexo"] + (["estrato"] if not con_estrato.empty else [])
    base = con_estrato if not con_estrato.empty else df
    for enf in ENFERMEDADES:
        sub = base[base["enfermedad"] == enf]
        if sub.empty:
            continue
        g = sub.groupby(claves)["casos"].sum().sort_values(ascending=False)
        k = g.index[0]
        etiqueta = f"{k[0]} años, {'mujeres' if k[1] == 'F' else 'hombres'}" + (f", estrato {int(k[2])}" if len(k) > 2 else "")
        s7.hallazgos.append(f"{cap(enf)}: el subgrupo con más atenciones es {etiqueta} "
                            f"({fmt(g.iloc[0])}, {pct(g.iloc[0] / sub['casos'].sum() * 100)} de la enfermedad).")
    secciones.append(s7)

    # ---------------- Priorización ----------------
    prioridades = []
    for enf in ENFERMEDADES:
        if por_enf[enf] == 0:
            continue
        magnitud = por_enf[enf] / por_enf.max()
        cambio = tend_info.get(enf, {}).get("cambio_anual_pct", 0.0)
        t_score = float(np.clip((cambio + 10) / 20, 0, 1))
        if not con_estrato.empty:
            sub = con_estrato[con_estrato["enfermedad"] == enf]
            vuln = sub[sub["estrato"].isin([1, 2])]["casos"].sum() / max(sub["casos"].sum(), 1)
            txt_v = f"{pct(vuln * 100)} de sus atenciones en estratos 1 y 2"
        else:
            fila = ct_edad.loc[enf]
            vuln = fila.get("50-59", 0) / max(fila.sum(), 1)
            txt_v = f"{pct(vuln * 100)} de sus atenciones en personas de 50 a 59 años"
        puntaje = 0.45 * magnitud + 0.30 * t_score + 0.25 * vuln
        nivel = "ALTA" if puntaje >= 0.60 else "MEDIA" if puntaje >= 0.40 else "BAJA"
        prioridades.append({
            "enfermedad": enf, "puntaje": round(float(puntaje), 3), "nivel": nivel,
            "razones": [f"{pct(part[enf])} de las atenciones analizadas",
                        f"tendencia {tend_info[enf]['clase']} ({'+' if cambio >= 0 else ''}{fmt(cambio, 1)} % anual)"
                        if enf in tend_info else "tendencia no calculable (menos de 3 años)",
                        txt_v],
            "acciones": ACCIONES[enf]})
    prioridades.sort(key=lambda p: p["puntaje"], reverse=True)
    for i, p in enumerate(prioridades, 1):
        p["orden"] = i

    # ---------------- Calidad de datos ----------------
    cal = contexto.get("calidad")
    if cal:
        s8 = Seccion("8. Calidad de los datos")
        for o, c in cal.items():
            s8.hallazgos.append(f"{'Registros individuales' if o == 'INDIVIDUAL' else 'RIPS agregado'}: "
                                f"{fmt(c['atenciones'])} atenciones cargadas; sin estrato: {pct(c['sin_estrato'] / max(c['atenciones'], 1) * 100)}; "
                                f"sin IPS: {pct(c['sin_ips'] / max(c['atenciones'], 1) * 100)}.")
        ult = contexto.get("ultima_etl")
        if ult:
            leidos = int(ult.get("registros_leidos") or 0)
            rech = int(ult.get("registros_rechazados") or 0)
            s8.hallazgos.append(f"Última carga ETL (#{ult['id_ejecucion']}, {ult['fuente']}): {fmt(leidos)} filas leídas, "
                                f"{fmt(rech)} rechazadas por validación ({pct(rech / max(leidos, 1) * 100)}).")
        secciones.append(s8)

    # ---------------- Conclusión ----------------
    top = prioridades[0]
    partes = [f"En la población analizada ({filtro.edad_min}–{filtro.edad_max} años, {kpis['periodo']}), "
              f"{NOMBRE[principal]} es la enfermedad crónica con mayor número de atenciones ({pct(part[principal])})."]
    crec = [NOMBRE[e] for e, t in tend_info.items() if t["clase"] == "en aumento"]
    if crec:
        partes.append(("Presentan" if len(crec) > 1 else "Presenta") + " tendencia en aumento: " + unir(crec) + ".")
    edades = {enf: ct_edad.loc[enf].idxmax() for enf in ENFERMEDADES if ct_edad.loc[enf].sum()}
    partes.append("Los grupos de edad con más atenciones son: " +
                  unir([f"{NOMBRE[e]}, {g} años" for e, g in edades.items()]) + ".")
    if not con_estrato.empty:
        e_tot = con_estrato.groupby("estrato")["casos"].sum()
        partes.append(f"El estrato {int(e_tot.idxmax())} concentra la mayor parte de las atenciones "
                      f"({pct(e_tot.max() / e_tot.sum() * 100)}).")
    partes.append(f"Se recomienda priorizar {NOMBRE[top['enfermedad']]} (prioridad {top['nivel'].lower()}) "
                  f"con acciones como: {top['acciones'][0][0].lower() + top['acciones'][0][1:]}")
    partes.append("Este es un diagnóstico poblacional de apoyo a la gestión; no constituye diagnóstico clínico.")
    return Diagnostico(datetime.now(), filtro.descripcion(), fuente, total, kpis, secciones, prioridades,
                       " ".join(partes), adv, df,
                       series={"anual": serie, "edad": ct_edad, "por_enf": por_enf,
                               "estrato": (ct_est if not con_estrato.empty else None),
                               "sexo": ct_sexo})


def _texto_chi(a: str, b: str, chi: dict) -> str:
    sig = chi["p"] < 0.05
    p_txt = "p < 0,001" if chi["p"] < 0.001 else f"p = {fmt(chi['p'], 3)}"
    base = (f"Prueba chi-cuadrado: {'existe' if sig else 'no se encontró'} asociación estadísticamente significativa "
            f"entre {a} y {b} (χ² = {fmt(chi['chi2'], 1)}, gl = {chi['gl']}, {p_txt}")
    if sig:
        base += f"; intensidad {fuerza_asociacion(chi['v_cramer'])}, V de Cramér = {fmt(chi['v_cramer'], 2)})."
        if chi["v_cramer"] < 0.10:
            base += " Con tantos registros, diferencias pequeñas resultan significativas: en la práctica la diferencia es menor."
    else:
        base += ")."
    return base


# ---------------------------------------------------------------------------
class DiagnosticoService:
    """Consulta la base de datos y produce el diagnóstico."""

    def __init__(self):
        from ..repositories import AtencionRepository, ETLRepository, LocalidadRepository, SalidaRepository
        self.atenciones = AtencionRepository()
        self.etl = ETLRepository()
        self.localidades = LocalidadRepository()
        self.salidas = SalidaRepository()

    def fuente_por_defecto(self) -> str | None:
        o = self.atenciones.origenes()
        if "INDIVIDUAL" in o:
            return "INDIVIDUAL"
        return "AGREGADO" if "AGREGADO" in o else None

    def generar(self, filtro: Filtro | None = None, id_usuario: int | None = None, guardar: bool = True) -> Diagnostico:
        filtro = filtro or Filtro(origen=self.fuente_por_defecto())
        filtro.validar()
        df = self.atenciones.resumen(filtro)
        ctx = {"estrato_localidades": self.localidades.estrato_predominante(),
               "demo": self.atenciones.usa_datos_demo(filtro.origen),
               "calidad": self.atenciones.calidad(), "ultima_etl": self.etl.ultima_exitosa()}
        if filtro.origen in (None, "INDIVIDUAL"):
            ctx["personas_unicas"] = self.atenciones.personas_unicas(filtro)
        dx = diagnosticar(df, filtro, ctx)
        if guardar and dx.total:
            self.salidas.registrar_diagnostico(id_usuario, filtro.como_dict(), dx.conclusion, dx.a_dict())
        return dx
