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
from lib.config_manager import settings, SECTION
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

        # Rozroznianie pojedynczego i podwojnego klikniecia w ikone
        self._click_lock = threading.Lock()
        self._pending_clicks = 0
        self._click_timer = None

        # Sledzenie zmian config.yaml (np. przycisk SET w edytorze)
        self._config_mtime = None

    def initialize(self):
        """Initialize the display and photoframe components."""
        try:
            # Load default folders from history and update config
            self._initialize_default_folders()
            
            # Initialize display
            self.display = LCDDisplay()
            if not self.display.initialize():
                debug_print("❌ Failed to initialize display", 'error')
                return False

            # Initialize photoframe and attach display
            self.photoframe = PhotoFrame(str(config_path()))
            self.photoframe.set_display(self.display)

            debug_print("✅ Initialization complete")
            return True
        except Exception as e:
            debug_print(f"Initialization failed: {e}", 'error')
            return False
    
    def _initialize_default_folders(self):
        """Uzupelnij brakujace foldery w konfiguracji pierwszym wpisem z historii.

        Swiadomie NIE nadpisujemy folderow wybranych przez uzytkownika -
        wczesniejsza wersja robila to przy kazdym starcie, wiec ustawienia
        znikaly po restarcie aplikacji.
        """
        try:
            from lib.config_manager import config_manager

            def _first_entry(path):
                try:
                    if path.exists():
                        with path.open("r", encoding="utf-8") as f:
                            for line in f:
                                line = line.strip()
                                if line:
                                    return line
                except OSError as e:
                    debug_print(f"Error reading history file {path}: {e}", 'error')
                return ''

            cfg = config_manager.load_config(force_reload=True)
            section = cfg.setdefault(SECTION, {})
            values = settings(cfg)
            changed = False

            def _missing(folder):
                return not folder or not os.path.isdir(str(folder))

            for orientation, history_path in (('portrait', portrait_history_path()),
                                              ('landscape', landscape_history_path())):
                default_key = f'default_{orientation}_folder'
                active_key = f'active_{orientation}_folder'

                if _missing(values[default_key]):
                    candidate = _first_entry(history_path) or values[active_key]
                    if candidate and not _missing(candidate):
                        section[default_key] = candidate
                        values[default_key] = candidate
                        changed = True
                        debug_print(f"📁 Folder domyslny ({orientation}): {candidate}")

                if _missing(values[active_key]) and not _missing(values[default_key]):
                    section[active_key] = values[default_key]
                    values[active_key] = values[default_key]
                    changed = True
                    debug_print(f"📁 Folder aktywny ({orientation}): {values[default_key]}")

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
            'next_image': self._cmd_next_image,
            'switch_orientation': self._cmd_switch_orientation,
            'open_config': self._cmd_open_config,
            'reload_config': self._cmd_reload_config,
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
        debug_print("🖱️ Podwojny klik - przelaczam na folder domyslny")
        self.switch_to_default_folder()
        self._note_config_written()

    def _cmd_next_image(self):
        """Pojedynczy klik - pokaz nastepne zdjecie."""
        if not self.photoframe:
            debug_print("❌ No photoframe instance", 'error')
            return
        debug_print("🖱️ Pojedynczy klik - nastepne zdjecie")
        self.photoframe.show_next_image_now()

    def _cmd_reload_config(self):
        """Konfiguracja zmieniona na dysku (np. przycisk SET w edytorze)."""
        debug_print("📋 Wykryto zmiane config.yaml - przeladowuje")
        self.reload_config()

    def _cmd_switch_orientation(self):
        if self.photoframe:
            self.photoframe.switch_orientation()
            self._note_config_written()
        else:
            debug_print("❌ No photoframe instance", 'error')

    def _note_config_written(self):
        """Zapamietaj, ze to my zapisalismy config - watcher ma tego nie liczyc
        jako zmiany z zewnatrz (inaczej zdjecie zmienialoby sie dwa razy)."""
        try:
            self._config_mtime = config_path().stat().st_mtime
        except OSError:
            pass

    def _config_watcher(self):
        """Pilnuje config.yaml i reaguje na zmiany z edytora (np. przycisk SET).

        Pokaz slajdow sprawdza konfiguracje dopiero przed kolejnym zdjeciem,
        czyli nawet po 40 s. Watcher skraca to do sekundy.
        """
        path = config_path()
        while self.running:
            time.sleep(1.0)
            try:
                mtime = path.stat().st_mtime
            except OSError:
                continue
            if self._config_mtime is None:
                self._config_mtime = mtime
                continue
            if mtime != self._config_mtime:
                self._config_mtime = mtime
                self._enqueue('reload_config')

    def _cmd_exit(self):
        debug_print("🛑 Exiting application...")
        self.shutdown()

    # Okno, w ktorym drugie klikniecie liczy sie jako podwojny klik.
    # Windows nie wysyla tu WM_LBUTTONDBLCLK: pystray rejestruje klase okna ze
    # style=0, czyli bez CS_DBLCLKS (_win32.py:375), wiec dwuklik dociera jako
    # dwa WM_LBUTTONUP i musimy go rozpoznac sami po czasie.
    DOUBLE_CLICK_WINDOW = 0.4

    def tray_icon_clicked(self, icon, item):
        """Lewy klik w ikone: 1 klik = nastepne zdjecie, 2 kliki = folder domyslny."""
        with self._click_lock:
            self._pending_clicks += 1
            if self._click_timer is None:
                self._click_timer = threading.Timer(
                    self.DOUBLE_CLICK_WINDOW, self._resolve_clicks)
                self._click_timer.daemon = True
                self._click_timer.start()

    def _resolve_clicks(self):
        """Po uplywie okna dwukliku zdecyduj, ktore polecenie wykonac."""
        with self._click_lock:
            clicks = self._pending_clicks
            self._pending_clicks = 0
            self._click_timer = None

        if clicks <= 0:
            return
        self._enqueue('default_folder' if clicks >= 2 else 'next_image')

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
                    debug_print("⚙️ Configuration already open")
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
            debug_print("⚙️ Configuration already open")

    @staticmethod
    def _editor_command():
        """Polecenie uruchamiajace edytor konfiguracji.

        W wersji zamrozonej sys.executable to PhotoFrame.exe - PyInstaller
        ignoruje podany za nim skrypt, wiec podanie sciezki do .py uruchamialo
        po prostu druga kopie aplikacji. Edytor jest teraz czescia paczki
        i wolamy go wlasnym przelacznikiem --config.
        """
        if getattr(sys, 'frozen', False):
            return [sys.executable, '--config']
        return [sys.executable, os.path.abspath(__file__), '--config']

    def _open_config_action(self):
        """Actually open the configuration editor and track its process so only one opens."""
        try:
            command = self._editor_command()
            creationflags = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
            try:
                proc = subprocess.Popen(command, cwd=str(app_dir()), creationflags=creationflags)
                self._config_process = proc
                self._config_open = True
                debug_print(f"⚙️  Configuration editor opened: {' '.join(command)}")
                try:
                    returncode = proc.wait()
                except Exception:
                    returncode = None
                if returncode:
                    debug_print(f"⚙️ Edytor konfiguracji zakonczyl sie kodem {returncode}", 'error')
                else:
                    debug_print("⚙️ Configuration editor closed")
                # Reload configuration after editor closes
                self.reload_config()
            finally:
                self._config_process = None
                self._config_open = False
        except Exception as e:
            debug_print(f"❌ Failed to open configuration: {e}", 'error')

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
                debug_print("No photoframe instance to reload config")
        except Exception as e:
            debug_print(f"Error reloading config: {e}", 'error')

    def switch_to_default_folder(self, icon=None, item=None):
        """Ustaw folder domyslny biezacej orientacji jako aktywny (podwojny klik)."""
        try:
            if not self.photoframe:
                debug_print("No photoframe instance available")
                return
            
            # Check if lock is active - if yes, exit
            if self.photoframe._reload_lock:
                debug_print("⏱️ Reload already in progress, ignoring click")
                return
            
            # Set lock to block slideshow loop
            self.photoframe._reload_lock = True
            debug_print("🔒 Lock set - blocking slideshow loop")
            
            try:
                config = self.photoframe.load_config()
                values = settings(config)
                portrait = bool(values['orientation_portrait'])
                orientation = 'portrait' if portrait else 'landscape'

                default_key = f'default_{orientation}_folder'
                active_key = f'active_{orientation}_folder'
                default_folder = values[default_key]

                if not default_folder:
                    debug_print(f"Brak folderu domyslnego w konfiguracji ({default_key})", 'error')
                    return

                if not os.path.isdir(default_folder):
                    debug_print(f"Folder domyslny nie istnieje: {default_folder}", 'error')
                    return

                if values[active_key] == default_folder:
                    debug_print(f"Folder domyslny ({orientation}) jest juz aktywny: {default_folder}")
                    return

                debug_print(f"🔄 Przelaczam na folder domyslny ({orientation}): {default_folder}")

                config.setdefault(SECTION, {})[active_key] = default_folder

                from lib.config_manager import config_manager
                if config_manager.save_config(config):
                    debug_print("✅ Config saved with default folder")
                else:
                    debug_print("❌ Failed to save config", 'error')
                    return
                
                # Update photoframe's in-memory config
                self.photoframe.config = config
                
                # Reload images from location in config (use current config, already set above)
                if self.photoframe.running:
                    self.photoframe.current_images = self.photoframe.load_images(use_current_config=True)
                    self.photoframe.current_index = 0
                    # Load first image immediately
                    self.photoframe.show_current_image_now()
                    debug_print(f"✅ Loaded {len(self.photoframe.current_images)} images from default folder")
                    
            finally:
                # Release lock after 1 second
                def release_lock():
                    time.sleep(1.0)
                    self.photoframe._reload_lock = False
                    debug_print("🔓 Lock released after 1 second")
                
                threading.Thread(target=release_lock, daemon=True).start()
            
        except Exception as e:
            debug_print(f"❌ Error switching to default folder: {e}", 'error')
            debug_print(f"❌ Error: {e}", 'error')
            # Ensure lock is released on error
            if self.photoframe:
                self.photoframe._reload_lock = False
    
    def start_slideshow(self):
        """Start the photo slideshow"""
        if not self.photoframe:
            debug_print("❌ No photoframe instance available", 'error')
            return False
        if not self.photoframe.start_slideshow():
            debug_print("❌ Failed to start slideshow", 'error')
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
        debug_print(f"📡 Received signal {signum}")
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

        # Watek pilnujacy zmian config.yaml (edytor konfiguracji)
        self._note_config_written()
        threading.Thread(target=self._config_watcher, name='config-watcher',
                         daemon=True).start()

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
            debug_print("\n⌨️  Keyboard interrupt received")
            self.shutdown()

        return True

    def _setup_tray(self):
        """Create and start the tray icon (best-effort)."""
        try:
            # Ensure pystray and PIL Image are available
            if 'pystray' not in globals() or 'Image' not in globals():
                debug_print("⚠️  pystray or PIL not available; skipping tray icon", 'error')
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
                    debug_print(f"⚠️  Failed to create tray icon object: {e} / {e2}", 'error')
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
                debug_print(f"⚠️  Tray icon run failed: {e}", 'error')
        except Exception as e:
            debug_print(f"⚠️  Tray icon setup failed: {e}", 'error')


def main():
    """Main entry point"""
    if '--config' in sys.argv[1:]:
        # Tryb edytora konfiguracji - swiadomie bez blokady pojedynczej
        # instancji, bo trzyma ja dzialajaca aplikacja glowna.
        from lib.config_editor import main as run_config_editor
        return run_config_editor() == 0

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