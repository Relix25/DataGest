# DataGest PyInstaller spec (onedir mode)
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

hiddenimports = collect_submodules("PySide6")
SPEC_DIR = Path(SPECPATH)
ROOT_DIR = SPEC_DIR.parent
SRC_DIR = ROOT_DIR / "src"
ENTRYPOINT = ROOT_DIR / "src" / "main.py"

a = Analysis(
    [str(ENTRYPOINT)],
    pathex=[str(ROOT_DIR), str(SRC_DIR)],
    binaries=[],
    datas=[],
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="DataGest",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="DataGest",
)
