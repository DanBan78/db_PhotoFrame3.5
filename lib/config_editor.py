#!/usr/bin/env python3
"""Edytor konfiguracji Photo Frame.

Moduł jest częścią pakietu (a nie luźnym skryptem w tools/), dzięki czemu
trafia do paczki EXE i można go uruchomić przez `PhotoFrame.exe --config`.
Wcześniej aplikacja próbowała odpalić `subprocess.Popen([sys.executable,
'tools/config_editor.py'])`; w wersji zamrożonej sys.executable to sam
PhotoFrame.exe, więc zamiast edytora startowała druga kopia aplikacji -
a ścieżka do skryptu i tak nie istniała, więc menu nie robiło nic.

Sekcja Photo Frame Configuration:
- folder zdjęć pionowych / poziomych (wybór + historia)
- orientacja (Portrait/Landscape) + obrót 180°
- interwał zmiany zdjęcia
- kolejność losowa, zachowanie proporcji, zegar
"""
from __future__ import annotations

import math
import os
import sys
from pathlib import Path

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import yaml

from .config_manager import ConfigManager, settings, SECTION, SCALE_MODES
from .paths import (
    config_path,
    portrait_history_path,
    landscape_history_path,
    ensure_tools_dir,
)

# Debug configuration
DEBUG_ENABLED = True

CONFIG_PATH = config_path()
PORTRAIT_HISTORY = portrait_history_path()
LANDSCAPE_HISTORY = landscape_history_path()
HISTORY_LIMIT = 5

# Opisy trybow skalowania widoczne w oknie
SCALE_MODE_LABELS = {
    'fit': "Dopasuj (czarne pasy)",
    'fill': "Wypelnij ekran (przytnij)",
}

# Suwak interwalu: skok co 4 sekundy
INTERVAL_MIN = 4
INTERVAL_MAX = 300
INTERVAL_STEP = 4


def snap_interval(value):
    """Zaokraglij interwal do najblizszej wielokrotnosci INTERVAL_STEP.

    Zaokraglamy do NAJBLIZSZEJ, nie w dol - wczesniej wartosc 11 zamieniala sie
    przy zapisie na 8 zamiast na 12. Polowki ida w gore (26 -> 28); wbudowane
    round() zaokragla je do parzystej wielokrotnosci, wiec dawalo 26 -> 24.
    """
    try:
        snapped = math.floor(float(value) / INTERVAL_STEP + 0.5) * INTERVAL_STEP
    except (TypeError, ValueError):
        snapped = INTERVAL_MIN
    return max(INTERVAL_MIN, min(INTERVAL_MAX, int(snapped)))

# Wlasna instancja - zapis idzie przez ten sam atomowy mechanizm z blokada
# miedzyprocesowa, ktorego uzywa glowna aplikacja.
_config_manager = ConfigManager(str(CONFIG_PATH))


def load_debug_config():
    """Load debug settings from config file"""
    global DEBUG_ENABLED
    try:
        if CONFIG_PATH.exists():
            with CONFIG_PATH.open("r", encoding="utf-8") as f:
                config = yaml.safe_load(f) or {}
            DEBUG_ENABLED = settings(config)['debug_enabled']
    except Exception:
        pass


def debug_print(message, level='info'):
    """Print debug message if debug is enabled"""
    if DEBUG_ENABLED and level in ['info', 'debug', 'error']:
        try:
            print(message)
        except Exception:
            pass


load_debug_config()


def load_history(path: Path) -> list[str]:
    try:
        if path.exists():
            with path.open("r", encoding="utf-8") as f:
                return [line.strip() for line in f.readlines() if line.strip()]
    except Exception:
        pass
    return []


def save_history(path: Path, entries: list[str]):
    try:
        ensure_tools_dir()
        # Keep unique, last-most-recent at end
        unique = []
        for e in reversed(entries):
            if e not in unique:
                unique.append(e)
        unique = list(reversed(unique))[:HISTORY_LIMIT]
        with path.open("w", encoding="utf-8") as f:
            for e in unique:
                f.write(e + "\n")
    except Exception:
        pass


