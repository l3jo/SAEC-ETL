"""CARGA: inserción masiva con COPY dentro de una transacción."""
from __future__ import annotations

import io
import json

import pandas as pd

from ..db import Database
from .reglas import codigo_localidad, norm_col


def _copy(cur, df: pd.DataFrame, tabla: str, columnas: list[str], columnas_sql: list[str] | None = None) -> None:
    """COPY ... FROM STDIN en formato CSV (mucho más rápido que INSERT fila a fila)."""
    if df.empty:
        return
    buf = io.StringIO()
    df[columnas].to_csv(buf, index=False, header=False, na_rep="\\N")
    buf.seek(0)
    cur.copy_expert(f"COPY {tabla} ({', '.join(columnas_sql or columnas)}) FROM STDIN WITH (FORMAT csv, NULL '\\N')", buf)


class Loader:
    """Mantiene una conexión y una transacción abiertas durante la carga de un archivo."""

    def __init__(self, db: Database | None = None):
        self.db = db or Database.get()
        self.raw = None
        self.cur = None
        self._ids: dict[str, dict] = {}
        self._staging_creada: set[str] = set()

    # -- transacción --
    def __enter__(self):
        self.raw = self.db.engine.raw_connection()
        self.cur = self.raw.cursor()
        self._cargar_catalogos()
        return self

    def __exit__(self, exc_type, exc, tb):
        try:
            if exc_type is None:
                self.raw.commit()
            else:
                self.raw.rollback()
        finally:
            self.cur.close()
            self.raw.close()
        return False

    def _cargar_catalogos(self) -> None:
        q = {
            "enfermedad": "SELECT nombre, id_enfermedad FROM enfermedad",
            "estrato": "SELECT numero_estrato, id_estrato FROM estrato",
            "localidad": "SELECT nombre, id_localidad FROM localidad",
            "ips": "SELECT codigo_habilitacion, id_institucion FROM institucion WHERE codigo_habilitacion IS NOT NULL",
        }
        for k, sql in q.items():
            self.cur.execute(sql)
            self._ids[k] = {str(a): b for a, b in self.cur.fetchall()}

    def _id_localidad(self, nombre: str | None):
        if not nombre:
            return None
        if nombre not in self._ids["localidad"]:
            cod = codigo_localidad(nombre) or ("X" + str(len(self._ids["localidad"]) + 1).zfill(3))
            self.cur.execute("""INSERT INTO localidad (codigo, nombre) VALUES (%s, %s)
                                ON CONFLICT (codigo) DO UPDATE SET nombre = EXCLUDED.nombre
                                RETURNING id_localidad""", (cod, nombre))
            self._ids["localidad"][nombre] = self.cur.fetchone()[0]
        return self._ids["localidad"][nombre]

    # -- operaciones --
    def borrar_ejecuciones(self, ids: list[int]) -> int:
        if not ids:
            return 0
        self.cur.execute("DELETE FROM atencion WHERE id_ejecucion = ANY(%s)", (ids,))
        return self.cur.rowcount

    def staging(self, df: pd.DataFrame, tipo: str) -> None:
        """Guarda el bloque crudo en el esquema staging (tabla por tipo de archivo)."""
        tabla = f"staging.{tipo.lower()}"
        crudo = df.copy()
        crudo.columns = [norm_col(c)[:60] or f"col{i}" for i, c in enumerate(crudo.columns)]
        crudo = crudo.loc[:, ~crudo.columns.duplicated()]
        if tabla not in self._staging_creada:
            cols = ", ".join(f'"{c}" TEXT' for c in crudo.columns)
            self.cur.execute(f"DROP TABLE IF EXISTS {tabla}")
            self.cur.execute(f"CREATE TABLE {tabla} ({cols})")
            self._staging_creada.add(tabla)
        _copy(self.cur, crudo, tabla, list(crudo.columns), [f'"{c}"' for c in crudo.columns])

    def atenciones(self, df: pd.DataFrame, id_ejecucion: int) -> int:
        if df.empty:
            return 0
        d = pd.DataFrame()
        d["anio"] = df["anio"]
        d["mes"] = df["mes"].astype("Int64")
        d["sexo"] = df["sexo"]
        d["edad"] = df["edad"].astype("Int64")
        d["grupo_edad"] = df["grupo_edad"]
        d["id_estrato"] = df["estrato"].map(lambda e: self._ids["estrato"].get(str(int(e))) if pd.notna(e) else None).astype("Int64")
        d["id_localidad"] = df["localidad"].map(self._id_localidad).astype("Int64")
        d["id_institucion"] = df["ips_codigo"].map(lambda c: self._ids["ips"].get(str(c)) if c else None).astype("Int64")
        d["id_enfermedad"] = df["enfermedad"].map(self._ids["enfermedad"]).astype("Int64")
        d["tipo_atencion"] = df["tipo_atencion"]
        d["regimen"] = df["regimen"]
        d["paciente_hash"] = df["paciente_hash"]
        d["cantidad"] = df["cantidad"].astype(int)
        d["origen"] = df["origen"]
        d["id_ejecucion"] = id_ejecucion
        _copy(self.cur, d, "atencion", list(d.columns))
        return len(d)

    def rechazos(self, rech: pd.DataFrame, id_ejecucion: int, limite_restante: int) -> None:
        """Guarda los rechazos (con un tope para no inflar la base con archivos muy sucios)."""
        if rech.empty or limite_restante <= 0:
            return
        r = rech.head(limite_restante).copy()
        def limpio(reg: dict) -> str:
            return json.dumps({k: (None if v is None or (isinstance(v, float) and v != v) or v is pd.NA else v)
                               for k, v in reg.items()}, ensure_ascii=False, default=str)
        r["registro_original"] = r["registro"].map(limpio)
        r["id_ejecucion"] = id_ejecucion
        _copy(self.cur, r, "etl_rechazo", ["id_ejecucion", "motivo", "registro_original"])

    def instituciones(self, filas: list[dict]) -> int:
        for f in filas:
            id_loc = self._id_localidad(f.get("localidad"))
            self.cur.execute("""
                INSERT INTO institucion (codigo_habilitacion, nombre, direccion, latitud, longitud,
                                         id_localidad, en_area_estudio)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (codigo_habilitacion) DO UPDATE SET nombre = EXCLUDED.nombre,
                    direccion = EXCLUDED.direccion, latitud = EXCLUDED.latitud, longitud = EXCLUDED.longitud,
                    id_localidad = EXCLUDED.id_localidad, en_area_estudio = EXCLUDED.en_area_estudio""",
                (f["codigo"], f["nombre"], f["direccion"], f["latitud"], f["longitud"], id_loc, f["en_area"]))
        self._cargar_catalogos()
        return len(filas)

    def estratos_localidad(self, mapa: dict[str, int]) -> int:
        n = 0
        for loc, est in mapa.items():
            id_loc = self._id_localidad(loc)
            self.cur.execute("""UPDATE localidad SET id_estrato_predominante =
                                (SELECT id_estrato FROM estrato WHERE numero_estrato = %s)
                                WHERE id_localidad = %s""", (int(est), id_loc))
            n += self.cur.rowcount
        return n
