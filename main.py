"""Clean Photo Frame Application
Simple digital photo frame for Turing Smart Screen 3.5" Rev A
"""

import sys
import os
import time
import signal
import subprocess
import threading
import yaml
from pathlib import Path

# Debug configuration
DEBUG_ENABLED = True
DEBUG_LEVEL = 'info'

def load_debug_config():
    """Load debug settings from config file"""
    global DEBUG_ENABLED, DEBUG_LEVEL
    try:
        config_path = Path(__file__).parent / "tools" / "config.yaml"
        if config_path.exists():
            with config_path.open("r", encoding="utf-8") as f:
                config = yaml.safe_load(f) or {}
                debug_config = config.get('debug', {})
                DEBUG_ENABLED = debug_config.get('enabled', True)
                DEBUG_LEVEL = debug_config.get('level', 'info')
    except Exception:
        pass  # Use defaults if config loading fails

def debug_print(message, level='info'):
    """Print debug message if debug is enabled and level matches"""
    if not DEBUG_ENABLED:
        return
    if level == 'error' or DEBUG_LEVEL in ['info', 'debug']:
        print(message)

# Load debug config at startup
load_debug_config()
from PIL import Image
import pystray

from lib.display import LCDDisplay
from lib.photoframe import PhotoFrame


class PhotoFrameApp:
    def __init__(self):
        # Core components
        self.display = None
        self.photoframe = None

        # Running state
        self.running = True

        # Tray/icon state
        self.tray_icon = None
        self.tray_thread = None

        # Configuration editor activation state
        self._activation_lock = threading.Lock()
        self._last_activation = 0.0
        self._activation_count = 0
        self._activation_reset_timer = None
        self._config_open = False
        self._config_process = None

    def initialize(self):
        """Initialize the display and photoframe components."""
        try:
            # Load default folders from history and update config
            self._initialize_default_folders()
            
            # Initialize display
            self.display = LCDDisplay()
            if not self.display.initialize():
                print("❌ Failed to initialize display")
                return False

            # Initialize photoframe and attach display
            self.photoframe = PhotoFrame()
            self.photoframe.set_display(self.display)

            debug_print("✅ Initialization complete")
            return True
        except Exception as e:
            print(f"Initialization failed: {e}")
            return False
    
    def _initialize_default_folders(self):
        """Load top folders from history files and save their indices to config"""
        try:
            import yaml
            from pathlib import Path
            
            tools_dir = Path(__file__).parent / "tools"
            portrait_history_file = tools_dir / "portrait_folders_history.txt"
            landscape_history_file = tools_dir / "landscape_folders_history.txt"
            config_file = tools_dir / "config.yaml"
            
            # Load history files
            portrait_history = []
            landscape_history = []
            
            if portrait_history_file.exists():
                with portrait_history_file.open("r", encoding="utf-8") as f:
                    portrait_history = [line.strip() for line in f.readlines() if line.strip()]
                    
            if landscape_history_file.exists():
                with landscape_history_file.open("r", encoding="utf-8") as f:
                    landscape_history = [line.strip() for line in f.readlines() if line.strip()]
            
            # Load existing config
            cfg = {}
            if config_file.exists():
                with config_file.open("r", encoding="utf-8") as f:
                    cfg = yaml.safe_load(f) or {}
            
            if 'config' not in cfg:
                cfg['config'] = {}
            if 'photos' not in cfg:
                cfg['photos'] = {}
            
            # Set default folders (first from history) and indices
            if portrait_history:
                cfg['photos']['portrait_folder'] = portrait_history[0]
                cfg['config']['PHOTO_FRAME_FOLDER_PORTRAIT'] = portrait_history[0]
                cfg['config']['PORTRAIT_HISTORY_LINE'] = 0
                debug_print(f"📁 Default portrait folder: {portrait_history[0]}")
                
            if landscape_history:
                cfg['photos']['landscape_folder'] = landscape_history[0] 
                cfg['config']['PHOTO_FRAME_FOLDER_LANDSCAPE'] = landscape_history[0]
                cfg['config']['LANDSCAPE_HISTORY_LINE'] = 0
                debug_print(f"📁 Default landscape folder: {landscape_history[0]}")
            
            # Save updated config
            with config_file.open("w", encoding="utf-8") as f:
                yaml.safe_dump(cfg, f, sort_keys=False)
                
        except Exception as e:
            debug_print(f"Error initializing default folders: {e}", 'error')
    
    def next_photo(self, icon, item):
        """Next photo (triggered by double-click on tray icon)"""
        debug_print("🖱️ Next photo triggered by double-click on tray icon")
        if self.photoframe:
            self.photoframe.next_image()
            self.photoframe.show_current_image_now()
            print("📷 Skipped to next photo")
        else:
            print("❌ No photoframe instance")
    
    def switch_orientation(self, icon, item):
        """Tray menu: Switch orientation"""
        debug_print("🖱️ Switch orientation clicked in tray")
        if self.photoframe:
            self.photoframe.switch_orientation()
        else:
            print("❌ No photoframe instance")
    
    def open_config_handler(self, icon, item):
        """Handler wired to tray activation; requires two activations within threshold to open config."""
        try:
            now = time.time()
            threshold = 0.5
            with self._activation_lock:
                # reset count if too long since last
                if now - self._last_activation > threshold:
                    self._activation_count = 1
                else:
                    self._activation_count += 1
                self._last_activation = now

                # cancel previous reset timer and start a new one
                if self._activation_reset_timer:
                    try:
                        self._activation_reset_timer.cancel()
                    except Exception:
                        pass
                def _reset():
                    with self._activation_lock:
                        self._activation_count = 0
                self._activation_reset_timer = threading.Timer(threshold + 0.1, _reset)
                self._activation_reset_timer.daemon = True
                self._activation_reset_timer.start()

                if self._activation_count >= 2:
                    # double-activation detected
                    self._activation_count = 0
                    # Open configuration if not already open
                    if not self._config_open:
                        threading.Thread(target=self._open_config_action, daemon=True).start()
                    else:
                        print("⚙️ Configuration already open")
        except Exception as e:
            print(f"Error handling tray activation: {e}")

    def _open_config_menu_only(self, icon, item):
        """Handler only for menu item - opens config immediately"""
        debug_print("⚙️ Configuration opened from menu")
        # Clean up any previous process state
        if self._config_process:
            try:
                if self._config_process.poll() is None:
                    print("⚙️ Configuration already open")
                    return
                else:
                    # Process finished, clean up
                    self._config_process = None
                    self._config_open = False
            except Exception:
                self._config_process = None
                self._config_open = False
        
        if not self._config_open:
            threading.Thread(target=self._open_config_action, daemon=True).start()
        else:
            print("⚙️ Configuration already open")

    def _open_config_action(self):
        """Actually open the configuration editor and track its process so only one opens."""
        try:
            root = os.path.dirname(__file__)
            local_editor = os.path.join(root, 'tools', 'config_editor.py')
            if os.path.exists(local_editor):
                try:
                    proc = subprocess.Popen([sys.executable, local_editor], cwd=root)
                    self._config_process = proc
                    self._config_open = True
                    debug_print("⚙️  Configuration editor opened (tools/config_editor.py)")
                    # Wait for process to exit
                    try:
                        proc.wait()
                    except Exception:
                        pass
                    debug_print("⚙️ Configuration editor closed")
                    # Reload configuration after editor closes
                    self.reload_config()
                finally:
                    self._config_process = None
                    self._config_open = False
            else:
                print("⚠️  Configuration editor not found (expected tools/config_editor.py)")
        except Exception as e:
            print(f"❌ Failed to open configuration: {e}")

    def _icon_click_handler(self, icon, item):
        """Handle clicks on tray icon - single click: next photo, double click: config"""
        try:
            now = time.time()
            threshold = 0.5
            with self._activation_lock:
                # reset count if too long since last
                if now - self._last_activation > threshold:
                    self._activation_count = 1
                else:
                    self._activation_count += 1
                self._last_activation = now

                # cancel previous reset timer and start a new one
                if self._activation_reset_timer:
                    try:
                        self._activation_reset_timer.cancel()
                    except Exception:
                        pass
                def _reset():
                    with self._activation_lock:
                        self._activation_count = 0
                self._activation_reset_timer = threading.Timer(threshold, _reset)
                self._activation_reset_timer.daemon = True
                self._activation_reset_timer.start()

                if self._activation_count >= 2:
                    # double-activation detected - switch to default folder
                    self._activation_count = 0
                    if self._activation_reset_timer:
                        try:
                            self._activation_reset_timer.cancel()
                        except Exception:
                            pass
                    debug_print("[tray] Double click - switch to default folder")
                    threading.Thread(target=self.switch_to_default_folder, daemon=True).start()
        except Exception as e:
            print(f"Error handling icon click: {e}")

    # Note: some pystray backends do not support explicit double-click handlers.
    # We use a default menu item so that clicking the icon invokes the configuration
    # action on most platforms/backends. If your backend still doesn't activate
    # the default action on click, tell me the pystray version and platform and
    # I'll implement a backend-specific workaround.
    
    def exit_app(self, icon, item):
        """Tray menu: Exit application"""
        debug_print("🛑 Exiting application...")
        self.shutdown()
        # Stop the tray icon which will end the application
        if hasattr(icon, 'stop'):
            icon.stop()

    def reload_config(self):
        """Trigger reload of configuration in PhotoFrame and Display."""
        try:
            if self.photoframe:
                ok = self.photoframe.reload_config()
                debug_print("Reload config:", "OK" if ok else "Failed")
                # Do not refresh configuration editor - it was closed by user
            else:
                print("No photoframe instance to reload config")
        except Exception as e:
            print(f"Error reloading config: {e}")

    def _refresh_config_editor(self):
        """Refresh the configuration editor to reflect updated settings."""
        try:
            root = os.path.dirname(__file__)
            local_editor = os.path.join(root, 'tools', 'config_editor.py')
            if os.path.exists(local_editor):
                subprocess.Popen([sys.executable, local_editor, '--refresh'], cwd=root)
                print("⚙️ Configuration editor refreshed")
            else:
                print("⚠️ Configuration editor not found")
        except Exception as e:
            print(f"❌ Failed to refresh configuration editor: {e}")

    def switch_to_default_folder(self):
        """Switch to default folder for current orientation and show first image"""
        try:
            if not self.photoframe:
                return
                
            # Load current config to get default folders
            config = self.photoframe.load_config(self.photoframe.config_path)
            photos_config = config.get('photos', {})
            current_orientation = photos_config.get('orientation', 'landscape').lower()
            
            # Get default folder based on orientation
            if current_orientation == 'portrait':
                default_folder = photos_config.get('default_portrait_folder', '')
            else:
                default_folder = photos_config.get('default_landscape_folder', '')
            
            if default_folder and os.path.exists(default_folder):
                # Update config with default folder
                if current_orientation == 'portrait':
                    photos_config['portrait_folder'] = default_folder
                else:
                    photos_config['landscape_folder'] = default_folder
                
                # Save updated config
                with open(self.photoframe.config_path, 'w', encoding='utf-8') as f:
                    import yaml
                    yaml.safe_dump(config, f, sort_keys=False)
                
                # Reload and show first image
                self.photoframe.reload_config()
                debug_print(f"🔄 Switched to default {current_orientation} folder: {default_folder}")
            else:
                print(f"⚠️  No valid default {current_orientation} folder configured")
                
        except Exception as e:
            print(f"❌ Error switching to default folder: {e}")
    
    def start_slideshow(self):
        """Start the photo slideshow"""
        if not self.photoframe:
            print("❌ No photoframe instance available")
            return False
        if not self.photoframe.start_slideshow():
            print("❌ Failed to start slideshow")
            return False
        return True
    
    def shutdown(self):
        """Shutdown application"""
        debug_print("🛑 Shutting down...")
        self.running = False
        
        # Stop slideshow
        if self.photoframe:
            self.photoframe.stop_slideshow()
        
        # Clear display
        if self.display:
            self.display.close()
        
        # Stop tray icon
        if self.tray_icon:
            self.tray_icon.stop()
        
        debug_print("✅ Shutdown complete")
    
    def signal_handler(self, signum, frame):
        """Handle system signals"""
        print(f"📡 Received signal {signum}")
        self.shutdown()
    
    def run(self):
        """Main application loop"""
        # Setup signal handlers
        signal.signal(signal.SIGINT, self.signal_handler)
        signal.signal(signal.SIGTERM, self.signal_handler)
        
        # Initialize
        if not self.initialize():
            return False
        
        # Start slideshow
        if not self.start_slideshow():
            return False
        
        debug_print("🖼️  Photo Frame is running... (Press Ctrl+C to stop)")
        
        # Keep main thread alive
        try:
            # Setup tray icon (best-effort)
            try:
                self._setup_tray()
            except Exception:
                pass

            while self.running:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\n⌨️  Keyboard interrupt received")
            self.shutdown()

        return True

    def _setup_tray(self):
        """Create and start the tray icon (best-effort)."""
        try:
            # Ensure pystray and PIL Image are available
            if 'pystray' not in globals() or 'Image' not in globals():
                print("⚠️  pystray or PIL not available; skipping tray icon")
                return

            icon_path = os.path.join(os.path.dirname(__file__), 'res', 'icons', 'photoframe-photos', '64.png')
            icon_image = None
            try:
                if os.path.exists(icon_path):
                    icon_image = Image.open(icon_path)
                else:
                    # create a simple transparent placeholder
                    icon_image = Image.new('RGBA', (64, 64), (0, 0, 0, 0))
            except Exception:
                icon_image = Image.new('RGBA', (64, 64), (0, 0, 0, 0))

            menu = pystray.Menu(
                pystray.MenuItem('Next Photo (Hidden)', self._icon_click_handler, default=True, visible=False),
                pystray.MenuItem('Switch Orientation', self.switch_orientation),
                pystray.MenuItem('Open Configuration', self._open_config_menu_only),
                pystray.MenuItem('Exit Photo Frame', self.exit_app)
            )

            # Create icon
            try:
                self.tray_icon = pystray.Icon('PhotoFrame', icon_image, 'Photo Frame - Running', menu=menu)
            except Exception as e:
                # Older pystray variants may accept different args
                try:
                    self.tray_icon = pystray.Icon('PhotoFrame', icon_image)
                    self.tray_icon.title = 'Photo Frame - Running'
                    self.tray_icon.menu = menu
                except Exception as e2:
                    print(f"⚠️  Failed to create tray icon object: {e} / {e2}")
                    self.tray_icon = None

            if not self.tray_icon:
                return

            # Start the tray icon (use run_detached when available)
            try:
                if hasattr(self.tray_icon, 'run_detached'):
                    self.tray_icon.run_detached()
                    debug_print("✅ Tray icon started (detached)")
                else:
                    self.tray_thread = threading.Thread(target=self.tray_icon.run, daemon=True)
                    self.tray_thread.start()
                    debug_print("✅ Tray icon started (thread)")
            except Exception as e:
                print(f"⚠️  Tray icon run failed: {e}")
        except Exception as e:
            print(f"⚠️  Tray icon setup failed: {e}")
def main():
    """Main entry point"""
    app = PhotoFrameApp()
    return app.run()


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)