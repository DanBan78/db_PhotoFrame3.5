"""Clean Photo Frame Application
Simple digital photo frame for Turing Smart Screen 3.5" Rev A
"""

import sys
import os
import time
import signal
import subprocess
import threading
from PIL import Image
import pystray
import yaml

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
            # Initialize display
            self.display = LCDDisplay()
            if not self.display.initialize():
                print("❌ Failed to initialize display")
                return False

            # Initialize photoframe and attach display
            self.photoframe = PhotoFrame()
            self.photoframe.set_display(self.display)

            print("✅ Initialization complete")
            return True
        except Exception as e:
            print(f"Initialization failed: {e}")
            return False
    
    def next_photo(self, icon, item):
        """Tray menu: Next photo"""
        if item is None:
            print("🖱️ Next photo triggered by double-click on tray icon")
        else:
            print("🖱️ Next photo clicked in tray menu")
        if self.photoframe:
            self.photoframe.next_image()
            self.photoframe.show_current_image_now()
            print("📷 Skipped to next photo")
        else:
            print("❌ No photoframe instance")
    
    def switch_orientation(self, icon, item):
        """Tray menu: Switch orientation"""
        print("🖱️ Switch orientation clicked in tray")
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
                    print("⚙️  Configuration editor opened (tools/config_editor.py)")
                    # Wait for process to exit
                    try:
                        proc.wait()
                    except Exception:
                        pass
                    print("⚙️ Configuration editor closed")
                    # Reload configuration after editor closes
                    self.reload_config()
                finally:
                    self._config_process = None
                    self._config_open = False
            else:
                print("⚠️  Configuration editor not found (expected tools/config_editor.py)")
        except Exception as e:
            print(f"❌ Failed to open configuration: {e}")

    def _menu_open_config(self, icon, item):
        """Handler bound to tray menu item - logs the click and opens config in background."""
        try:
            # Log invocation
            print("[tray] _menu_open_config invoked, item=", repr(item))
            try:
                with open(os.path.join(os.path.dirname(__file__), 'tray_events.log'), 'a', encoding='utf-8') as lf:
                    lf.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} - menu_invoked item={repr(item)}\n")
            except Exception:
                pass

            # If invoked from the menu (item is not None), open immediately.
            if item is not None:
                if not self._config_open:
                    threading.Thread(target=self._open_config_action, daemon=True).start()
                else:
                    print("⚙️ Configuration already open (menu)")
                return

            # Otherwise this is an icon activation (click). Require double-activation.
            now = time.time()
            threshold = 0.5
            with self._activation_lock:
                if now - self._last_activation > threshold:
                    self._activation_count = 1
                else:
                    self._activation_count += 1
                self._last_activation = now

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
                    if not self._config_open:
                        threading.Thread(target=self._open_config_action, daemon=True).start()
                    else:
                        print("⚙️ Configuration already open (double-activation)")
                else:
                    print(f"[tray] single activation ({self._activation_count}) - waiting for double-activation")
        except Exception as e:
            print(f"[tray] Failed to handle menu open config: {e}")

    # Note: some pystray backends do not support explicit double-click handlers.
    # We use a default menu item so that clicking the icon invokes the configuration
    # action on most platforms/backends. If your backend still doesn't activate
    # the default action on click, tell me the pystray version and platform and
    # I'll implement a backend-specific workaround.
    
    def exit_app(self, icon, item):
        """Tray menu: Exit application"""
        print("🛑 Exiting application...")
        self.shutdown()

    def reload_config(self):
        """Trigger reload of configuration in PhotoFrame and Display."""
        try:
            if self.photoframe:
                ok = self.photoframe.reload_config()
                print("Reload config:", "OK" if ok else "Failed")
            else:
                print("No photoframe instance to reload config")
        except Exception as e:
            print(f"Error reloading config: {e}")
    
    def start_slideshow(self):
        """Start the photo slideshow"""
        if not self.photoframe.start_slideshow():
            print("❌ Failed to start slideshow")
            return False
        return True
    
    def shutdown(self):
        """Shutdown application"""
        print("🛑 Shutting down...")
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
        
        print("✅ Shutdown complete")
        sys.exit(0)
    
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
        
        print("🖼️  Photo Frame is running... (Press Ctrl+C to stop)")
        
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
                pystray.MenuItem('Next Photo', self.next_photo, default=True),
                pystray.MenuItem('Switch Orientation', self.switch_orientation),
                pystray.MenuItem('Open Configuration', self._menu_open_config),
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
                    print("✅ Tray icon started (detached)")
                else:
                    self.tray_thread = threading.Thread(target=self.tray_icon.run, daemon=True)
                    self.tray_thread.start()
                    print("✅ Tray icon started (thread)")
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