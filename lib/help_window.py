"""Okno pomocy - pokazuje README z opisem dzialania i opcji.

Uruchamiane jako osobny proces (`PhotoFrame.exe --help`), tak samo jak edytor
konfiguracji. Dzieki temu przewijanie i zamykanie okna nie blokuje watku pompy
komunikatow zasobnika systemowego.

Markdown jest zamieniany na czytelny tekst: znaczniki (gwiazdki, backticki,
linki) znikaja i staja sie stylem, a tabele dostaja prawdziwe ramki
z wyrownanymi kolumnami.
"""
from __future__ import annotations

import re
import sys
import textwrap

import tkinter as tk
from tkinter import ttk

from .paths import resource_path

README_NAME = 'README.md'

# Szerokosc tekstu w znakach - dobrana pod szerokosc okna i czcionke Consolas
TEXT_WIDTH = 96

BRAK_PLIKU = (
    "Nie znaleziono pliku README.md.\n\n"
    "W wersji skompilowanej plik jest dolaczany do paczki - jesli go brakuje, "
    "zbuduj aplikacje ponownie poleceniem:\n\n"
    "    pyinstaller PhotoFrame.spec --noconfirm\n"
)


def read_readme():
    """Wczytaj tresc README z paczki albo z katalogu projektu."""
    try:
        return resource_path(README_NAME).read_text(encoding='utf-8')
    except OSError:
        return BRAK_PLIKU


def strip_markup(text):
    """Usun znaczniki Markdown, zostawiajac sam tekst."""
    text = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'\1 (\2)', text)   # linki
    text = re.sub(r'\*\*([^*]+)\*\*', r'\1', text)                # pogrubienie
    text = re.sub(r'`([^`]+)`', r'\1', text)                      # kod w linii
    return text


def split_row(line):
    """Podziel wiersz tabeli Markdown na komorki."""
    return [strip_markup(c).strip() for c in line.strip().strip('|').split('|')]


def is_separator(line):
    """Czy to wiersz oddzielajacy naglowek tabeli (| --- | --- |)."""
    cells = split_row(line)
    return bool(cells) and all(set(c) <= set('-: ') and '-' in c for c in cells)


def format_table(rows, total_width=TEXT_WIDTH):
    """Zamien wiersze tabeli na tekst z ramkami i wyrownanymi kolumnami."""
    if not rows:
        return []

    columns = max(len(r) for r in rows)
    rows = [r + [''] * (columns - len(r)) for r in rows]

    # Ramka zjada: 1 znak na kazdej krawedzi + ' | ' miedzy kolumnami
    available = total_width - (3 * columns + 1)
    natural = [max(len(r[i]) for r in rows) for i in range(columns)]

    widths = list(natural)
    while sum(widths) > available:
        widest = widths.index(max(widths))
        widths[widest] -= 1
        if widths[widest] < 6:      # nie zwezamy w nieskonczonosc
            break

    def line(left, fill, middle, right):
        return left + middle.join(fill * (w + 2) for w in widths) + right

    out = [line('┌', '─', '┬', '┐')]
    for index, row in enumerate(rows):
        # Kazda komorka moze zajac kilka linii - wiersz ma wysokosc najwyzszej
        wrapped = [textwrap.wrap(cell, widths[i]) or [''] for i, cell in enumerate(row)]
        height = max(len(w) for w in wrapped)
        for level in range(height):
            cells = []
            for i in range(columns):
                piece = wrapped[i][level] if level < len(wrapped[i]) else ''
                cells.append(' ' + piece.ljust(widths[i]) + ' ')
            out.append('│' + '│'.join(cells) + '│')
        # Kreska po KAZDYM wierszu, nie tylko po naglowku. Bez niej opis
        # zawiniety na kilka linii zlewa sie z kolejna pozycja tabeli.
        if index < len(rows) - 1:
            out.append(line('├', '─', '┼', '┤'))
    out.append(line('└', '─', '┴', '┘'))
    return out


