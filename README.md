# SAEC — Sistema de Análisis de Enfermedades Crónicas

Software de escritorio (Python + Tkinter + ETL + PostgreSQL) para analizar EPOC, asma y diabetes en
pacientes de 18 a 59 años de la Subred Integrada de Servicios de Salud Norte de Bogotá (2020–2026),
y generar automáticamente un *diagnóstico situacional* con priorización y acciones sugeridas.

> El diagnóstico es *poblacional* (apoyo a la gestión en salud pública). No es un diagnóstico clínico
> de pacientes y no reemplaza el criterio de los profesionales de la salud.

## 1. Requisitos
- Python 3.10 a 3.13 (con Tkinter, incluido en el instalador oficial de Windows).
- PostgreSQL 13 o superior (probado con 16). PostGIS *no* es obligatorio.
- Windows 10/11, Linux o macOS.

## 2. Instalación rápida (Windows)
1. Instale PostgreSQL y anote la contraseña del usuario postgres.
2. Edite config/settings.ini → sección [database] (usuario y contraseña).
3. Doble clic en instalar.bat (crea el entorno, instala librerías, crea la base saec y el usuario administrador).
4. Doble clic en ejecutar.bat.

Usuario inicial: admin@saec.local / Admin2026 (cámbielo en *Usuarios*).

### Instalación manual (cualquier sistema)
bash
python -m venv .venv
.venv\Scripts\activate          # Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
python main.py instalar
python main.py                  # abre la aplicación


## 3. Probar sin descargar datos (demostración)
bash
python main.py demo

Genera datos *sintéticos* en datos_demo/, ejecuta el ETL y produce el diagnóstico en PDF y Excel
en reportes/. El diagnóstico avisa que se trata de datos de demostración.

## 4. Cargar los datos reales
En la aplicación: *Proceso ETL → Agregar archivos → Ejecutar ETL* (rol administrador), o por consola:
bash
python main.py etl ruta/estrato.csv ruta/ips.geojson ruta/morbilidad_rips_2023.csv

El tipo de archivo se detecta por sus columnas:

| Tipo | Origen | Columnas que se reconocen |
|---|---|---|
| RIPS agregado | Datos Abiertos Bogotá — Morbilidad atendida identificada en RIPS | ANO, Sexo_Gen, Edad_Quiquenio, tipo_usuario_afiliacion, prestador_localidad_codigo, prestador_localidad_nombre, tipo_atencion_nombre, dxPrincipal_agrupacion1_nombre, dxPrincipal_agrupacion2_nombre, administradora_consolidada, sum_atenciones |
| Registros individuales | Bases de la Subred / IPS | ver plantillas/plantilla_atenciones_individuales.csv |
| IPS | Datos Abiertos — Instituciones Prestadoras de Salud (CSV o GeoJSON) | nombre, código de habilitación, latitud/longitud (o geometría) |
| Estrato | Planeación — estrato por manzana o tabla localidad-estrato | localidad (o código), estrato |

Volver a cargar el mismo archivo *reemplaza* sus datos (no duplica). Si ocurre un error se hace
ROLLBACK y la base de datos no cambia. Los registros inválidos quedan en etl_rechazo.

*Importante sobre el RIPS público:* se publica agregado por quinquenio de edad y localidad del
prestador, sin estrato ni IPS. Con ese archivo SAEC analiza magnitud, edad, sexo y tendencia; el análisis
por estrato e IPS requiere registros individuales (plantilla).

## 5. Diagnóstico automático
Al iniciar sesión, la pantalla *Diagnóstico* se genera sola con la población objetivo. Incluye:
magnitud por enfermedad, perfil por edad, estrato y sexo (con prueba chi-cuadrado y V de Cramér),
tendencia anual (cambio % promedio, exclusión del año en curso), IPS con mayor carga, grupos prioritarios,
calidad de datos, *priorización* (puntaje = 45 % magnitud + 30 % tendencia + 25 % vulnerabilidad) y
acciones sugeridas. Se exporta a PDF o Excel. Por consola:
bash
python main.py diagnostico --pdf --excel


## 6. Parámetros de la población (config/settings.ini)
[poblacion] edad, años, estratos y localidades del área de estudio (por defecto CHAPINERO, que
corresponde a calles 45–100 / carreras 1–13). [area_estudio] polígono aproximado para marcar las IPS
dentro del área. Las plantillas de plantillas/ traen valores ilustrativos: reemplácelos.

## 7. Pruebas
bash
python -m pytest -q tests

Las pruebas de integración usan una base aparte (saec_test) y se omiten si no hay PostgreSQL.

## 8. Ejecutable
construir_exe.bat genera dist/SAEC/SAEC.exe con PyInstaller (copie también config/ y db/).

## 9. Estructura

main.py                 punto de entrada (interfaz y comandos)
config/settings.ini     conexión y parámetros
db/                     01_schema.sql, 02_vistas.sql, 03_semillas.sql
saec/etl/               extract.py, transform.py, load.py, pipeline.py, reglas.py, demo_data.py
saec/services/          diagnostico.py, estadistica.py, consultas.py, reportes.py, graficos.py, auth.py
saec/repositories.py    todas las consultas SQL
saec/ui/                app.py, widgets.py, tema.py, vistas/ (login, diagnóstico, consultas, estadísticas, mapa, etl, usuarios, config)
tests/                  pruebas unitarias e integración
