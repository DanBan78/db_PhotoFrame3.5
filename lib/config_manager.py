"""
Configuration Manager for PhotoFrame application.
Provides centralized configuration loading, validation, and management.
"""

import yaml
import os
import shutil
import tempfile
from lib.debug_utils import debug_print
from lib.filelock import file_lock
from lib.paths import config_path as _default_config_path


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

                self._config = data
                if not silent:
                    debug_print(f"Configuration loaded from {self.config_path}")

        return self._config.copy()  # Return a copy to prevent external modifications

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
                yaml.safe_dump(config, f, default_flow_style=False, indent=2)
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
        return {
            'slideshow': {
                'interval': 30,
                'show_time': True,
                'show_date': False,
                'shuffle': True
            },
            'photos': {
                'portrait_folder': '',
                'landscape_folder': '',
                'orientation': 'Portrait'
            },
            'display': {
                'brightness': 80,
                'timeout': 0
            },
            'config': {
                'PHOTO_FRAME_ORIENTATION': 'Portrait',
                'PHOTO_FRAME_INVERSE': False,
                'COM_PORT': 'COM3'
            },
            'debug': {
                'enabled': True,
                'level': 'info'
            }
        }
    
    def get_section(self, section_name, default=None):
        """Get specific configuration section"""
        config = self.load_config()
        return config.get(section_name, default or {})
    
    def get_value(self, section, key, default=None):
        """Get specific configuration value"""
        section_config = self.get_section(section)
        return section_config.get(key, default)
    
    def set_value(self, section, key, value):
        """Set specific configuration value"""
        config = self.load_config()
        if section not in config:
            config[section] = {}
        config[section][key] = value
        return self.save_config(config)
    
    def update_section(self, section_name, updates):
        """Update an entire configuration section"""
        config = self.load_config()
        if section_name not in config:
            config[section_name] = {}
        config[section_name].update(updates)
        return self.save_config(config)
    
    def validate_config(self, config):
        """Validate configuration structure and values"""
        errors = []
        
        # Check required sections
        required_sections = ['slideshow', 'photos', 'display', 'config', 'debug']
        for section in required_sections:
            if section not in config:
                errors.append(f"Missing required section: {section}")
        
        # Validate slideshow settings
        if 'slideshow' in config:
            slideshow = config['slideshow']
            if 'interval' in slideshow:
                try:
                    interval = int(slideshow['interval'])
                    if interval < 1:
                        errors.append("Slideshow interval must be at least 1 second")
                except (ValueError, TypeError):
                    errors.append("Slideshow interval must be a valid number")
        
        # Validate photo folders exist
        if 'photos' in config:
            photos = config['photos']
            for folder_key in ['portrait_folder', 'landscape_folder']:
                folder_path = photos.get(folder_key)
                if folder_path and not os.path.exists(folder_path):
                    errors.append(f"Photo folder does not exist: {folder_path}")
        
        # Validate orientation
        valid_orientations = ['Portrait', 'Landscape']
        if 'photos' in config and 'orientation' in config['photos']:
            if config['photos']['orientation'] not in valid_orientations:
                errors.append(f"Invalid orientation. Must be one of: {valid_orientations}")
        
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