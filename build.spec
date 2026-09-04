# PyInstaller spec -- build with:  pyinstaller build.spec --noconfirm
from PyInstaller.utils.hooks import collect_data_files

datas = [("config/platforms.json", "config"), ("assets/pawn.ico", "assets")]
datas += collect_data_files("tkinterdnd2")  # the tkdnd Tcl package + binaries

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=["tkinterdnd2", "python_calamine", "python_calamine._python_calamine"],
    hookspath=[],
    runtime_hooks=[],
    # PIL only draws the icon at build time; nothing imports it at runtime.
    excludes=["matplotlib", "scipy", "IPython", "pytest", "numpy.testing", "PIL"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="TournamentEntryMerger",
    icon="assets/pawn.ico",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
