"""
Shared debug utilities for PhotoFrame application
"""
import logging
import yaml
from pathlib import Path

from .log import logger as _file_logger
from .paths import config_path as _config_path

class DebugConfig:
    DEBUG_ENABLED = True
    DEBUG_LEVEL = 'info'
    _config_loaded = False
    
    @classmethod
    def load_config(cls, config_path=None):
        """Load debug settings from config file"""
        if cls._config_loaded:
            return
            
        try:
            if config_path is None:
                config_path = _config_path()
            else:
                config_path = Path(config_path)


            if config_path.exists():
                with config_path.open("r", encoding="utf-8") as f:
                    config = yaml.safe_load(f) or {}
                # Czytamy plik bezposrednio (jestesmy importowani przed
                # ConfigManagerem), wiec obslugujemy tez uklad sprzed migracji.
                section = config.get('photo_frame')
                if isinstance(section, dict):
                    cls.DEBUG_ENABLED = section.get('debug_enabled', True)
                    cls.DEBUG_LEVEL = section.get('debug_level', 'info')
                else:
                    legacy = config.get('debug', {})
                    cls.DEBUG_ENABLED = legacy.get('enabled', True)
                    cls.DEBUG_LEVEL = legacy.get('level', 'info')
        except Exception:
            pass  # Use defaults if config loading fails
        finally:
            cls._config_loaded = True
    
    @classmethod
    def debug_print(cls, message, level='info'):
        """Print debug message if debug is enabled and level matches"""
        if not cls._config_loaded:
            cls.load_config()
            
        if not cls.DEBUG_ENABLED:
            return
            
        if level == 'error' or cls.DEBUG_LEVEL in ['info', 'debug']:
            cls._emit(message, level)

    @staticmethod
    def _emit(message, level='info'):
        """Zapisz komunikat do log.log (i na konsole, jesli jakas jest).

        W buildzie --noconsole sys.stdout nie istnieje, wiec dotychczasowe
        print() przepadalo bez sladu - kazdy blad aplikacji byl niewidoczny.
        Logowanie do pliku jest tez odporne na konsole cp1250, ktora nie
        potrafi zakodowac emoji z komunikatow (print rzucal UnicodeEncodeError
        prosto z callbacku zasobnika).
        """
        try:
            _file_logger.log(logging.ERROR if level == 'error' else logging.INFO, message)
        except Exception:
            pass

# Convenience function for direct use
def debug_print(message, level='info'):
    """Convenience function for debug printing"""
    DebugConfig.debug_print(message, level)

# Initialize configuration on import
DebugConfig.load_config()