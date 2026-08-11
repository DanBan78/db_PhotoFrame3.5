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
from .config_manager import config_manager, settings, SECTION
from .constants import *
from .weather import weather, format_temperature

class PhotoFrame:
    def __init__(self, config_path=DEFAULT_CONFIG_PATH):
        # Load initial configuration using config manager
        config_manager.config_path = config_path
        self.config = config_manager.load_config()
        self.config.setdefault(SECTION, {})
        self.display = None
        self.running = False
        self.current_images = []
        self.current_index = 0
        self.slideshow_thread = None
        self._reload_lock = False  # Lock to prevent slideshow loop reload during manual operations
        # Wysylka klatki musi byc niepodzielna: w lcd_comm_rev_a komenda
        # DISPLAY_BITMAP idzie poza update_queue_mutex, a dane obrazu w srodku,
        # wiec dwa watki wysylajace naraz (pokaz slajdow + akcja z zasobnika)
        # przeplataja sie na porcie szeregowym.
        self._display_lock = threading.RLock()
        # Zegar i temperatura dochodza dopiero OVERLAY_DELAY_SECONDS po zdjeciu
        self._overlay_timer = None
        self._frame_seq = 0
        
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

        # Reload image list according to new orientation_portrait
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
        
        cfg = settings(fresh_cfg)
        portrait = bool(cfg['orientation_portrait'])
        orientation = 'portrait' if portrait else 'landscape'
        folder = cfg['active_portrait_folder'] if portrait else cfg['active_landscape_folder']

        # Update in-memory config to the freshly read config so subsequent flows use current values
        self.config = fresh_cfg
        
        if not folder:
            debug_print(f"Brak skonfigurowanego folderu (active_{orientation}_folder)", 'error')
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
        
        # Kolejnosc wyswietlania: losowa albo alfabetyczna wg nazwy pliku
        if cfg['shuffle']:
            random.shuffle(images)
        else:
            images.sort(key=lambda p: os.path.basename(p).lower())

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
                    # Przeladowujemy liste zdjec tylko gdy zmienilo sie cos,
                    # co na nia wplywa (orientacja, aktywne foldery, kolejnosc)
                    current = settings(self.config)
                    fresh = settings(fresh_cfg)
                    watched = ('orientation_portrait', 'active_portrait_folder',
                               'active_landscape_folder', 'shuffle')
                    config_changed = any(current[k] != fresh[k] for k in watched)


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
            
            # Odczekaj zadany interwal przed nastepnym zdjeciem
            try:
                interval = max(1, int(settings(self.config)['interval']))
            except (TypeError, ValueError):
                interval = DEFAULT_SLIDESHOW_INTERVAL
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
        with self._display_lock:
            if not self.current_images or not self.running or not self.display:
                return

            image_path = self.current_images[self.current_index]
            debug_print(f"Displaying: {os.path.basename(image_path)}")
            try:
                self._frame_seq += 1
                self.display.show_photo(image_path)
                self._schedule_overlays(self._frame_seq)
            except Exception as e:
                debug_print(f"Error during immediate display: {e}", 'error')

    def _schedule_overlays(self, seq):
        """Zaplanuj dorysowanie zegara i temperatury na juz pokazanym zdjeciu."""
        cfg = settings(self.config)
        if not cfg['show_time'] and not cfg['show_temperature']:
            return

        if self._overlay_timer is not None:
            self._overlay_timer.cancel()

        timer = threading.Timer(OVERLAY_DELAY_SECONDS, self._draw_overlays, args=(seq,))
        timer.daemon = True
        timer.name = 'overlays'
        timer.start()
        self._overlay_timer = timer

    def _draw_overlays(self, seq):
        """Dorysuj nakladki, o ile zdjecie nie zmienilo sie w miedzyczasie."""
        with self._display_lock:
            # seq chroni przed wyscigiem: gdy w ciagu tych 2 sekund pojawilo sie
            # nowe zdjecie, nakladki dla poprzedniego sa juz nieaktualne.
            if seq != self._frame_seq or not self.running or not self.display:
                return

            cfg = settings(self.config)
            temperature_text = ''
            if cfg['show_temperature']:
                weather.set_location(cfg['latitude'], cfg['longitude'])
                temperature_text = format_temperature(weather.get_temperature())

            try:
                self.display.draw_overlays(show_time=bool(cfg['show_time']),
                                           temperature_text=temperature_text)
            except Exception as e:
                debug_print(f"Error drawing overlays: {e}", 'error')

    def show_next_image_now(self):
        """Przejdz do nastepnego zdjecia i pokaz je od razu (pojedynczy klik w ikone)."""
        with self._display_lock:
            if not self.current_images or not self.running:
                debug_print("Brak zdjec do pokazania", 'error')
                return False
            self.next_image()
            self.show_current_image_now()
            return True
    
    def previous_image(self):
        """Go to previous image"""
        if self.current_images and self.running:
            self.current_index = (self.current_index - 1) % len(self.current_images)
    
    def switch_orientation(self):
        """Switch between portrait and landscape"""
        portrait = not bool(settings(self.config)['orientation_portrait'])
        self.config.setdefault(SECTION, {})['orientation_portrait'] = portrait
        new_orientation = 'portrait' if portrait else 'landscape'


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
            debug_print(f"Error applying config to display: {e}", 'error')
        
        # Reload images and show immediately (use current config already set above)
        if self.running:
            self.current_images = self.load_images(use_current_config=True)
            self.current_index = 0
            self.show_current_image_now()
            
        debug_print(f"Switched to {new_orientation} orientation")