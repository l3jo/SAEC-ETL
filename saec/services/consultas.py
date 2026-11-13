"""Servicios de consulta y estadística (equivalen a los endpoints de la versión web)."""
from __future__ import annotations

import pandas as pd

from ..models import ENFERMEDADES, GRUPOS_EDAD, Filtro
from ..repositories import AtencionRepository, CatalogoRepository, IPSRepository


class ConsultaService:
    def __init__(self):
        self.atenciones = AtencionRepository()
        self.catalogo = CatalogoRepository()

    def listar_enfermedades(self) -> pd.DataFrame:
        return self.catalogo.enfermedades()

    def consultar_atenciones(self, f: Filtro, pagina: int = 1, limite: int = 50) -> tuple[pd.DataFrame, int]:
        f.validar()
        return self.atenciones.atenciones_paginadas(f, pagina, limite)


class EstadisticasService:
    def __init__(self):
        self.atenciones = AtencionRepository()

    def _res(self, f: Filtro) -> pd.DataFrame:
        f.validar()
        return self.atenciones.resumen(f)

    def frecuencia(self, f: Filtro) -> pd.DataFrame:
        df = self._res(f)
        s = df.groupby("enfermedad")["casos"].sum().reindex(ENFERMEDADES, fill_value=0) if not df.empty \
            else pd.Series(0, index=ENFERMEDADES)
        return pd.DataFrame({"enfermedad": s.index, "casos": s.values.astype(int)}).sort_values("casos", ascending=False)

    def por_grupo_edad(self, f: Filtro) -> pd.DataFrame:
        df = self._res(f)
        if df.empty:
            return pd.DataFrame(0, index=ENFERMEDADES, columns=GRUPOS_EDAD)
        return df.pivot_table(index="enfermedad", columns="grupo_edad", values="casos", aggfunc="sum",
                              fill_value=0).reindex(index=ENFERMEDADES, columns=GRUPOS_EDAD, fill_value=0)

    def por_estrato(self, f: Filtro) -> pd.DataFrame:
        """estrato, enfermedad, casos, porcentaje (dentro de la enfermedad)."""
        df = self._res(f)
        df = df[df["estrato"].notna()] if not df.empty else df
        if df.empty:
            return pd.DataFrame(columns=["estrato", "enfermedad", "casos", "porcentaje"])
        g = df.groupby(["estrato", "enfermedad"], as_index=False)["casos"].sum()
        g["porcentaje"] = (g["casos"] / g.groupby("enfermedad")["casos"].transform("sum") * 100).round(1)
        g["estrato"] = g["estrato"].astype(int)
        return g.sort_values(["enfermedad", "estrato"])

    def tendencia_anual(self, f: Filtro) -> pd.DataFrame:
        df = self._res(f)
        if df.empty:
            return pd.DataFrame(columns=ENFERMEDADES)
        return df.pivot_table(index="anio", columns="enfermedad", values="casos", aggfunc="sum",
                              fill_value=0).reindex(columns=ENFERMEDADES, fill_value=0).sort_index()


class IPSService:
    def __init__(self):
        self.repo = IPSRepository()

    def listar_ips(self, f: Filtro) -> pd.DataFrame:
        f.validar()
        return self.repo.listar(f)

    def detalle_ips(self, id_ips: int, f: Filtro) -> pd.DataFrame:
        return self.repo.detalle(id_ips, f)
