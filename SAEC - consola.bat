@echo off
chcp 65001 >nul
cd /d "%~dp0"
set "PYTHONUTF8=1"
set "PATH=%~dp0runtime\python;%~dp0runtime\pgsql\bin;%PATH%"
echo Consola de SAEC portable. Ejemplos:
echo   python main.py demo
echo   python main.py diagnostico --pdf
echo   python main.py etl C:\ruta\archivo.csv
cmd /k
