-- =====================================================================
--  SAEC - Datos iniciales (catálogos)
-- =====================================================================
INSERT INTO estrato (numero_estrato, descripcion) VALUES
    (1, 'Bajo-bajo'), (2, 'Bajo'), (3, 'Medio-bajo'),
    (4, 'Medio'), (5, 'Medio-alto'), (6, 'Alto')
ON CONFLICT (numero_estrato) DO NOTHING;

INSERT INTO subred (nombre, zona_cobertura) VALUES
    ('Subred Integrada de Servicios de Salud Norte',
     'Usaquén, Chapinero, Barrios Unidos, Teusaquillo, Suba y Engativá')
ON CONFLICT (nombre) DO NOTHING;

INSERT INTO localidad (codigo, nombre, id_subred)
SELECT v.codigo, v.nombre, s.id_subred
FROM (VALUES ('01', 'USAQUEN'), ('02', 'CHAPINERO'), ('10', 'ENGATIVA'),
             ('11', 'SUBA'), ('12', 'BARRIOS UNIDOS'), ('13', 'TEUSAQUILLO')) AS v(codigo, nombre)
CROSS JOIN subred s
WHERE s.nombre = 'Subred Integrada de Servicios de Salud Norte'
ON CONFLICT (codigo) DO NOTHING;

INSERT INTO enfermedad (nombre, codigo_cie10, categoria) VALUES
    ('EPOC', 'J44', 'Respiratoria'),
    ('ASMA', 'J45', 'Respiratoria'),
    ('DIABETES', 'E11', 'Metabólica')
ON CONFLICT (nombre) DO NOTHING;
