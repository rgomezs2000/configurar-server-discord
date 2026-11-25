@echo off
rem Inicia Discord Server Studio sin consola (si pythonw está disponible).
setlocal
cd /d "%~dp0"

where pythonw >nul 2>nul
if %errorlevel%==0 (
    start "" pythonw main.py %*
    goto :eof
)

where python >nul 2>nul
if %errorlevel%==0 (
    start "" python main.py %*
    goto :eof
)

echo No se encontro Python en el PATH.
echo Instala Python 3.10 o superior desde https://www.python.org/downloads/
pause
