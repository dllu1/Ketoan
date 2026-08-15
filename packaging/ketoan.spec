# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the Hung Phat Accounting Suite desktop app.

Build with ``packaging/build.ps1`` (preferred) or::

    pyinstaller packaging/ketoan.spec --noconfirm

Produces a one-folder distribution in ``dist/HungPhatAccounting/``. One-folder
(not one-file) is deliberate: PySide6 is ~200 MB, and a one-file build would
re-extract all of it to a temp directory on every launch.
"""
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

PROJECT_ROOT = Path(SPECPATH).resolve().parent

# Every resource the app reads at runtime through ``Path(__file__).parent`` —
# the relative layout below must mirror the source tree exactly, because
# app/config.py and data/database.py rebuild these paths from the frozen
# package location.
datas = [
    (str(PROJECT_ROOT / "ui" / "resources" / "qss"), "ui/resources/qss"),
    (str(PROJECT_ROOT / "ui" / "resources" / "fonts"), "ui/resources/fonts"),
    (str(PROJECT_ROOT / "data" / "migrations"), "data/migrations"),
    (str(PROJECT_ROOT / "data" / "account_sets"), "data/account_sets"),
    # reportlab resolves its Type-1 fonts and .rl_settings from package data at
    # runtime; PyInstaller's hooks only cover its modules, not these ~1.6 MB of
    # files, and PDF export would fail on the user's machine without them.
    *collect_data_files("reportlab"),
]

# Repos/services are reached via plain imports, but the report exporters pull
# openpyxl/reportlab lazily and Google OAuth is imported inside a function.
hiddenimports = [
    "openpyxl",
    "reportlab.pdfbase._fontdata",
    *collect_submodules("google.oauth2"),
    *collect_submodules("google_auth_oauthlib"),
]

# Qt ships far more than this app touches (only QtCore/QtGui/QtWidgets are
# imported). Dropping the heavyweights keeps the distribution small.
excludes = [
    "PySide6.Qt3DAnimation", "PySide6.Qt3DCore", "PySide6.Qt3DExtras",
    "PySide6.Qt3DInput", "PySide6.Qt3DLogic", "PySide6.Qt3DRender",
    "PySide6.QtBluetooth", "PySide6.QtCharts", "PySide6.QtDataVisualization",
    "PySide6.QtDesigner", "PySide6.QtHelp", "PySide6.QtMultimedia",
    "PySide6.QtMultimediaWidgets", "PySide6.QtNfc", "PySide6.QtOpenGL",
    "PySide6.QtOpenGLWidgets", "PySide6.QtPdf", "PySide6.QtPdfWidgets",
    "PySide6.QtPositioning", "PySide6.QtQml", "PySide6.QtQuick",
    "PySide6.QtQuick3D", "PySide6.QtQuickControls2", "PySide6.QtQuickWidgets",
    "PySide6.QtRemoteObjects", "PySide6.QtScxml", "PySide6.QtSensors",
    "PySide6.QtSerialPort", "PySide6.QtSpatialAudio", "PySide6.QtSql",
    "PySide6.QtStateMachine", "PySide6.QtTest", "PySide6.QtTextToSpeech",
    "PySide6.QtWebChannel", "PySide6.QtWebEngineCore",
    "PySide6.QtWebEngineQuick", "PySide6.QtWebEngineWidgets",
    "PySide6.QtWebSockets",
    # Toolchains that are dev-only or would be dragged in transitively.
    "PyQt5", "PyQt6", "tkinter", "pytest", "pytestqt",
    "matplotlib", "numpy", "pandas", "IPython", "flask", "werkzeug",
]

a = Analysis(
    [str(PROJECT_ROOT / "main.py")],
    # PROJECT_ROOT first: site-packages also contains unrelated PyPI packages
    # literally named `domain` and `data`, which would otherwise shadow ours.
    pathex=[str(PROJECT_ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
    optimize=0,
)

# Qt's hook collects these unconditionally, but nothing in the source tree can
# reach them: there is no QTranslator/QLocale call (the UI ships hardcoded
# Vietnamese), no QML/Quick, and no on-screen keyboard. Qt6Pdf/qpdf only let
# QImage decode PDFs — the app writes PDFs with reportlab instead. Together
# they are ~18 MB of dead weight.
#
# `opengl32sw.dll` is deliberately NOT pruned: it is Qt's software OpenGL
# fallback, and dropping it breaks rendering on machines with no usable GPU
# driver (remote desktop, thin clients).
_DEAD_BINARIES = (
    "qt6qml", "qt6quick", "qt6virtualkeyboard", "qtvirtualkeyboardplugin",
    "qt6pdf", "imageformats/qpdf",
)


def _dest(entry) -> str:
    """Normalised destination path of a TOC entry, for substring matching."""
    return entry[0].lower().replace("\\", "/")


a.binaries = [
    e for e in a.binaries if not any(d in _dest(e) for d in _DEAD_BINARIES)
]
a.datas = [e for e in a.datas if "/translations/" not in _dest(e)]

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="HungPhatAccounting",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,  # GUI app: no console window behind the main window.
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(PROJECT_ROOT / "packaging" / "HungPhat.ico"),
    version=str(PROJECT_ROOT / "packaging" / "version_info.txt"),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="HungPhatAccounting",
)
