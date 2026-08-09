"""Centralne rozwiązywanie ścieżek dla PhotoFrame.

Aplikacja działa w dwóch trybach:
  * ze źródeł  - katalogiem bazowym jest katalog repozytorium,
  * jako EXE   - katalogiem bazowym jest katalog obok PhotoFrame.exe,
                 natomiast zasoby dołączone do paczki (res/) leżą w sys._MEIPASS.

Nigdy nie polegamy na katalogu roboczym procesu (CWD): przy starcie ze skrótu,
autostartu lub Harmonogramu zadań CWD bywa zupełnie inny niż katalog aplikacji.
"""

import sys
from pathlib import Path


def is_frozen() -> bool:
    """True gdy kod działa wewnątrz paczki PyInstaller."""
    return bool(getattr(sys, 'frozen', False))


def app_dir() -> Path:
    """Katalog danych aplikacji (config, historia, log) - zapisywalny."""
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def resource_dir() -> Path:
    """Katalog zasobów tylko do odczytu (res/) dołączonych do paczki."""
    if is_frozen():
        meipass = getattr(sys, '_MEIPASS', None)
        if meipass:
            return Path(meipass)
    return app_dir()


def resource_path(*parts) -> Path:
    """Ścieżka do zasobu dołączonego do paczki, np. resource_path('res', 'icons')."""
    return resource_dir().joinpath(*parts)


def tools_dir() -> Path:
    """Katalog z konfiguracją i historią folderów."""
    return app_dir() / 'tools'


def config_path() -> Path:
    return tools_dir() / 'config.yaml'


def portrait_history_path() -> Path:
    return tools_dir() / 'portrait_folders_history.txt'


def landscape_history_path() -> Path:
    return tools_dir() / 'landscape_folders_history.txt'


def log_path() -> Path:
    return app_dir() / 'log.log'


def ensure_tools_dir() -> Path:
    """Utwórz katalog tools/ jeśli nie istnieje i zwróć go."""
    directory = tools_dir()
    try:
        directory.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    return directory
