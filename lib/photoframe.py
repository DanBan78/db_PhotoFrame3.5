"""
Simple Photo Frame Slideshow
Clean implementation for displaying photos
"""

import os
import time
import random
import threading
from pathlib import Path

# Import shared utilities
from .debug_utils import debug_print
from .config_manager import config_manager
from .constants import *

class PhotoFrame:
    def __init__(self, config_path=DEFAULT_CONFIG_PATH):
        # Load initial configuration using config manager
        config_manager.config_path = config_path
        self.config = config_manager.load_config()
        # Ensure photos section exists
        if 'photos' not in self.config:
            self.config['photos'] = {}
        self.display = None
        self.running = False
        self.current_images = []
        self.current_index = 0
        self.slideshow_thread = None
        self._reload_lock = False  # Lock to prevent slideshow loop reload during manual operations
        
    def load_config(self):
        """Load configuration using config manager"""
        self.config = config_manager.load_config()
        return self.config
    
    def get_default_config(self):
        """Return default configuration"""
        return config_manager.get_default_config()
    
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

    def reload_config(self):
        """Reload configuration from disk and apply to display/slideshow."""
        debug_print("Reloading configuration...")
        new_cfg = config_manager.load_config(force_reload=True)
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
            self.current_images = self.load_images(use_current_config=True)
            self.current_index = 0
            # Immediately show first image from new orientation
            self.show_current_image_now()

        debug_print("Configuration reloaded")
        return True
        
    def load_images(self, use_current_config=False):
        """Load images from configured folder
        
        Args:
            use_current_config: If True, use self.config instead of reloading from disk
        """
        # Use current config or read fresh from disk
        if use_current_config:
            fresh_cfg = self.config
        else:
            fresh_cfg = config_manager.load_config(force_reload=True, silent=True)
        
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

        # Use current config (already loaded by reload_config above)
        self.current_images = self.load_images(use_current_config=True)
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
            
            # Skip this cycle if reload lock is active (manual operation in progress)
            if self._reload_lock:
                time.sleep(0.1)  # Small sleep to avoid busy loop
                continue
            
            # Before displaying, check if configuration changed on disk
            # Only reload if something actually changed to avoid spam
            try:
                fresh_cfg = config_manager.load_config(force_reload=True, silent=True)
                if fresh_cfg:
                    # Check if relevant config changed (orientation or folders)
                    config_changed = False
                    if self.config.get('photos', {}).get('orientation') != fresh_cfg.get('photos', {}).get('orientation'):
                        config_changed = True
                    if self.config.get('photos', {}).get('portrait_folder') != fresh_cfg.get('photos', {}).get('portrait_folder'):
                        config_changed = True
                    if self.config.get('photos', {}).get('landscape_folder') != fresh_cfg.get('photos', {}).get('landscape_folder'):
                        config_changed = True
                    
                    # Only if config changed, apply it and reload images
                    if config_changed:
                        debug_print("📋 Config changed detected - reloading images")
                        self.config = fresh_cfg
                        if self.display and hasattr(self.display, 'apply_config'):
                            try:
                                self.display.apply_config(self.config)
                            except Exception as e:
                                debug_print(f"Error applying config to display in loop: {e}", 'error')
                        # Refresh the image list
                        try:
                            new_images = self.load_images(use_current_config=True)
                            if new_images:
                                self.current_images = new_images
                                self.current_index = 0
                        except Exception as e:
                            debug_print(f"Error reloading image list after config change: {e}", 'error')
                    # If nothing changed, just use fresh config silently without any logs
                    else:
                        self.config = fresh_cfg
            except Exception as e:
                debug_print(f"Error checking config in slideshow loop: {e}", 'error')

            # Display current image using show_current_image_now
            self.show_current_image_now()
            
            # Move to next image
            self.current_index = (self.current_index + 1) % len(self.current_images)
            
            # Wait for interval - check both new and old config locations
            interval = self.config.get('slideshow', {}).get('interval') or self.config.get('photos', {}).get('slideshow_interval', 30)
            time.sleep(interval)
    
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
            # Get show_time from slideshow section (config editor saves it there)
            show_time = self.config.get('slideshow', {}).get('show_time', True)
            show_date = self.config.get('slideshow', {}).get('show_date', False)
            self.display.display_image_with_overlay(
                image_path,
                show_time=show_time,
                show_date=show_date
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
        
        # Save to config file using config manager
        try:
            config_manager.save_config(self.config)
            debug_print(f"Saved orientation change to config: {new_orientation}")
            # Force reload to ensure consistency
            self.config = config_manager.load_config(force_reload=True)
        except Exception as e:
            debug_print(f"Error saving orientation to config: {e}", 'error')
        
        # Apply config to display
        try:
            if self.display and hasattr(self.display, 'apply_config'):
                self.display.apply_config(self.config)
        except Exception as e:
            print(f"Error applying config to display: {e}")
        
        # Reload images and show immediately (use current config already set above)
        if self.running:
            self.current_images = self.load_images(use_current_config=True)
            self.current_index = 0
            self.show_current_image_now()
            
        debug_print(f"Switched to {new_orientation} orientation")