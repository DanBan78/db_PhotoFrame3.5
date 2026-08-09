#!/usr/bin/env python3
"""Zgodnosciowy launcher edytora konfiguracji.

Wlasciwa implementacja mieszka w lib/config_editor.py, dzieki czemu trafia
do paczki EXE i jest uruchamiana przez `PhotoFrame.exe --config`.
Ten plik zostaje tylko po to, zeby stare skroty do tools/config_editor.py
nadal dzialaly przy uruchomieniu ze zrodel.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lib.config_editor import main  # noqa: E402

if __name__ == '__main__':
    sys.exit(main())
