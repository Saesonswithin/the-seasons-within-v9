@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"
title The Seasons Within
set PYTHONUTF8=1
set "PY="
set "PYARGS="

REM Find any real installed Python. Prefer the Windows py launcher.
where py.exe >nul 2>nul
if not errorlevel 1 (
  for %%V in (3.15 3.14 3.13 3.12 3.11 3.10) do (
    if not defined PY (
      py -%%V -c "import sys; print(sys.executable)" >nul 2>nul
      if not errorlevel 1 (
        set "PY=py"
        set "PYARGS=-%%V"
      )
    )
  )
)

REM Search common per-user Python folders if py launcher was not found.
if not defined PY (
  for %%D in (Python315 Python314 Python313 Python312 Python311 Python310) do (
    if exist "%LOCALAPPDATA%\Programs\Python\%%D\python.exe" (
      if not defined PY set "PY=%LOCALAPPDATA%\Programs\Python\%%D\python.exe"
    )
  )
)

REM Finally try python.exe only if it is a real interpreter, not Store alias.
if not defined PY (
  where python.exe >nul 2>nul
  if not errorlevel 1 (
    python -c "import sys; print(sys.executable)" >nul 2>nul
    if not errorlevel 1 set "PY=python"
  )
)

if not defined PY goto :NOPYTHON

:FOUND
echo.
echo The Seasons Within is starting...
echo Using installed Python: %PY% %PYARGS%

REM Install only the packages required to START the platform.
if /I "%PY%"=="py" (
  %PY% %PYARGS% -m pip install --disable-pip-version-check --quiet Flask==3.0.3 "Werkzeug>=3.0,<4" "stripe>=12,<14" "geopy>=2.4,<3" "timezonefinder>=6,<9"
  if errorlevel 1 goto :INSTALLFAIL
  REM Swiss Ephemeris is optional at startup. It may not yet have a wheel for newest Python versions.
  %PY% %PYARGS% -m pip show pysweph >nul 2>nul
  if errorlevel 1 %PY% %PYARGS% -m pip install --disable-pip-version-check --quiet --only-binary=:all: "pysweph>=2.10.3.6" >nul 2>nul
  start "The Seasons Within Server" /min %PY% %PYARGS% "%~dp0app.py"
) else (
  "%PY%" -m pip install --disable-pip-version-check --quiet Flask==3.0.3 "Werkzeug>=3.0,<4" "stripe>=12,<14" "geopy>=2.4,<3" "timezonefinder>=6,<9"
  if errorlevel 1 goto :INSTALLFAIL
  "%PY%" -m pip show pysweph >nul 2>nul
  if errorlevel 1 "%PY%" -m pip install --disable-pip-version-check --quiet --only-binary=:all: "pysweph>=2.10.3.6" >nul 2>nul
  start "The Seasons Within Server" /min "%PY%" "%~dp0app.py"
)

REM Wait for the Flask app and then open it.
powershell -NoProfile -ExecutionPolicy Bypass -Command "$u='http://127.0.0.1:5055'; for($i=0;$i -lt 60;$i++){try{Invoke-WebRequest -UseBasicParsing -Uri $u -TimeoutSec 1 ^| Out-Null; exit 0}catch{Start-Sleep -Milliseconds 500}}; exit 1" >nul 2>nul
if errorlevel 1 goto :SERVERFAIL
start "" "http://127.0.0.1:5055"
exit /b 0

:INSTALLFAIL
echo.
echo The app packages could not be installed.
echo Make sure you are connected to the internet, then double-click this file again.
pause
exit /b 1

:SERVERFAIL
echo.
echo The app did not finish starting. Another copy may already be running.
echo Try opening http://127.0.0.1:5055 in your browser.
pause
exit /b 1

:NOPYTHON
echo.
echo Windows could not find a real Python installation.
echo Your files are okay. Install any current 64-bit Python for Windows, then double-click this file again.
start "" "https://www.python.org/downloads/windows/"
pause
exit /b 1