class ConfigEditor:
    def __init__(self):
        self.window = tk.Tk()
        self.window.title("Photo Frame Configuration")

        # Set window size
        window_width = 700
        window_height = 340

        # Get screen dimensions
        screen_width = self.window.winfo_screenwidth()
        screen_height = self.window.winfo_screenheight()

        # Calculate position for bottom-right corner (above taskbar)
        # Taskbar is typically 40-50 pixels, so we add some margin
        taskbar_height = 50
        margin = 10

        x_position = screen_width - window_width - margin
        y_position = screen_height - window_height - taskbar_height - margin - 50

        # Set geometry with position
        self.window.geometry(f"{window_width}x{window_height}+{x_position}+{y_position}")
        self.window.resizable(False, False)

        # Okno ma sie pokazac na wierzchu - uruchamiamy je z zasobnika,
        # wiec latwo bylo je przeoczyc za innymi oknami.
        try:
            self.window.attributes('-topmost', True)
            self.window.after(500, lambda: self.window.attributes('-topmost', False))
            self.window.lift()
            self.window.focus_force()
        except Exception:
            pass

        # Chroni przed rekurencja, gdy sami przestawiamy suwak na wartosc ze skoku
        self._interval_snapping = False

        # Load history first
        self.portrait_history = load_history(PORTRAIT_HISTORY)
        self.landscape_history = load_history(LANDSCAPE_HISTORY)

        # Widgets
        y = 10
        ttk.Label(self.window, text="Photo Frame Configuration", font=("Arial", 12, "bold")).place(x=10, y=y)

        y += 30
        ttk.Label(self.window, text="Portrait photos").place(x=10, y=y)
        self.portrait_dropdown_var = tk.StringVar()
        self.portrait_dropdown = ttk.Combobox(self.window, textvariable=self.portrait_dropdown_var, values=self.portrait_history, state="readonly")
        self.portrait_dropdown.place(x=140, y=y, width=420)
        self.portrait_btn = ttk.Button(self.window, text="...", width=3, command=self.browse_portrait)
        self.portrait_btn.place(x=570, y=y)
        # Button to set portrait as default
        self.portrait_set_btn = ttk.Button(self.window, text="SET", width=5, command=self.set_portrait_as_default)
        self.portrait_set_btn.place(x=610, y=y)
        self.portrait_default_label = ttk.Label(self.window, text="", foreground='#555555')
        self.portrait_default_label.place(x=140, y=y + 20, width=420)

        y += 36
        ttk.Label(self.window, text="Landscape photos").place(x=10, y=y)
        self.landscape_dropdown_var = tk.StringVar()
        self.landscape_dropdown = ttk.Combobox(self.window, textvariable=self.landscape_dropdown_var, values=self.landscape_history, state="readonly")
        self.landscape_dropdown.place(x=140, y=y, width=420)
        self.landscape_btn = ttk.Button(self.window, text="...", width=3, command=self.browse_landscape)
        self.landscape_btn.place(x=570, y=y)
        # Button to set landscape as default
        self.landscape_set_btn = ttk.Button(self.window, text="SET", width=5, command=self.set_landscape_as_default)
        self.landscape_set_btn.place(x=610, y=y)
        self.landscape_default_label = ttk.Label(self.window, text="", foreground='#555555')
        self.landscape_default_label.place(x=140, y=y + 20, width=420)

        y += 36
        ttk.Label(self.window, text="Frame orientation").place(x=10, y=y)
        # Replace combobox with a toggle button that switches between Portrait and Landscape
        self.orientation_var = tk.StringVar(value="Portrait")

        def _toggle_orientation():
            cur = self.orientation_var.get()
            nxt = "Landscape" if cur == "Portrait" else "Portrait"
            self.orientation_var.set(nxt)
            self.orientation_toggle.config(text=nxt)

        self.orientation_toggle = ttk.Button(self.window, text=self.orientation_var.get(), command=_toggle_orientation)
        self.orientation_toggle.place(x=140, y=y, width=160)
        self.rotate_var = tk.BooleanVar()
        self.rotate_check = ttk.Checkbutton(self.window, text="Rotate 180°", variable=self.rotate_var)
        self.rotate_check.place(x=320, y=y)

        # (no extra rotate angle configuration)

        y += 36
        ttk.Label(self.window, text="Change interval (sec)").place(x=10, y=y)
        # Replace spinbox with a slider from 4 to 300 seconds with 4-second steps
        self.interval_var = tk.IntVar(value=12)
        self.interval_scale = ttk.Scale(self.window, from_=INTERVAL_MIN, to=INTERVAL_MAX,
                                        orient='horizontal', command=self._on_interval_move)
        self.interval_scale.place(x=140, y=y, width=520)
        # Show current value label
        self.interval_value_label = ttk.Label(self.window, textvariable=self.interval_var)
        self.interval_value_label.place(x=670, y=y)

        y += 36
        self.random_var = tk.BooleanVar()
        self.random_check = ttk.Checkbutton(self.window, text="Random order", variable=self.random_var)
        self.random_check.place(x=10, y=y)

        # Skalowanie: fit = cale zdjecie + czarne pasy, fill = wypelnij ekran i przytnij
        self.scale_mode_var = tk.StringVar(value='fit')

        def _toggle_scale_mode():
            index = SCALE_MODES.index(self.scale_mode_var.get()) if self.scale_mode_var.get() in SCALE_MODES else 0
            nxt = SCALE_MODES[(index + 1) % len(SCALE_MODES)]
            self.scale_mode_var.set(nxt)
            self.scale_mode_toggle.config(text=SCALE_MODE_LABELS[nxt])

        self.scale_mode_toggle = ttk.Button(self.window, text=SCALE_MODE_LABELS['fit'],
                                            command=_toggle_scale_mode)
        self.scale_mode_toggle.place(x=140, y=y - 3, width=250)
        # Add show_time checkbox
        self.show_time_var = tk.BooleanVar(value=True)
        self.show_time_check = ttk.Checkbutton(self.window, text="Show clock", variable=self.show_time_var)
        self.show_time_check.place(x=410, y=y)

        # Buttons
        y += 40
        self.save_btn = ttk.Button(self.window, text="Save", command=self.on_save_run)
        self.save_btn.place(x=540, y=y, width=140, height=60)

        # Potwierdzenie akcji - w wersji EXE nie ma konsoli, wiec komunikat
        # musi byc widoczny w oknie
        self.status_label = ttk.Label(self.window, text="", foreground='#0a7d28')
        self.status_label.place(x=10, y=y + 20, width=520)

        self.load_config()

        # Bind right-click on browse buttons to show history
        self.portrait_btn.bind("<Button-3>", lambda e: self.show_portrait_history_menu(e))
        self.landscape_btn.bind("<Button-3>", lambda e: self.show_landscape_history_menu(e))

    def _apply_default_folder(self, orientation, folder, history, history_file,
                              dropdown, dropdown_var):
        """Ustaw folder jako domyslny: historia + config.yaml, ze skutkiem od razu.

        Sam zapis historii nie wystarcza. Wczesniej SET przestawial tylko plik
        historii, wiec ramka dalej pokazywala stary folder, a klucz
        *_HISTORY_LINE w configu wskazywal po przesunieciu zupelnie inny wpis.
        """
        if not folder:
            self._set_status("Najpierw wybierz folder", error=True)
            return

        # Historia: wybrany folder na pierwsze miejsce
        if folder in history:
            history.remove(folder)
        history.insert(0, folder)
        dropdown.configure(values=history)
        save_history(history_file, history)
        dropdown_var.set(history[0])

        # Config: folder staje sie domyslny ORAZ aktywny, ramka przelacza sie od razu
        try:
            cfg = _config_manager.load_config(force_reload=True)
        except Exception:
            cfg = {}
        section = cfg.setdefault(SECTION, {})
        section[f'default_{orientation}_folder'] = folder
        section[f'active_{orientation}_folder'] = folder

        # Ramka ma pokazywac wlasnie ten folder, wiec ustawiamy tez orientacje
        section['orientation_portrait'] = (orientation == 'portrait')
        self.orientation_var.set(orientation.capitalize())
        try:
            self.orientation_toggle.config(text=orientation.capitalize())
        except Exception:
            pass

        if _config_manager.save_config(cfg):
            name = os.path.basename(folder.rstrip('/\\')) or folder
            self._set_status(f"Domyslny folder ({orientation}): {name}")
            debug_print(f"Set as default {orientation}: {folder}")
            self._refresh_default_labels(settings(cfg))
        else:
            self._set_status("Nie udalo sie zapisac konfiguracji", error=True)

    def _refresh_default_labels(self, cfg):
        """Pokaz przy kazdym polu, ktory folder jest obecnie domyslny."""
        for orientation, label in (('portrait', getattr(self, 'portrait_default_label', None)),
                                   ('landscape', getattr(self, 'landscape_default_label', None))):
            if label is None:
                continue
            folder = cfg.get(f'default_{orientation}_folder') or ''
            name = os.path.basename(str(folder).rstrip('/\\')) or '-'
            try:
                label.config(text=f"domyslny: {name}")
            except Exception:
                pass

    def set_portrait_as_default(self):
        """Set current portrait folder as default (move to first position in history)"""
        self._apply_default_folder(
            'portrait', self.portrait_dropdown_var.get(), self.portrait_history,
            PORTRAIT_HISTORY, self.portrait_dropdown, self.portrait_dropdown_var)

    def set_landscape_as_default(self):
        """Set current landscape folder as default (move to first position in history)"""
        self._apply_default_folder(
            'landscape', self.landscape_dropdown_var.get(), self.landscape_history,
            LANDSCAPE_HISTORY, self.landscape_dropdown, self.landscape_dropdown_var)

    def _on_interval_move(self, value):
        """Suwak interwalu porusza sie skokowo co INTERVAL_STEP sekund."""
        if self._interval_snapping:
            return

        snapped = snap_interval(value)
        self.interval_var.set(snapped)

        try:
            if abs(float(value) - snapped) > 0.01:
                # Przyciagnij tez sam suwak, zeby uchwyt stal na wartosci ze skoku
                self._interval_snapping = True
                try:
                    self.interval_scale.set(snapped)
                finally:
                    self._interval_snapping = False
        except (TypeError, ValueError):
            pass

    def _set_status(self, text, error=False):
        """Pokaz komunikat w oknie - w wersji EXE print nie ma gdzie trafic."""
        try:
            self.status_label.config(text=text, foreground='#b00020' if error else '#0a7d28')
        except Exception:
            pass

    def load_config(self):
        try:
            data = _config_manager.load_config(force_reload=True)
        except Exception as e:
            debug_print(f"Error loading config: {e}", 'error')
            return

        cfg = settings(data)

        # Pola pokazuja folder AKTYWNY; historia sluzy tylko jako podpowiedzi
        self.portrait_dropdown_var.set(
            cfg['active_portrait_folder'] or cfg['default_portrait_folder']
            or (self.portrait_history[0] if self.portrait_history else ''))
        self.landscape_dropdown_var.set(
            cfg['active_landscape_folder'] or cfg['default_landscape_folder']
            or (self.landscape_history[0] if self.landscape_history else ''))

        orientation_val = "Portrait" if cfg['orientation_portrait'] else "Landscape"
        self.orientation_var.set(orientation_val)
        try:
            self.orientation_toggle.config(text=orientation_val)
        except Exception:
            pass

        self.rotate_var.set(bool(cfg['inverse']))

        interval_val = snap_interval(cfg['interval'])
        self.interval_var.set(interval_val)
        try:
            self.interval_scale.set(interval_val)
        except Exception:
            pass

        self.random_var.set(bool(cfg['shuffle']))
        self.scale_mode_var.set(cfg['scale_mode'])
        try:
            self.scale_mode_toggle.config(text=SCALE_MODE_LABELS[cfg['scale_mode']])
        except Exception:
            pass
        self.show_time_var.set(bool(cfg['show_time']))
        self._refresh_default_labels(cfg)

    def show_portrait_history_menu(self, event):
        menu = tk.Menu(self.window, tearoff=0)
        menu.add_command(label="Browse for new folder...", command=self.browse_portrait)
        if self.portrait_history:
            menu.add_separator()
            for folder in reversed(self.portrait_history[-HISTORY_LIMIT:]):
                name = os.path.basename(folder) or folder
                menu.add_command(label=name, command=lambda f=folder: self.select_portrait(f))
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def show_landscape_history_menu(self, event):
        menu = tk.Menu(self.window, tearoff=0)
        menu.add_command(label="Browse for new folder...", command=self.browse_landscape)
        if self.landscape_history:
            menu.add_separator()
            for folder in reversed(self.landscape_history[-HISTORY_LIMIT:]):
                name = os.path.basename(folder) or folder
                menu.add_command(label=name, command=lambda f=folder: self.select_landscape(f))
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def browse_portrait(self):
        current = self.portrait_dropdown_var.get()
        folder = filedialog.askdirectory(initialdir=current or os.path.expanduser("~"))
        if folder:
            self.select_portrait(folder)

    def browse_landscape(self):
        current = self.landscape_dropdown_var.get()
        folder = filedialog.askdirectory(initialdir=current or os.path.expanduser("~"))
        if folder:
            self.select_landscape(folder)

    def select_portrait(self, folder):
        if folder and os.path.exists(folder):
            self.portrait_dropdown_var.set(folder)
            # update history
            if folder in self.portrait_history:
                self.portrait_history.remove(folder)
            self.portrait_history.append(folder)
            self.portrait_dropdown.configure(values=self.portrait_history)
            save_history(PORTRAIT_HISTORY, self.portrait_history)

    def select_landscape(self, folder):
        if folder and os.path.exists(folder):
            self.landscape_dropdown_var.set(folder)
            if folder in self.landscape_history:
                self.landscape_history.remove(folder)
            self.landscape_history.append(folder)
            self.landscape_dropdown.configure(values=self.landscape_history)
            save_history(LANDSCAPE_HISTORY, self.landscape_history)

    def on_save_run(self):
        # Build config structure na bazie aktualnego pliku
        try:
            cfg = _config_manager.load_config(force_reload=True)
        except Exception:
            cfg = {}

        section = cfg.setdefault(SECTION, {})

        # Wybrane w oknie foldery staja sie aktywne; domyslne zmienia tylko SET
        section['active_portrait_folder'] = self.portrait_dropdown_var.get()
        section['active_landscape_folder'] = self.landscape_dropdown_var.get()

        section['orientation_portrait'] = self.orientation_var.get().lower().startswith('p')
        section['inverse'] = bool(self.rotate_var.get())
        section['shuffle'] = bool(self.random_var.get())
        section['scale_mode'] = self.scale_mode_var.get()
        section['show_time'] = bool(self.show_time_var.get())
        section['interval'] = snap_interval(self.interval_var.get())

        # Zapis atomowy, pod blokada wspoldzielona z glowna aplikacja
        if not _config_manager.save_config(cfg):
            messagebox.showerror("Error", f"Could not save {CONFIG_PATH}")
            return

        debug_print("⚙️ Configuration saved successfully")

        # Close the editor after saving
        self.window.destroy()

    def run(self):
        self.window.mainloop()


def main() -> int:
    """Uruchom edytor konfiguracji. Zwraca kod wyjscia procesu."""
    try:
        ConfigEditor().run()
        return 0
    except tk.TclError as e:
        # Brak dostepnego srodowiska graficznego / uszkodzony Tcl w paczce
        sys.stderr.write(f"Nie mozna otworzyc edytora konfiguracji: {e}\n")
        return 1


if __name__ == '__main__':
    sys.exit(main())
