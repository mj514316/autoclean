# PyInstaller spec — build on Windows with: pyinstaller autoclean.spec
from PyInstaller.utils.hooks import collect_all

datas = [("model", "model"), ("words.txt", ".")]
binaries = []
hiddenimports = []

for pkg in ("sherpa_onnx", "sounddevice"):
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hiddenimports += h

a = Analysis(
    ["configurator.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="AutoClean",
    console=False,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="AutoClean",
)
