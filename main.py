"""Clean Photo Frame Application
Simple digital photo frame for Turing Smart Screen 3.5" Rev A
"""

import sys
import os
import time
import queue
import signal
import subprocess
import threading

# Import shared utilities
from lib.debug_utils import debug_print
from lib.constants import *
from lib.paths import (
    app_dir,
    config_path,
    portrait_history_path,
    landscape_history_path,
    resource_path,
)
from PIL import Image
import pystray

from lib.display import LCDDisplay
from lib.photoframe import PhotoFrame
from lib.single_instance import SingleInstance


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

        # Configuration editor state
        self._config_open = False
        self._config_process = None

        # Kolejka polecen z zasobnika - patrz _command_worker()
        self._commands = queue.Queue()
        self._command_thread = None
        self._last_click_time = 0.0

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
            self.photoframe = PhotoFrame(str(config_path()))
            self.photoframe.set_display(self.display)

            debug_print("✅ Initialization complete")
            return True
        except Exception as e:
            print(f"Initialization failed: {e}")
            return False
    
    def _initialize_default_folders(self):
        """Uzupełnij brakujące foldery w konfiguracji pierwszym wpisem z historii.

        Świadomie NIE nadpisujemy folderów wybranych przez użytkownika w edytorze -
        wcześniejsza wersja robiła to przy każdym starcie, więc ustawienia znikały
        po restarcie aplikacji.
        """
        try:
            from lib.config_manager import config_manager

            def _read_history(path):
                try:
                    if path.exists():
                        with path.open("r", encoding="utf-8") as f:
                            return [line.strip() for line in f if line.strip()]
                except OSError as e:
                    debug_print(f"Error reading history file {path}: {e}", 'error')
                return []

            portrait_history = _read_history(portrait_history_path())
            landscape_history = _read_history(landscape_history_path())

            cfg = config_manager.load_config(force_reload=True)
            cfg.setdefault('config', {})
            cfg.setdefault('photos', {})

            def _needs_default(folder):
                return not folder or not os.path.isdir(str(folder))

            changed = False

            if portrait_history and _needs_default(cfg['photos'].get('portrait_folder')):
                cfg['photos']['portrait_folder'] = portrait_history[0]
                cfg['config']['PHOTO_FRAME_FOLDER_PORTRAIT'] = portrait_history[0]
                cfg['config']['PORTRAIT_HISTORY_LINE'] = 0
                changed = True
                debug_print(f"📁 Default portrait folder: {portrait_history[0]}")

            if landscape_history and _needs_default(cfg['photos'].get('landscape_folder')):
                cfg['photos']['landscape_folder'] = landscape_history[0]
                cfg['config']['PHOTO_FRAME_FOLDER_LANDSCAPE'] = landscape_history[0]
                cfg['config']['LANDSCAPE_HISTORY_LINE'] = 0
                changed = True
                debug_print(f"📁 Default landscape folder: {landscape_history[0]}")

            if changed:
                config_manager.save_config(cfg)

        except Exception as e:
            debug_print(f"Unexpected error initializing default folders: {e}", 'error')
    
    # ------------------------------------------------------------------
    # Kolejka polecen z zasobnika
    #
    # pystray na Windows wola callbacki SYNCHRONICZNIE na watku pompy
    # komunikatow okna zasobnika (_win32.py:_on_notify). Kazda dluzsza praca -
    # skan katalogu, zapis YAML, wyslanie klatki po porcie szeregowym (sekundy) -
    # zamrazala wiec ikone: kolejne klikniecia ginely, menu sie nie rozwijalo.
    # Handlery tylko wrzucaja polecenie do kolejki i natychmiast wracaja.
    # ------------------------------------------------------------------

    def _enqueue(self, command):
        """Zlec polecenie watkowi roboczemu; pomija duplikaty juz czekajace w kolejce."""
        try:
            if command in tuple(self._commands.queue):
                debug_print(f"⏱️ Polecenie '{command}' juz oczekuje - pomijam")
                return
            self._commands.put_nowait(command)
        except Exception as e:
            debug_print(f"Nie udalo sie zakolejkowac '{command}': {e}", 'error')

    def _command_worker(self):
        """Wykonuje polecenia z zasobnika poza watkiem pompy komunikatow."""
        handlers = {
            'default_folder': self._cmd_default_folder,
            'switch_orientation': self._cmd_switch_orientation,
            'open_config': self._cmd_open_config,
            'exit': self._cmd_exit,
        }
        while True:
            command = self._commands.get()
            try:
                if command is None:
                    break
                handler = handlers.get(command)
                if handler is None:
                    debug_print(f"Nieznane polecenie zasobnika: {command}", 'error')
                    continue
                handler()
            except Exception as e:
                debug_print(f"Blad podczas obslugi '{command}': {e}", 'error')
            finally:
                self._commands.task_done()

    def _cmd_default_folder(self):
        now = time.time()
        if now - self._last_click_time < 1.0:
            debug_print("⏱️ Klikniecie pominiete (cooldown 1 s)")
            return
        self._last_click_time = now
        debug_print("🖱️ Tray icon clicked - switching to default folder")
        self.switch_to_default_folder()

    def _cmd_switch_orientation(self):
        if self.photoframe:
            self.photoframe.switch_orientation()
        else:
            debug_print("❌ No photoframe instance", 'error')

    def _cmd_exit(self):
        debug_print("🛑 Exiting application...")
        self.shutdown()

    def tray_icon_clicked(self, icon, item):
        """Lewy klik w ikone - przelacz na domyslny folder."""
        self._enqueue('default_folder')

    def switch_orientation(self, icon, item):
        """Tray menu: Switch orientation"""
        debug_print("🖱️ Switch orientation clicked in tray")
        self._enqueue('switch_orientation')

    def _open_config_menu_only(self, icon, item):
        """Tray menu: Open configuration"""
        debug_print("⚙️ Configuration opened from menu")
        self._enqueue('open_config')

    def _cmd_open_config(self):
        """Otworz edytor konfiguracji (jedna instancja na raz)."""
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
            root = str(app_dir())
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

    def exit_app(self, icon, item):
        """Tray menu: Exit application"""
        self._enqueue('exit')

    def reload_config(self):
        """Trigger reload of configuration in PhotoFrame and Display."""
        try:
            if self.photoframe:
                ok = self.photoframe.reload_config()
                debug_print(f"Reload config: {'OK' if ok else 'Failed'}")
                # Do not refresh configuration editor - it was closed by user
            else:
                print("No photoframe instance to reload config")
        except Exception as e:
            print(f"Error reloading config: {e}")

    def _refresh_config_editor(self):
        """Refresh the configuration editor to reflect updated settings."""
        try:
            root = str(app_dir())
            local_editor = os.path.join(root, 'tools', 'config_editor.py')
            if os.path.exists(local_editor):
                subprocess.Popen([sys.executable, local_editor, '--refresh'], cwd=root)
                print("⚙️ Configuration editor refreshed")
            else:
                print("⚠️ Configuration editor not found")
        except Exception as e:
            print(f"❌ Failed to refresh configuration editor: {e}")

    def switch_to_default_folder(self, icon=None, item=None):
        """Set default folder (first from history) for current orientation - ON CLICK SYSTRAY"""
        try:
            if not self.photoframe:
                debug_print("No photoframe instance available")
                return
            
            # Check if lock is active - if yes, exit
            if self.photoframe._reload_lock:
                print("⏱️ Reload already in progress, ignoring click")
                return
            
            # Set lock to block slideshow loop
            self.photoframe._reload_lock = True
            print("🔒 Lock set - blocking slideshow loop")
            
            try:
                # Get current orientation from config
                config = self.photoframe.load_config()
                current_orientation = config.get('photos', {}).get('orientation', 'portrait').lower()
                
                # Read appropriate history file - ALWAYS use first line (default)
                if current_orientation.startswith('p'):  # portrait
                    history_file = portrait_history_path()
                else:  # landscape
                    history_file = landscape_history_path()
                
                if not history_file.exists():
                    debug_print(f"History file not found: {history_file}")
                    return
                    
                # Read first line (default folder)
                with open(history_file, 'r', encoding='utf-8') as f:
                    lines = [line.strip() for line in f.readlines() if line.strip()]
                    
                if not lines:
                    debug_print(f"No folders in history file: {history_file}")
                    return
                    
                # ALWAYS use first folder from history (index 0)
                default_folder = lines[0]
                
                if not os.path.exists(default_folder):
                    debug_print(f"Default folder does not exist: {default_folder}")
                    return
                
                print(f"🔄 Setting default {current_orientation} folder: {default_folder}")
                
                # Update config with default folders from history (first paths)
                if current_orientation.startswith('p'):  # portrait
                    config['photos']['portrait_folder'] = default_folder
                    config['config']['PHOTO_FRAME_FOLDER_PORTRAIT'] = default_folder
                    config['config']['PORTRAIT_HISTORY_LINE'] = 0
                else:  # landscape
                    config['photos']['landscape_folder'] = default_folder
                    config['config']['PHOTO_FRAME_FOLDER_LANDSCAPE'] = default_folder
                    config['config']['LANDSCAPE_HISTORY_LINE'] = 0
                
                # Save config
                from lib.config_manager import config_manager
                if config_manager.save_config(config):
                    print(f"✅ Config saved with default folder")
                else:
                    print(f"❌ Failed to save config")
                    return
                
                # Update photoframe's in-memory config
                self.photoframe.config = config
                
                # Reload images from location in config (use current config, already set above)
                if self.photoframe.running:
                    self.photoframe.current_images = self.photoframe.load_images(use_current_config=True)
                    self.photoframe.current_index = 0
                    # Load first image immediately
                    self.photoframe.show_current_image_now()
                    print(f"✅ Loaded {len(self.photoframe.current_images)} images from default folder")
                    
            finally:
                # Release lock after 1 second
                def release_lock():
                    time.sleep(1.0)
                    self.photoframe._reload_lock = False
                    print("🔓 Lock released after 1 second")
                
                threading.Thread(target=release_lock, daemon=True).start()
            
        except Exception as e:
            debug_print(f"❌ Error switching to default folder: {e}", 'error')
            print(f"❌ Error: {e}")
            # Ensure lock is released on error
            if self.photoframe:
                self.photoframe._reload_lock = False
    
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
        if not self.running:
            return
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
            try:
                self.tray_icon.stop()
            except Exception as e:
                debug_print(f"Blad zatrzymywania ikony zasobnika: {e}", 'error')

        # Obudz watek polecen, zeby zakonczyl petle
        try:
            self._commands.put_nowait(None)
        except Exception:
            pass

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

        # Watek obslugujacy polecenia z zasobnika
        self._command_thread = threading.Thread(
            target=self._command_worker, name='tray-commands', daemon=True)
        self._command_thread.start()

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

            icon_path = str(resource_path('res', 'icons', 'photoframe-photos', '64.png'))
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
                pystray.MenuItem('Switch to Default Folder', self.tray_icon_clicked, default=True, visible=False),
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
    instance = SingleInstance()
    if not instance.acquire():
        debug_print("ℹ️  Photo Frame juz dziala - zamykam druga instancje")
        return True

    try:
        app = PhotoFrameApp()
        return app.run()
    finally:
        instance.release()


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)