"""
Configuration Manager for PhotoFrame application.
Provides centralized configuration loading, validation, and management.

Format pliku (jedna plaska sekcja):

    photo_frame:
      com_port: COM3
      debug_enabled: true
      debug_level: info
      show_time: false
      show_temperature: false
      latitude: 52.2297
      longitude: 21.0122
      brightness: 85
      interval: 44
      orientation_portrait: true
      scale_mode: fit
      inverse: false
      shuffle: true
      default_landscape_folder: C:/.Source/Ramka/poziome
      default_portrait_folder: C:/.Source/Ramka/PionAI
      active_landscape_folder: C:/.Source/Ramka/poziome
      active_portrait_folder: C:/.Source/Ramka/PionAI

default_* to folder, na ktory wraca podwojne klikniecie w ikone zasobnika,
active_* to folder aktualnie wyswietlany. Starszy uklad (sekcje config/photos/
slideshow/display/debug z podwojonymi kluczami) jest automatycznie migrowany
przy pierwszym odczycie - patrz _migrate_legacy().
"""

import yaml
import os
import shutil
import tempfile
from lib.debug_utils import debug_print
from lib.filelock import file_lock
from lib.paths import (
    config_path as _default_config_path,
    portrait_history_path,
    landscape_history_path,
)

SECTION = 'photo_frame'

# Tryby skalowania zdjecia do ekranu (proporcje zachowane w obu):
#   fit  - cale zdjecie widoczne, wolne miejsce wypelniaja czarne pasy
#   fill - zdjecie pokrywa caly ekran, nadmiar jest przyciety, obraz wysrodkowany
SCALE_MODES = ('fit', 'fill')

# Kolejnosc kluczy w zapisywanym pliku
DEFAULTS = {
    'com_port': 'COM3',
    'debug_enabled': True,
    'debug_level': 'info',
    'show_time': False,
    # Temperatura z Open-Meteo dla podanych wspolrzednych; puste = nieustawione
    'show_temperature': False,
    'latitude': '',
    'longitude': '',
    'brightness': 85,
    'interval': 30,
    'orientation_portrait': True,
    'scale_mode': 'fit',
    'inverse': False,
    'shuffle': True,
    'default_landscape_folder': '',
    'default_portrait_folder': '',
    'active_landscape_folder': '',
    'active_portrait_folder': '',
}


def settings(config):
    """Zwroc ustawienia z sekcji photo_frame uzupelnione o wartosci domyslne.

    Dzieki temu kod czytajacy konfiguracje nigdy nie musi sprawdzac, czy klucz
    istnieje, ani znac starego ukladu pliku.
    """
    values = dict(DEFAULTS)
    if isinstance(config, dict):
        section = config.get(SECTION)
        if isinstance(section, dict):
            values.update({k: v for k, v in section.items() if v is not None})
    if values.get('scale_mode') not in SCALE_MODES:
        values['scale_mode'] = DEFAULTS['scale_mode']
    return values


def _ordered(config):
    """Uloz klucze sekcji photo_frame w stalej, czytelnej kolejnosci."""
    if not isinstance(config, dict) or SECTION not in config:
        return config
    section = config[SECTION]
    if not isinstance(section, dict):
        return config
    ordered = {k: section[k] for k in DEFAULTS if k in section}
    ordered.update({k: v for k, v in section.items() if k not in ordered})
    rest = {k: v for k, v in config.items() if k != SECTION}
    return {SECTION: ordered, **rest}


