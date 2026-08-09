# -*- mode: python ; coding: utf-8 -*-
"""Konfiguracja buildu PyInstaller dla PhotoFrame.

Budowanie:
    .venv\\Scripts\\pyinstaller.exe PhotoFrame.spec --noconfirm

Uklad wyniku (dist/PhotoFrame):
    PhotoFrame.exe
    _internal/...      <- kod, biblioteki i zasoby res/ (tylko do odczytu)
    tools/config.yaml  <- konfiguracja uzytkownika, zapisywalna, obok EXE

Zasoby res/ trafiaja do paczki (_internal) i sa czytane przez
lib.paths.resource_path(). Konfiguracja i historia folderow NIE moga byc
w paczce, bo _internal jest odtwarzany przy kazdym uruchomieniu - lezy
obok EXE i jest adresowana przez lib.paths.app_dir().
"""

block_cipher = None

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('res', 'res'),
    ],
    hiddenimports=[
        # edytor konfiguracji uruchamiany przez PhotoFrame.exe --config
        'lib.config_editor',
        'tkinter',
        'tkinter.ttk',
        'tkinter.filedialog',
        'tkinter.messagebox',
        # backend zasobnika systemowego wybierany dynamicznie
        'pystray._win32',
        # port szeregowy wyswietlacza
        'serial',
        'serial.tools',
        'serial.tools.list_ports',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='PhotoFrame',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,          # aplikacja zasobnika - bez okna konsoli
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='res/icons/photoframe-photos/icon.ico',
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='PhotoFrame',
)
