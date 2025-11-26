"""
Simple Photo Frame Slideshow
Clean implementation for displaying photos
"""

import os
import time
import random
import threading
from pathlib import Path
import yaml

# Debug configuration
DEBUG_ENABLED = True

def load_debug_config():
    """Load debug settings from config file"""
    global DEBUG_ENABLED
    try:
        config_path = Path(__file__).parent.parent / "tools" / "config.yaml"
        if config_path.exists():
            with config_path.open("r", encoding="utf-8") as f:
                config = yaml.safe_load(f) or {}
                debug_config = config.get('debug', {})
                DEBUG_ENABLED = debug_config.get('enabled', True)
    except Exception:
        pass

def debug_print(message, level='info'):
    """Print debug message if debug is enabled"""
    if DEBUG_ENABLED and level in ['info', 'debug', 'error']:
        print(message)

load_debug_config()

class PhotoFrame:
    def __init__(self, config_path="tools/config.yaml"):
        # Load initial configuration from disk
        self.config_path = config_path
        self.config = self.load_config(config_path)
        # Ensure photos section exists
        if 'photos' not in self.config:
            self.config['photos'] = {}
        self.display = None
        self.running = False
        self.current_images = []
        self.current_index = 0
        self.slideshow_thread = None
        
    def load_config(self, config_path):
        """Load configuration from YAML file"""
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f)
        except Exception as e:
            debug_print(f"Error loading config: {e}", 'error')
            return self.get_default_config()
    
    def get_default_config(self):
        """Default configuration"""
        return {
            'display': {'serial_port': 'COM3', 'brightness': 85},
            'photos': {
                'portrait_folder': 'C:/.Source/Ramka/pionowe',
                'landscape_folder': 'C:/.Source/Ramka/poziome',
                'slideshow_interval': 10,
                'orientation': 'landscape'
            },
            'overlay': {'show_time': True, 'show_date': True}
        }
    
    def set_display(self, display):
        """Set display controller"""
        self.display = display
        # Only update the display's in-memory config reference here.
        # The running slideshow will read and apply the latest config before
        # showing the next image, so we avoid forcing immediate apply here.
        try:
            if self.display is not None:
                try:
                    setattr(self.display, 'config', self.config)
                except Exception:
                    # best-effort: ignore if display doesn't accept attribute
                    pass
        except Exception as e:
            debug_print(f"Error setting display config in set_display: {e}", 'error')

    def reload_config(self, config_path="tools/config.yaml"):
        """Reload configuration from disk and apply to display/slideshow."""
        debug_print("Reloading configuration...")
        new_cfg = self.load_config(config_path)
        if not new_cfg:
            debug_print("Failed to reload config; keeping previous settings", 'error')
            return False
        self.config = new_cfg
        # Apply to display if available
        try:
            if self.display and hasattr(self.display, 'apply_config'):
                self.display.apply_config(self.config)
        except Exception as e:
            debug_print(f"Error applying config to display: {e}", 'error')

        # Reload image list according to new photos.orientation
        if self.running:
            self.current_images = self.load_images()
            self.current_index = 0
            # Immediately show first image from new orientation
            self.show_current_image_now()

        debug_print("Configuration reloaded")
        return True
        
    def load_images(self):
        """Load images from configured folder"""
        # Read fresh configuration from disk to ensure we use the latest values
        fresh_cfg = self.load_config(self.config_path) or {}
        photos_cfg = fresh_cfg.get('photos', {}) if isinstance(fresh_cfg, dict) else {}
        config_cfg = fresh_cfg.get('config', {}) if isinstance(fresh_cfg, dict) else {}

        # Determine orientation (prefer photos.orientation, fallback to legacy key)
        orientation = photos_cfg.get('orientation')
        if orientation is None:
            orientation = config_cfg.get('PHOTO_FRAME_ORIENTATION', 'portrait')
        orientation = str(orientation).lower()

        # Choose folder explicitly: portrait->portrait_folder, landscape->landscape_folder
        if orientation.startswith('p'):
            folder = photos_cfg.get('portrait_folder') or config_cfg.get('PHOTO_FRAME_FOLDER_PORTRAIT') or photos_cfg.get('portrait')
        else:
            folder = photos_cfg.get('landscape_folder') or config_cfg.get('PHOTO_FRAME_FOLDER_LANDSCAPE') or photos_cfg.get('landscape')

        # Update in-memory config to the freshly read config so subsequent flows use current values
        self.config = fresh_cfg
        
        if not folder:
            debug_print("No image folder configured (portrait_folder/landscape_folder missing)", 'error')
            return []

        if not os.path.exists(folder):
            debug_print(f"Image folder not found: {folder}", 'error')
            return []
        
        # Find all image files
        image_extensions = {'.jpg', '.jpeg', '.png', '.bmp', '.gif'}
        images = []
        
        for file_path in Path(folder).iterdir():
            if file_path.suffix.lower() in image_extensions:
                images.append(str(file_path))
        
        # Shuffle for random order
        random.shuffle(images)

        debug_print(f"Loaded {len(images)} images from {folder} (orientation={orientation})")
        return images
    
    def start_slideshow(self):
        """Start the slideshow"""
        if not self.display:
            debug_print("Display not initialized", 'error')
            return False
        # Reload configuration before starting slideshow to pick up any recent changes
        try:
            self.reload_config()
        except Exception:
            pass

        self.current_images = self.load_images()
        if not self.current_images:
            debug_print("No images found", 'error')
            return False
        
        self.running = True
        self.current_index = 0
        
        # Start slideshow in separate thread
        self.slideshow_thread = threading.Thread(target=self._slideshow_loop, daemon=True)
        self.slideshow_thread.start()
        
        debug_print(f"Photo frame slideshow started with {len(self.current_images)} images")
        return True
    
    def _slideshow_loop(self):
        """Main slideshow loop"""
        while self.running:
            if not self.current_images:
                break
                
            # Get current image
            image_path = self.current_images[self.current_index]
            
            # Before displaying, re-read configuration from disk and apply it
            # to ensure we use the latest settings saved by the config editor.
            try:
                fresh_cfg = self.load_config(self.config_path)
                if fresh_cfg:
                    self.config = fresh_cfg
                    if self.display and hasattr(self.display, 'apply_config'):
                        try:
                            self.display.apply_config(self.config)
                        except Exception as e:
                            debug_print(f"Error applying config to display in loop: {e}", 'error')
                    # After applying config, refresh the image list so that
                    # orientation/folder changes take effect immediately.
                    try:
                        new_images = self.load_images()
                        if new_images:
                            self.current_images = new_images
                            self.current_index = 0
                    except Exception as e:
                        debug_print(f"Error reloading image list after config change: {e}", 'error')
            except Exception as e:
                debug_print(f"Error reloading config before display: {e}", 'error')

            # Display with overlay
            debug_print(f"Displaying: {os.path.basename(image_path)}")
            success = False
            try:
                success = self.display.display_image_with_overlay(
                    image_path,
                    show_time=self.config.get('overlay', {}).get('show_time', True),
                    show_date=self.config.get('overlay', {}).get('show_date', True)
                )
            except Exception as e:
                debug_print(f"Error during display_image_with_overlay: {e}", 'error')
            
            if not success:
                debug_print(f"Failed to display {image_path}", 'error')
            
            # Move to next image
            self.current_index = (self.current_index + 1) % len(self.current_images)
            
            # Wait for interval
            time.sleep(self.config['photos']['slideshow_interval'])
    
    def stop_slideshow(self):
        """Stop the slideshow"""
        self.running = False
        if self.slideshow_thread:
            self.slideshow_thread.join(timeout=1)
        debug_print("Slideshow stopped")
    
    def next_image(self):
        """Skip to next image"""
        debug_print(f"next_image called: images={len(self.current_images) if self.current_images else 0}, running={self.running}")
        if self.current_images and self.running:
            self.current_index = (self.current_index + 1) % len(self.current_images)
            debug_print(f"next_image: moved to index {self.current_index}")
    
    def show_current_image_now(self):
        """Immediately display current image (for config changes)"""
        if not self.current_images or not self.running or not self.display:
            return
        
        image_path = self.current_images[self.current_index]
        debug_print(f"Displaying: {os.path.basename(image_path)}")
        try:
            self.display.display_image_with_overlay(
                image_path,
                show_time=self.config.get('overlay', {}).get('show_time', True),
                show_date=self.config.get('overlay', {}).get('show_date', True)
            )
        except Exception as e:
            debug_print(f"Error during immediate display: {e}", 'error')
    
    def previous_image(self):
        """Go to previous image"""
        if self.current_images and self.running:
            self.current_index = (self.current_index - 1) % len(self.current_images)
    
    def switch_orientation(self):
        """Switch between portrait and landscape"""
        current = self.config.get('photos', {}).get('orientation', 'landscape')
        new_orientation = 'portrait' if current == 'landscape' else 'landscape'
        self.config['photos']['orientation'] = new_orientation
        
        # Save to config file
        try:
            import yaml
            with open(self.config_path, 'w', encoding='utf-8') as f:
                yaml.safe_dump(self.config, f, sort_keys=False)
        except Exception as e:
            debug_print(f"Error saving orientation to config: {e}", 'error')
        
        # Apply config to display
        try:
            if self.display and hasattr(self.display, 'apply_config'):
                self.display.apply_config(self.config)
        except Exception as e:
            print(f"Error applying config to display: {e}")
        
        # Reload images and show immediately
        if self.running:
            self.current_images = self.load_images()
            self.current_index = 0
            self.show_current_image_now()
            
        debug_print(f"Switched to {new_orientation} orientation")