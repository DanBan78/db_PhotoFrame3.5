"""Prosta blokada międzyprocesowa oparta na pliku.

Konfigurację czyta pętla pokazu slajdów, zapisuje ją zasobnik systemowy oraz
edytor konfiguracji - potencjalnie z trzech różnych procesów. Bez blokady
zdarzało się, że dwa zapisy nakładały się na siebie i config.yaml stawał się
niepoprawnym YAML-em (a aplikacja po cichu wracała do pustej konfiguracji).
"""

import os
import time
from contextlib import contextmanager

if os.name == 'nt':
    import msvcrt

    def _try_lock(handle) -> bool:
        try:
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            return True
        except OSError:
            return False

    def _unlock(handle):
        try:
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        except OSError:
            pass
else:  # pragma: no cover - aplikacja jest przeznaczona na Windows
    import fcntl

    def _try_lock(handle) -> bool:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            return True
        except OSError:
            return False

    def _unlock(handle):
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        except OSError:
            pass


@contextmanager
def file_lock(lock_path, timeout=5.0, poll_interval=0.05):
    """Wyłączny dostęp do zasobu opisanego plikiem *lock_path*.

    Po przekroczeniu *timeout* blok wykonuje się mimo braku blokady - lepiej
    zaryzykować zapis niż zawiesić pokaz slajdów na stałe.
    """
    lock_path = str(lock_path)
    try:
        os.makedirs(os.path.dirname(lock_path), exist_ok=True)
    except OSError:
        pass

    handle = None
    acquired = False
    try:
        try:
            handle = open(lock_path, 'a+b')
        except OSError:
            handle = None

        if handle is not None:
            deadline = time.monotonic() + timeout
            while True:
                handle.seek(0)
                if _try_lock(handle):
                    acquired = True
                    break
                if time.monotonic() >= deadline:
                    break
                time.sleep(poll_interval)

        yield acquired
    finally:
        if handle is not None:
            if acquired:
                _unlock(handle)
            try:
                handle.close()
            except OSError:
                pass
