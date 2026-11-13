@echo off
cd /d "%~dp0"
"%~dp0runtime\pgsql\bin\pg_ctl.exe" stop -D "%~dp0datos_pg" -m fast
pause
