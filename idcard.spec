# -*- mode: python ; coding: utf-8 -*-
import os
import sys

block_cipher = None

# Base directory
BASE_DIR = os.path.abspath(SPECPATH)

# Data files to bundle inside executable
datas = [
    (os.path.join(BASE_DIR, 'sample_data'), 'sample_data'),
    (os.path.join(BASE_DIR, 'assets'), 'assets'),
]

# Hidden imports needed for dynamic loading
hiddenimports = [
    'PyQt6',
    'PyQt6.QtCore',
    'PyQt6.QtGui',
    'PyQt6.QtWidgets',
    'PIL',
    'PIL.Image',
    'PIL.ImageDraw',
    'PIL.ImageFont',
    'PIL.ImageOps',
    'PIL.PngImagePlugin',
    'PIL.JpegImagePlugin',
    'PIL.PdfImagePlugin',
    'requests',
    'urllib3',
    'yaml',
    'reportlab',
    'models',
    'generator_engine',
    'canvas_editor',
]

icon_file = os.path.join(BASE_DIR, 'assets', 'app_icon.ico')
if not os.path.exists(icon_file):
    icon_file = os.path.join(BASE_DIR, 'assets', 'app_icon.png')

a = Analysis(
    ['main.py'],
    pathex=[BASE_DIR],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter', 'matplotlib', 'scipy', 'numpy', 'pytest'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='IDCardStudio',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # Set to False so black terminal window does not appear on Windows
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=icon_file,
)
