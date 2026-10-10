@echo off
REM Build AutoClean for Windows. Run on the Windows PC.
REM Needs nothing installed: if no Python 3.11+ is found, the script
REM downloads and installs Python 3.12.15 itself (per-user, no admin).
REM Old Pythons (e.g. 3.6) are never reused - sherpa-onnx only ships
REM prebuilt wheels for 3.11+, so older versions can never work.
setlocal
cd /d "%~dp0"

set PY=
for %%V in (-3.15 -3.14 -3.13 -3.12 -3.11) do (
    for /f "tokens=*" %%P in ('py %%V -c "import sys; print(sys.executable)" 2^>nul') do (
        set "PY=%%P"
        goto :pyready
    )
)
for /f "tokens=*" %%P in ('python -c "import sys; v=sys.version_info; exit(1) if (v[0]*100+v[1]) < 311 else print(sys.executable)" 2^>nul') do (
    set "PY=%%P"
    goto :pyready
)

REM --- no usable Python: install 3.12.15 per-user (no admin needed) ---
echo No Python 3.11+ found - installing Python 3.12.15 for this user...
set PYSETUP=%TEMP%\python-3.12.15-amd64.exe
curl -L -o "%PYSETUP%" "https://www.python.org/ftp/python/3.12.15/python-3.12.15-amd64.exe"
if errorlevel 1 (
    echo ERROR: could not download the Python installer. Check your connection.
    exit /b 1
)
if not exist "%PYSETUP%" (
    echo ERROR: Python installer download failed.
    exit /b 1
)
"%PYSETUP%" /quiet InstallAllUsers=0 PrependPath=1 Include_launcher=1 Include_test=0
if errorlevel 1 (
    echo ERROR: the Python installer failed.
    exit /b 1
)
del "%PYSETUP%"
set "PY=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
if not exist "%PY%" (
    echo ERROR: Python installed but python.exe was not found where expected.
    exit /b 1
)

:pyready
for /f "tokens=*" %%i in ('"%PY%" -c "import sys; print(sys.version.split()[0])"') do set PYVER=%%i
echo Using Python %PYVER% at "%PY%"

REM --- recreate the venv if it is not Python 3.11+ ---
if exist .venv\Scripts\python.exe (
    .venv\Scripts\python.exe -c "import sys; exit(0 if sys.version_info >= (3,11) else 1)" >nul 2>&1
    if errorlevel 1 (
        echo Existing .venv is Python ^< 3.11 - deleting it and recreating...
        rmdir /s /q .venv
    )
)
if not exist .venv\Scripts\python.exe (
    echo Creating .venv...
    "%PY%" -m venv .venv
    if errorlevel 1 (
        echo ERROR: venv creation failed.
        exit /b 1
    )
)
set VENV=%CD%\.venv
call "%VENV%\Scripts\activate.bat"

"%VENV%\Scripts\python.exe" -m pip install -U pip
if errorlevel 1 (
    echo ERROR: pip upgrade failed.
    exit /b 1
)
"%VENV%\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 (
    echo ERROR: pip install failed - see the errors above.
    exit /b 1
)
"%VENV%\Scripts\python.exe" -m PyInstaller --noconfirm autoclean.spec
if errorlevel 1 (
    echo ERROR: PyInstaller build failed - see the errors above.
    exit /b 1
)

if not exist dist\AutoClean\AutoClean.exe (
    echo ERROR: build finished but dist\AutoClean\AutoClean.exe is missing.
    exit /b 1
)
echo.
echo Done. App is at dist\AutoClean\AutoClean.exe
echo Next: install VB-CABLE from https://vb-audio.com/Cable/
echo then set Windows output device to "CABLE Input".
endlocal
