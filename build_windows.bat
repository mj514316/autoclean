@echo off
REM Build AutoClean for Windows. Run on the Windows PC.
REM Prereqs: Python 3.11+ (python.org, "Add to PATH"), git clone of this repo.
setlocal
cd /d "%~dp0"

if not exist model\tokens.txt (
    echo Downloading ASR model...
    curl -L -o model.tar.bz2 "https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/sherpa-onnx-streaming-zipformer-en-20M-2023-02-17.tar.bz2"
    mkdir model
    tar -xjf model.tar.bz2 --strip-components=1 -C model
    del model.tar.bz2
)

py -m venv .venv || python -m venv .venv
call .venv\Scripts\activate.bat
pip install -r requirements.txt
pyinstaller --noconfirm autoclean.spec

echo.
echo Done. App is at dist\AutoClean\AutoClean.exe
echo Next: install VB-CABLE from https://vb-audio.com/Cable/
echo then set Windows output device to "CABLE Input".
endlocal
