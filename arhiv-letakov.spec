# PyInstaller (na Windows): pyinstaller --clean --noconfirm arhiv-letakov.spec
# Mapa namesto enega .exe: ta se razpakira v %TEMP%, kar AppLocker/WDAC blokira.

block_cipher = None

a = Analysis(
    ["letaki.py"],
    pathex=["."],
    binaries=[],
    datas=[("nastavitve.primer.yaml", ".")],
    hiddenimports=[
        "lxml._elementpath",
        "truststore",
        "PIL.Image",
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "pytest", "playwright"],
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="arhiv-letakov",
    debug=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    name="arhiv-letakov",
)
