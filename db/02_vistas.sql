-- =====================================================================
--  SAEC - Vistas de análisis
-- =====================================================================
DROP MATERIALIZED VIEW IF EXISTS mv_casos_resumen;
DROP VIEW IF EXISTS v_casos;

-- Vista detallada: hechos con sus dimensiones ya resueltas
CREATE VIEW v_casos AS
SELECT a.id_atencion,
       a.anio,
       a.mes,
       a.sexo,
       a.edad,
       a.grupo_edad,
       es.numero_estrato        AS estrato,
       l.nombre                 AS localidad,
       a.id_institucion,
       i.nombre                 AS institucion,
       e.nombre                 AS enfermedad,
       e.codigo_cie10,
       a.tipo_atencion,
       a.regimen,
       a.cantidad,
       a.origen,
       a.paciente_hash
FROM atencion a
JOIN enfermedad e       ON e.id_enfermedad = a.id_enfermedad
LEFT JOIN estrato es    ON es.id_estrato = a.id_estrato
LEFT JOIN localidad l   ON l.id_localidad = a.id_localidad
LEFT JOIN institucion i ON i.id_institucion = a.id_institucion;

-- Resumen agregado que alimenta gráficos y diagnóstico (se refresca al final del ETL)
CREATE MATERIALIZED VIEW mv_casos_resumen AS
SELECT anio,
       enfermedad,
       grupo_edad,
       COALESCE(sexo, 'I')            AS sexo,
       estrato,
       localidad,
       id_institucion,
       institucion,
       origen,
       SUM(cantidad)::BIGINT          AS casos
FROM v_casos
GROUP BY anio, enfermedad, grupo_edad, COALESCE(sexo, 'I'), estrato, localidad, id_institucion, institucion, origen;

CREATE INDEX ix_mv_resumen_anio ON mv_casos_resumen(anio);
CREATE INDEX ix_mv_resumen_enf  ON mv_casos_resumen(enfermedad);
