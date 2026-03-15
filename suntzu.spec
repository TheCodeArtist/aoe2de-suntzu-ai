# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for SunTzu-AoE2
# Build: pyinstaller suntzu.spec

a = Analysis(
    ["backend/__main__.py"],
    pathex=["."],
    binaries=[],
    datas=[
        ("frontend",                          "frontend"),
        ("assets",                            "assets"),
        ("references/sun-tzu-quotes.json",    "references"),
    ],
    hiddenimports=[
        "win32api",
        "win32con",
        "win32gui",
        "win32ui",
        "win32process",
        "pystray._win32",
        "PIL._tkinter_finder",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "pytest",
        "pytest_cov",
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="SunTzu-AoE2",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon="assets/sun-tzu-icon.ico",
    version="version_info.txt",
)
