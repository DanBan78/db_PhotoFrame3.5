"""
Configuration Manager for PhotoFrame application.
Provides centralized configuration loading, validation, and management.
"""

import yaml
import os
from lib.debug_utils import debug_print


class ConfigManager:
    """Centralized configuration management"""
    
    def __init__(self, config_path='tools/config.yaml'):
        self.config_path = config_path
        self._config = None
    
    def load_config(self, force_reload=False):
        """Load configuration from file with caching"""
        if self._config is None or force_reload:
            try:
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    self._config = yaml.safe_load(f) or {}
                debug_print(f"Configuration loaded from {self.config_path}")
            except (FileNotFoundError, yaml.YAMLError, PermissionError) as e:
                debug_print(f"Error loading config: {e}", 'error')
                self._config = self.get_default_config()
            except Exception as e:
                debug_print(f"Unexpected error loading config: {e}", 'error')
                self._config = self.get_default_config()
        
        return self._config.copy()  # Return a copy to prevent external modifications
    
    def save_config(self, config):
        """Save configuration to file"""
        try:
            # Backup current config
            if os.path.exists(self.config_path):
                backup_path = f"{self.config_path}.backup"
                # Remove old backup if exists
                if os.path.exists(backup_path):
                    os.remove(backup_path)
                os.rename(self.config_path, backup_path)
            
            with open(self.config_path, 'w', encoding='utf-8') as f:
                yaml.safe_dump(config, f, default_flow_style=False, indent=2)
            
            # Update cached config
            self._config = config.copy()
            debug_print(f"Configuration saved to {self.config_path}")
            return True
            
        except (PermissionError, OSError) as e:
            debug_print(f"Error saving config: {e}", 'error')
            # Restore backup if it exists
            backup_path = f"{self.config_path}.backup"
            if os.path.exists(backup_path):
                try:
                    os.rename(backup_path, self.config_path)
                except Exception:
                    pass
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