class HelpWindow:
    def __init__(self, text=None):
        self.window = tk.Tk()
        self.window.title("Photo Frame - pomoc")

        width, height = 880, 660
        x = (self.window.winfo_screenwidth() - width) // 2
        y = max(0, (self.window.winfo_screenheight() - height) // 2 - 40)
        self.window.geometry(f"{width}x{height}+{x}+{y}")
        self.window.minsize(600, 400)

        frame = ttk.Frame(self.window, padding=(10, 10, 4, 10))
        frame.pack(fill='both', expand=True)

        scrollbar = ttk.Scrollbar(frame, orient='vertical')
        scrollbar.pack(side='right', fill='y')

        # wrap='none', bo zawijanie robimy sami - inaczej ramki tabel
        # rozjezdzalyby sie przy kazdym dluzszym wierszu
        self.text = tk.Text(frame, wrap='none', yscrollcommand=scrollbar.set,
                            font=("Consolas", 10), padx=14, pady=10,
                            background='#ffffff', relief='flat', borderwidth=0,
                            cursor='arrow')
        self.text.pack(side='left', fill='both', expand=True)
        scrollbar.config(command=self.text.yview)

        self._configure_tags()
        self._render(text if text is not None else read_readme())
        self.text.configure(state='disabled')

        self.window.bind('<Escape>', lambda e: self.window.destroy())
        self.window.bind('q', lambda e: self.window.destroy())
        self.text.bind('<MouseWheel>',
                       lambda e: self.text.yview_scroll(-e.delta // 120, 'units'))

        try:
            self.window.lift()
            self.window.focus_force()
        except Exception:
            pass

    def _configure_tags(self):
        self.text.tag_configure('h1', font=("Segoe UI", 16, "bold"),
                                spacing1=10, spacing3=10, foreground='#1a1a1a')
        self.text.tag_configure('h2', font=("Segoe UI", 12, "bold"),
                                spacing1=16, spacing3=6, foreground='#0a4a7d')
        self.text.tag_configure('code', font=("Consolas", 10), background='#f4f4f4',
                                lmargin1=24, lmargin2=24)
        # Rozmiar 10, nie 9: przy 9 punktach glify ramek nie stykaja sie ze soba
        # i pozioma linia wyglada na przerywana.
        self.text.tag_configure('table', font=("Consolas", 10), foreground='#222222')
        self.text.tag_configure('bullet', lmargin1=18, lmargin2=38)

    def _render(self, content):
        lines = content.split('\n')
        index = 0
        w_kodzie = False

        while index < len(lines):
            line = lines[index]
            stripped = line.strip()

            if stripped.startswith('```'):
                w_kodzie = not w_kodzie
                index += 1
                continue

            if w_kodzie:
                self.text.insert('end', '    ' + line + '\n', 'code')
                index += 1
                continue

            # Tabela: zbieramy wszystkie kolejne wiersze zaczynajace sie od |
            if stripped.startswith('|'):
                rows = []
                while index < len(lines) and lines[index].strip().startswith('|'):
                    if not is_separator(lines[index]):
                        rows.append(split_row(lines[index]))
                    index += 1
                for row in format_table(rows):
                    self.text.insert('end', row + '\n', 'table')
                self.text.insert('end', '\n')
                continue

            if line.startswith('# '):
                self.text.insert('end', strip_markup(line[2:]) + '\n', 'h1')
            elif line.startswith('## '):
                self.text.insert('end', strip_markup(line[3:]) + '\n', 'h2')
            elif stripped.startswith(('- ', '* ')):
                marker = '  • '
                body = strip_markup(stripped[2:])
                wrapped = textwrap.fill(body, TEXT_WIDTH - 4,
                                        initial_indent=marker, subsequent_indent='    ')
                self.text.insert('end', wrapped + '\n', 'bullet')
            elif not stripped:
                self.text.insert('end', '\n')
            else:
                body = strip_markup(stripped)
                self.text.insert('end', textwrap.fill(body, TEXT_WIDTH) + '\n')

            index += 1

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
