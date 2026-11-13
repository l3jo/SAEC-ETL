-- =====================================================================
--  SAEC - Esquema de base de datos (PostgreSQL 13+)
--  Modelo en estrella: dimensiones + tabla de hechos "atencion"
-- =====================================================================
CREATE SCHEMA IF NOT EXISTS staging;

-- ---------- Dimensiones ----------
CREATE TABLE IF NOT EXISTS estrato (
    id_estrato      SERIAL PRIMARY KEY,
    numero_estrato  SMALLINT NOT NULL UNIQUE CHECK (numero_estrato BETWEEN 1 AND 6),
    descripcion     VARCHAR(120)
);

CREATE TABLE IF NOT EXISTS subred (
    id_subred       SERIAL PRIMARY KEY,
    nombre          VARCHAR(150) NOT NULL UNIQUE,
    zona_cobertura  VARCHAR(250)
);

CREATE TABLE IF NOT EXISTS localidad (
    id_localidad    SERIAL PRIMARY KEY,
    codigo          VARCHAR(4) NOT NULL UNIQUE,
    nombre          VARCHAR(100) NOT NULL,
    id_subred       INT REFERENCES subred(id_subred),
    id_estrato_predominante INT REFERENCES estrato(id_estrato),
    en_area_estudio BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS institucion (
    id_institucion      SERIAL PRIMARY KEY,
    codigo_habilitacion VARCHAR(20) UNIQUE,
    nombre              VARCHAR(200) NOT NULL,
    direccion           VARCHAR(200),
    latitud             NUMERIC(9,6),
    longitud            NUMERIC(9,6),
    id_localidad        INT REFERENCES localidad(id_localidad),
    en_area_estudio     BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS enfermedad (
    id_enfermedad   SERIAL PRIMARY KEY,
    nombre          VARCHAR(100) NOT NULL UNIQUE,
    codigo_cie10    VARCHAR(10) NOT NULL UNIQUE,
    categoria       VARCHAR(50)
);

CREATE TABLE IF NOT EXISTS usuario (
    id_usuario      SERIAL PRIMARY KEY,
    nombre          VARCHAR(120) NOT NULL,
    correo          VARCHAR(150) NOT NULL UNIQUE,
    contrasena_hash VARCHAR(255) NOT NULL,
    rol             VARCHAR(20) NOT NULL CHECK (rol IN ('ANALISTA', 'ADMINISTRADOR')),
    fecha_creacion  TIMESTAMP NOT NULL DEFAULT now(),
    activo          BOOLEAN NOT NULL DEFAULT TRUE
);

-- ---------- Control del ETL ----------
CREATE TABLE IF NOT EXISTS etl_ejecucion (
    id_ejecucion          SERIAL PRIMARY KEY,
    fuente                VARCHAR(250) NOT NULL,
    tipo_archivo          VARCHAR(20),
    archivo_hash          CHAR(40),
    fecha_inicio          TIMESTAMP NOT NULL DEFAULT now(),
    fecha_fin             TIMESTAMP,
    registros_leidos      INT DEFAULT 0,
    registros_cargados    INT DEFAULT 0,
    registros_rechazados  INT DEFAULT 0,
    estado                VARCHAR(15) NOT NULL DEFAULT 'EN_PROCESO'
                          CHECK (estado IN ('EN_PROCESO', 'EXITOSO', 'FALLIDO')),
    mensaje               TEXT,
    id_usuario            INT REFERENCES usuario(id_usuario)
);

CREATE TABLE IF NOT EXISTS etl_rechazo (
    id_rechazo        BIGSERIAL PRIMARY KEY,
    id_ejecucion      INT NOT NULL REFERENCES etl_ejecucion(id_ejecucion) ON DELETE CASCADE,
    motivo            VARCHAR(200) NOT NULL,
    registro_original JSONB
);

-- ---------- Hechos ----------
-- Cada fila representa una o varias atenciones con las mismas características.
--   * RIPS público (agregado): cantidad = sum_atenciones, edad = NULL, grupo por quinquenio
--   * Registros individuales:  cantidad = 1, edad exacta, paciente seudonimizado
CREATE TABLE IF NOT EXISTS atencion (
    id_atencion     BIGSERIAL PRIMARY KEY,
    anio            SMALLINT NOT NULL CHECK (anio BETWEEN 2000 AND 2100),
    mes             SMALLINT CHECK (mes BETWEEN 1 AND 12),
    sexo            CHAR(1) CHECK (sexo IN ('F', 'M', 'I')),
    edad            SMALLINT,
    grupo_edad      VARCHAR(7) NOT NULL,
    id_estrato      INT REFERENCES estrato(id_estrato),
    id_localidad    INT REFERENCES localidad(id_localidad),
    id_institucion  INT REFERENCES institucion(id_institucion),
    id_enfermedad   INT NOT NULL REFERENCES enfermedad(id_enfermedad),
    tipo_atencion   VARCHAR(60),
    regimen         VARCHAR(60),
    paciente_hash   CHAR(64),
    cantidad        INT NOT NULL DEFAULT 1 CHECK (cantidad > 0),
    origen          VARCHAR(12) NOT NULL DEFAULT 'INDIVIDUAL' CHECK (origen IN ('INDIVIDUAL', 'AGREGADO')),
    id_ejecucion    INT NOT NULL REFERENCES etl_ejecucion(id_ejecucion) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS ix_atencion_anio        ON atencion(anio);
CREATE INDEX IF NOT EXISTS ix_atencion_enfermedad  ON atencion(id_enfermedad);
CREATE INDEX IF NOT EXISTS ix_atencion_estrato     ON atencion(id_estrato);
CREATE INDEX IF NOT EXISTS ix_atencion_localidad   ON atencion(id_localidad);
CREATE INDEX IF NOT EXISTS ix_atencion_institucion ON atencion(id_institucion);

-- ---------- Salidas ----------
CREATE TABLE IF NOT EXISTS reporte (
    id_reporte       SERIAL PRIMARY KEY,
    id_usuario       INT REFERENCES usuario(id_usuario),
    fecha_generacion TIMESTAMP NOT NULL DEFAULT now(),
    tipo             VARCHAR(50),
    formato          VARCHAR(5),
    filtros          JSONB,
    ruta_archivo     VARCHAR(400)
);

CREATE TABLE IF NOT EXISTS diagnostico (
    id_diagnostico   SERIAL PRIMARY KEY,
    id_usuario       INT REFERENCES usuario(id_usuario),
    fecha_generacion TIMESTAMP NOT NULL DEFAULT now(),
    filtros          JSONB,
    resumen          TEXT,
    resultado        JSONB
);
