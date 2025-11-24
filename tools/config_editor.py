#!/usr/bin/env python3
"""
Simple Photo Frame configuration editor for PhotoFrame-Clean.
Provides the Photo Frame Configuration section:
- Portrait photos folder (entry + browse + recent history)
- Landscape photos folder (entry + browse + recent history)
- Orientation (Portrait/Landscape) + Rotate 180°
- Change interval (sec)
- Random order, Maintain aspect ratio
- Save & Run (writes config.yaml and launches main.py)
- Exit App

Uses tkinter and PyYAML (already in requirements.txt).
"""
from __future__ import annotations
import os
import sys
import glob
import subprocess
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import yaml
from pathlib import Path

MAIN_DIR = Path(__file__).resolve().parents[1]
TOOLS_DIR = Path(__file__).resolve().parent
CONFIG_PATH = TOOLS_DIR / "config.yaml"
PORTRAIT_HISTORY = TOOLS_DIR / "portrait_folders_history.txt"
LANDSCAPE_HISTORY = TOOLS_DIR / "landscape_folders_history.txt"
HISTORY_LIMIT = 5


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
        self.window.geometry("560x360")
        self.window.resizable(False, False)

        # Widgets
        y = 10
        ttk.Label(self.window, text="Photo Frame Configuration", font=(None, 12, "bold")).place(x=10, y=y)

        y += 30
        ttk.Label(self.window, text="Portrait photos").place(x=10, y=y)
        self.portrait_entry = ttk.Entry(self.window)
        self.portrait_entry.place(x=140, y=y, width=360)
        self.portrait_btn = ttk.Button(self.window, text="...", width=3, command=self.browse_portrait)
        self.portrait_btn.place(x=510, y=y)

        y += 36
        ttk.Label(self.window, text="Landscape photos").place(x=10, y=y)
        self.landscape_entry = ttk.Entry(self.window)
        self.landscape_entry.place(x=140, y=y, width=360)
        self.landscape_btn = ttk.Button(self.window, text="...", width=3, command=self.browse_landscape)
        self.landscape_btn.place(x=510, y=y)

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
        # Replace spinbox with a slider from 5 to 300 seconds
        self.interval_var = tk.IntVar(value=10)
        self.interval_scale = ttk.Scale(self.window, from_=5, to=300, orient='horizontal', command=lambda v: self.interval_var.set(int(float(v))))
        self.interval_scale.place(x=200, y=y, width=260)
        # Show current value label
        self.interval_value_label = ttk.Label(self.window, textvariable=self.interval_var)
        self.interval_value_label.place(x=470, y=y)

        y += 36
        self.random_var = tk.BooleanVar()
        self.random_check = ttk.Checkbutton(self.window, text="Random order", variable=self.random_var)
        self.random_check.place(x=10, y=y)
        self.aspect_var = tk.BooleanVar(value=True)
        self.aspect_check = ttk.Checkbutton(self.window, text="Maintain aspect ratio", variable=self.aspect_var)
        self.aspect_check.place(x=180, y=y)

        # Buttons
        self.save_btn = ttk.Button(self.window, text="Save", command=self.on_save_run)
        self.save_btn.place(x=120, y=300, width=140, height=40)
        self.exit_btn = ttk.Button(self.window, text="Exit App", command=self.on_exit)
        self.exit_btn.place(x=300, y=300, width=140, height=40)

        # Load config and histories
        self.portrait_history = load_history(PORTRAIT_HISTORY)
        self.landscape_history = load_history(LANDSCAPE_HISTORY)
        self.load_config()

        # Bind right-click on browse buttons to show history
        self.portrait_btn.bind("<Button-3>", lambda e: self.show_portrait_history_menu(e))
        self.landscape_btn.bind("<Button-3>", lambda e: self.show_landscape_history_menu(e))

    def load_config(self):
        if CONFIG_PATH.exists():
            try:
                with CONFIG_PATH.open("r", encoding="utf-8") as f:
                    data = yaml.safe_load(f) or {}
                cfg = data.get('config', {})
                self.portrait_entry.delete(0, tk.END)
                self.portrait_entry.insert(0, cfg.get('PHOTO_FRAME_FOLDER_PORTRAIT', cfg.get('PHOTO_FRAME_FOLDER', '')))
                self.landscape_entry.delete(0, tk.END)
                self.landscape_entry.insert(0, cfg.get('PHOTO_FRAME_FOLDER_LANDSCAPE', cfg.get('PHOTO_FRAME_FOLDER', '')))
                # Orientation: set toggle text accordingly
                orientation_val = cfg.get('PHOTO_FRAME_ORIENTATION', cfg.get('orientation', 'Portrait'))
                orientation_val = str(orientation_val).capitalize()
                self.orientation_var.set(orientation_val)
                try:
                    self.orientation_toggle.config(text=orientation_val)
                except Exception:
                    pass
                self.rotate_var.set(cfg.get('PHOTO_FRAME_INVERSE', False))
                # no per-angle setting to load
                # interval: if photos.slideshow_interval exists prefer that
                interval_val = cfg.get('PHOTO_FRAME_INTERVAL', cfg.get('PHOTO_FRAME_INTERVAL', 10))
                # Also check photos section
                photos = data.get('photos', {})
                if 'slideshow_interval' in photos:
                    interval_val = photos.get('slideshow_interval')
                try:
                    interval_val = int(interval_val)
                except Exception:
                    interval_val = 10
                self.interval_var.set(interval_val)
                try:
                    self.interval_scale.set(interval_val)
                except Exception:
                    pass
                self.random_var.set(cfg.get('PHOTO_FRAME_RANDOM', False))
                self.aspect_var.set(cfg.get('PHOTO_FRAME_MAINTAIN_ASPECT_RATIO', True))
            except Exception as e:
                print(f"Error loading config: {e}")

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
        folder = filedialog.askdirectory(initialdir=self.portrait_entry.get() or os.path.expanduser("~"))
        if folder:
            self.select_portrait(folder)

    def browse_landscape(self):
        folder = filedialog.askdirectory(initialdir=self.landscape_entry.get() or os.path.expanduser("~"))
        if folder:
            self.select_landscape(folder)

    def select_portrait(self, folder):
        if folder and os.path.exists(folder):
            self.portrait_entry.delete(0, tk.END)
            self.portrait_entry.insert(0, folder)
            # update history
            if folder in self.portrait_history:
                self.portrait_history.remove(folder)
            self.portrait_history.append(folder)
            save_history(PORTRAIT_HISTORY, self.portrait_history)

    def select_landscape(self, folder):
        if folder and os.path.exists(folder):
            self.landscape_entry.delete(0, tk.END)
            self.landscape_entry.insert(0, folder)
            if folder in self.landscape_history:
                self.landscape_history.remove(folder)
            self.landscape_history.append(folder)
            save_history(LANDSCAPE_HISTORY, self.landscape_history)

    def on_save_run(self):
        # Build config structure
        cfg = {}
        if CONFIG_PATH.exists():
            try:
                with CONFIG_PATH.open("r", encoding="utf-8") as f:
                    cfg = yaml.safe_load(f) or {}
            except Exception:
                cfg = {}
        # Ensure both 'config' and 'photos' sections are present
        if 'config' not in cfg:
            cfg['config'] = {}
        if 'photos' not in cfg:
            cfg['photos'] = {}

        # Save config-level flags
        cfg['config']['MODE'] = 'PICTURE_FRAME'
        cfg['config']['PHOTO_FRAME_INVERSE'] = bool(self.rotate_var.get())

        # Save photos section used by PhotoFrame
        cfg['photos']['portrait_folder'] = self.portrait_entry.get()
        cfg['photos']['landscape_folder'] = self.landscape_entry.get()
        cfg['photos']['orientation'] = self.orientation_var.get().lower()
        # no per-angle setting saved
        try:
            cfg['photos']['slideshow_interval'] = int(self.interval_var.get())
        except Exception:
            cfg['photos']['slideshow_interval'] = 10

        # Keep backwards-compatible config keys too
        cfg['config']['PHOTO_FRAME_FOLDER_PORTRAIT'] = self.portrait_entry.get()
        cfg['config']['PHOTO_FRAME_FOLDER_LANDSCAPE'] = self.landscape_entry.get()
        cfg['config']['PHOTO_FRAME_ORIENTATION'] = self.orientation_var.get()
        cfg['config']['PHOTO_FRAME_INTERVAL'] = cfg['photos']['slideshow_interval']
        cfg['config']['PHOTO_FRAME_RANDOM'] = bool(self.random_var.get())
        cfg['config']['PHOTO_FRAME_MAINTAIN_ASPECT_RATIO'] = bool(self.aspect_var.get())

        try:
            with CONFIG_PATH.open("w", encoding="utf-8") as f:
                yaml.safe_dump(cfg, f, sort_keys=False)
        except Exception as e:
            messagebox.showerror("Error", f"Could not save config.yaml: {e}")
            return

        # Do not launch the application; only save config and close the editor.
        # The running application is expected to reload config or be restarted separately.
        self.window.destroy()

    def on_exit(self):
        # Try to terminate parent process if possible (same behavior as 3.5inch's configure)
        try:
            import os as _os, signal as _signal
            if hasattr(_os, 'getppid'):
                parent_pid = _os.getppid()
                _os.kill(parent_pid, _signal.SIGTERM)
        except Exception:
            pass
        self.window.destroy()

    def run(self):
        self.window.mainloop()


if __name__ == '__main__':
    editor = ConfigEditor()
    editor.run()
