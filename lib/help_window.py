"""Okno pomocy - pokazuje README z opisem dzialania i opcji.

Uruchamiane jako osobny proces (`PhotoFrame.exe --help`), tak samo jak edytor
konfiguracji. Dzieki temu przewijanie i zamykanie okna nie blokuje watku pompy
komunikatow zasobnika systemowego.
"""
from __future__ import annotations

import sys

import tkinter as tk
from tkinter import ttk

from .paths import resource_path

README_NAME = 'README.md'

BRAK_PLIKU = (
    "Nie znaleziono pliku README.md.\n\n"
    "W wersji skompilowanej plik jest dolaczany do paczki - jesli go brakuje, "
    "zbuduj aplikacje ponownie poleceniem:\n\n"
    "    pyinstaller PhotoFrame.spec --noconfirm\n"
)


def read_readme():
    """Wczytaj tresc README z paczki albo z katalogu projektu."""
    path = resource_path(README_NAME)
    try:
        return path.read_text(encoding='utf-8')
    except OSError:
        return BRAK_PLIKU


class HelpWindow:
    def __init__(self, text=None):
        self.window = tk.Tk()
        self.window.title("Photo Frame - pomoc")

        width, height = 860, 640
        x = (self.window.winfo_screenwidth() - width) // 2
        y = max(0, (self.window.winfo_screenheight() - height) // 2 - 40)
        self.window.geometry(f"{width}x{height}+{x}+{y}")
        self.window.minsize(600, 400)

        frame = ttk.Frame(self.window, padding=(10, 10, 4, 10))
        frame.pack(fill='both', expand=True)

        scrollbar = ttk.Scrollbar(frame, orient='vertical')
        scrollbar.pack(side='right', fill='y')

        self.text = tk.Text(frame, wrap='word', yscrollcommand=scrollbar.set,
                            font=("Consolas", 10), padx=12, pady=10,
                            background='#ffffff', relief='flat', borderwidth=0)
        self.text.pack(side='left', fill='both', expand=True)
        scrollbar.config(command=self.text.yview)

        self._configure_tags()
        self._insert(text if text is not None else read_readme())
        self.text.configure(state='disabled')

        # Wygodne zamykanie: Esc albo Q
        self.window.bind('<Escape>', lambda e: self.window.destroy())
        self.window.bind('q', lambda e: self.window.destroy())

        try:
            self.window.lift()
            self.window.focus_force()
        except Exception:
            pass

    def _configure_tags(self):
        self.text.tag_configure('h1', font=("Segoe UI", 15, "bold"),
                                spacing1=12, spacing3=8, foreground='#1a1a1a')
        self.text.tag_configure('h2', font=("Segoe UI", 12, "bold"),
                                spacing1=14, spacing3=6, foreground='#0a4a7d')
        self.text.tag_configure('code', font=("Consolas", 10),
                                background='#f2f2f2')
        self.text.tag_configure('table', font=("Consolas", 9))
        self.text.tag_configure('bullet', lmargin1=18, lmargin2=32)

    def _insert(self, content):
        """Wstaw tekst, wyrozniajac naglowki, listy, tabele i bloki kodu.

        To nie jest pelny renderer Markdown - chodzi tylko o to, zeby opis
        dalo sie wygodnie czytac w oknie.
        """
        w_kodzie = False
        for line in content.split('\n'):
            stripped = line.strip()

            if stripped.startswith('```'):
                w_kodzie = not w_kodzie
                continue

            if w_kodzie:
                self.text.insert('end', line + '\n', 'code')
            elif line.startswith('# '):
                self.text.insert('end', line[2:] + '\n', 'h1')
            elif line.startswith('## '):
                self.text.insert('end', line[3:] + '\n', 'h2')
            elif stripped.startswith('|'):
                self.text.insert('end', line + '\n', 'table')
            elif stripped.startswith(('- ', '* ')):
                self.text.insert('end', line + '\n', 'bullet')
            else:
                self.text.insert('end', line + '\n')

    def run(self):
        self.window.mainloop()


def main() -> int:
    """Pokaz okno pomocy. Zwraca kod wyjscia procesu."""
    try:
        HelpWindow().run()
        return 0
    except tk.TclError as e:
        sys.stderr.write(f"Nie mozna otworzyc okna pomocy: {e}\n")
        return 1


if __name__ == '__main__':
    sys.exit(main())