def _first_history_entry(path):
    """Pierwszy wpis z pliku historii folderow (uzywany jako folder domyslny)."""
    try:
        if path.exists():
            with path.open('r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line:
                        return line
    except OSError:
        pass
    return ''


def _migrate_legacy(old):
    """Przepisz stary uklad (config/photos/slideshow/display/debug) na photo_frame."""
    legacy = old.get('config', {}) if isinstance(old.get('config'), dict) else {}
    photos = old.get('photos', {}) if isinstance(old.get('photos'), dict) else {}
    slideshow = old.get('slideshow', {}) if isinstance(old.get('slideshow'), dict) else {}
    display = old.get('display', {}) if isinstance(old.get('display'), dict) else {}
    debug = old.get('debug', {}) if isinstance(old.get('debug'), dict) else {}

    orientation = photos.get('orientation') or legacy.get('PHOTO_FRAME_ORIENTATION') or 'portrait'

    active_portrait = photos.get('portrait_folder') or legacy.get('PHOTO_FRAME_FOLDER_PORTRAIT') or ''
    active_landscape = photos.get('landscape_folder') or legacy.get('PHOTO_FRAME_FOLDER_LANDSCAPE') or ''

    # Folder domyslny bral sie dotad z pierwszej linii pliku historii
    default_portrait = _first_history_entry(portrait_history_path()) or active_portrait
    default_landscape = _first_history_entry(landscape_history_path()) or active_landscape

    values = dict(DEFAULTS)
    values.update({
        'com_port': legacy.get('COM_PORT') or DEFAULTS['com_port'],
        'debug_enabled': bool(debug.get('enabled', DEFAULTS['debug_enabled'])),
        'debug_level': debug.get('level') or DEFAULTS['debug_level'],
        'show_time': bool(slideshow.get('show_time', DEFAULTS['show_time'])),
        'brightness': display.get('brightness', DEFAULTS['brightness']),
        'interval': slideshow.get('interval') or photos.get('slideshow_interval') or DEFAULTS['interval'],
        'orientation_portrait': str(orientation).lower().startswith('p'),
        # Stare PHOTO_FRAME_MAINTAIN_ASPECT_RATIO=false oznaczalo rozciaganie;
        # najblizszym odpowiednikiem bez znieksztalcen jest wypelnienie ekranu.
        'scale_mode': 'fit' if legacy.get('PHOTO_FRAME_MAINTAIN_ASPECT_RATIO', True) else 'fill',
        'inverse': bool(legacy.get('PHOTO_FRAME_INVERSE', DEFAULTS['inverse'])),
        'shuffle': bool(slideshow.get('shuffle', legacy.get('PHOTO_FRAME_RANDOM', DEFAULTS['shuffle']))),
        'default_landscape_folder': default_landscape,
        'default_portrait_folder': default_portrait,
        'active_landscape_folder': active_landscape,
        'active_portrait_folder': active_portrait,
    })
    return {SECTION: values}


class ConfigManager:
    """Centralized configuration management"""

    def __init__(self, config_path=None):
        self.config_path = str(config_path) if config_path else str(_default_config_path())
        self._config = None

    @property
    def backup_path(self):
        return f"{self.config_path}.backup"

    @property
    def lock_path(self):
        return f"{self.config_path}.lock"

    def _read_yaml(self, path):
        """Wczytaj plik YAML; zwraca None gdy pliku brak lub jest uszkodzony."""
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f)
            if isinstance(data, dict):
                return data
            if data is None:
                return {}
            debug_print(f"Config file has unexpected structure: {path}", 'error')
            return None
        except FileNotFoundError:
            return None
        except (yaml.YAMLError, PermissionError, OSError) as e:
            debug_print(f"Error loading config '{path}': {e}", 'error')
            return None

    def load_config(self, force_reload=False, silent=False):
        """Load configuration from file with caching

        Args:
            force_reload: Force reload from disk even if cached
            silent: Don't print debug messages (for periodic checks)
        """
        if self._config is None or force_reload:
            with file_lock(self.lock_path):
                data = self._read_yaml(self.config_path)

                if data is None:
                    # Uszkodzony lub brakujący plik - próbujemy ostatniej dobrej kopii,
                    # zamiast po cichu wracać do pustej konfiguracji (brak folderów
                    # ze zdjęciami = slideshow nie wystartuje).
                    data = self._read_yaml(self.backup_path)
                    if data is not None:
                        debug_print(
                            f"Config unreadable - restored from backup {self.backup_path}",
                            'error')
                        self._config = data
                        self._write_config_locked(data)
                        return self._config.copy()

                    debug_print("Config unreadable and no usable backup - using defaults", 'error')
                    self._config = self.get_default_config()
                    return self._config.copy()

                migrated = self._ensure_new_format(data)
                self._config = migrated if migrated is not None else data
                if not silent:
                    debug_print(f"Configuration loaded from {self.config_path}")

        return self._config.copy()  # Return a copy to prevent external modifications

    def _ensure_new_format(self, data):
        """Zmigruj stary uklad pliku na sekcje photo_frame i zapisz wynik.

        Zwraca zmigrowana konfiguracje albo None, gdy plik jest juz w nowym
        formacie. Wymaga trzymanej blokady pliku.
        """
        if not isinstance(data, dict) or SECTION in data:
            return None

        if not data:
            new_config = self.get_default_config()
        else:
            new_config = _migrate_legacy(data)
            debug_print("📋 Migracja konfiguracji do nowego formatu (photo_frame)")

        try:
            self._write_config_locked(new_config)
        except OSError as e:
            debug_print(f"Nie udalo sie zapisac zmigrowanej konfiguracji: {e}", 'error')
        return new_config

    def _write_config_locked(self, config):
        """Atomowy zapis configu. Wymaga trzymanej blokady pliku."""
        directory = os.path.dirname(self.config_path) or '.'
        os.makedirs(directory, exist_ok=True)

        # Kopia zapasowa przez copy (nie rename) - config.yaml nigdy nie znika,
        # więc równolegle czytający proces zawsze widzi kompletny plik.
        if os.path.exists(self.config_path):
            try:
                shutil.copy2(self.config_path, self.backup_path)
            except OSError as e:
                debug_print(f"Could not refresh config backup: {e}", 'error')

        tmp_fd, tmp_path = tempfile.mkstemp(dir=directory, prefix='.config-', suffix='.tmp')
        try:
            with os.fdopen(tmp_fd, 'w', encoding='utf-8') as f:
                # sort_keys=False + uporzadkowana sekcja => plik czytelny dla czlowieka
                yaml.safe_dump(_ordered(config), f, default_flow_style=False,
                               indent=2, sort_keys=False, allow_unicode=True)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_path, self.config_path)  # atomowa podmiana
        except BaseException:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise

    def save_config(self, config):
        """Save configuration to file (atomically, under a cross-process lock)"""
        if not isinstance(config, dict) or not config:
            debug_print("Refusing to save empty configuration", 'error')
            return False

        try:
            with file_lock(self.lock_path):
                self._write_config_locked(config)
                self._config = config.copy()
            debug_print(f"Configuration saved to {self.config_path}")
            return True

        except (PermissionError, OSError) as e:
            debug_print(f"Error saving config: {e}", 'error')
            return False
        except Exception as e:
            debug_print(f"Unexpected error saving config: {e}", 'error')
            return False

    def get_default_config(self):
        """Get default configuration values"""
        return {SECTION: dict(DEFAULTS)}

    def validate_config(self, config):
        """Validate configuration structure and values"""
        errors = []

        if SECTION not in config:
            errors.append(f"Missing required section: {SECTION}")
            return errors

        cfg = config[SECTION]

        try:
            if int(cfg.get('interval', DEFAULTS['interval'])) < 1:
                errors.append("interval must be at least 1 second")
        except (ValueError, TypeError):
            errors.append("interval must be a valid number")

        try:
            brightness = int(cfg.get('brightness', DEFAULTS['brightness']))
            if not 0 <= brightness <= 100:
                errors.append("brightness must be between 0 and 100")
        except (ValueError, TypeError):
            errors.append("brightness must be a valid number")

        if cfg.get('scale_mode', DEFAULTS['scale_mode']) not in SCALE_MODES:
            errors.append(f"scale_mode must be one of: {sorted(SCALE_MODES)}")

        for key in ('active_portrait_folder', 'active_landscape_folder',
                    'default_portrait_folder', 'default_landscape_folder'):
            folder = cfg.get(key)
            if folder and not os.path.isdir(str(folder)):
                errors.append(f"Folder does not exist ({key}): {folder}")

        return errors

    def is_valid_config_file(self, file_path=None):
        """Check if config file exists and is valid YAML"""
        path_to_check = file_path or self.config_path
        try:
            if not os.path.exists(path_to_check):
                return False
            
            with open(path_to_check, 'r', encoding='utf-8') as f:
                yaml.safe_load(f)
            return True
            
        except (yaml.YAMLError, PermissionError):
            return False
        except Exception:
            return False


# Global configuration manager instance
config_manager = ConfigManager()


def get_config():
    """Convenience function to get current configuration"""
    return config_manager.load_config()


def save_config(config):
    """Convenience function to save configuration"""
    return config_manager.save_config(config)


def get_config_value(section, key, default=None):
    """Convenience function to get specific config value"""
    return config_manager.get_value(section, key, default)


def set_config_value(section, key, value):
    """Convenience function to set specific config value"""
    return config_manager.set_value(section, key, value)