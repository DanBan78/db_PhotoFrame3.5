"""
Shared debug utilities for PhotoFrame application
"""
import yaml
from pathlib import Path

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
                # Try to find config.yaml from different locations
                current_file = Path(__file__)
                config_path = current_file.parent.parent / "tools" / "config.yaml"
                
            if config_path.exists():
                with config_path.open("r", encoding="utf-8") as f:
                    config = yaml.safe_load(f) or {}
                    debug_config = config.get('debug', {})
                    cls.DEBUG_ENABLED = debug_config.get('enabled', True)
                    cls.DEBUG_LEVEL = debug_config.get('level', 'info')
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
            print(message)

# Convenience function for direct use
def debug_print(message, level='info'):
    """Convenience function for debug printing"""
    DebugConfig.debug_print(message, level)

# Initialize configuration on import
DebugConfig.load_config()