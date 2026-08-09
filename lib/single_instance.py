"""Gwarancja, że w systemie działa tylko jedna kopia PhotoFrame.

Druga instancja nie może otworzyć portu COM (PermissionError 13), ale zanim
się o tym przekona, zdąży odczytać i zapisać config.yaml - a przy równoległym
zapisie z pierwszą instancją potrafiła go uszkodzić. Prościej i bezpieczniej
jest nie dopuścić do drugiego startu.
"""

import os

from .debug_utils import debug_print
from .paths import app_dir

_DEFAULT_NAME = 'PhotoFrame-SingleInstance'


class SingleInstance:
    """Blokada trzymana przez cały czas życia procesu."""

    def __init__(self, name=_DEFAULT_NAME):
        self.name = name
        self._handle = None
        self._acquired = False

    def acquire(self) -> bool:
        """True gdy to jedyna instancja; False gdy aplikacja już działa."""
        if self._acquired:
            return True

        if os.name == 'nt':
            self._acquired = self._acquire_windows()
        else:  # pragma: no cover - aplikacja jest przeznaczona na Windows
            self._acquired = self._acquire_posix()
        return self._acquired

    def _acquire_windows(self) -> bool:
        import ctypes
        from ctypes import wintypes

        ERROR_ALREADY_EXISTS = 183

        kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel32.CreateMutexW.argtypes = [wintypes.LPCVOID, wintypes.BOOL, wintypes.LPCWSTR]
        kernel32.CreateMutexW.restype = wintypes.HANDLE

        # "Local\" = zasięg sesji użytkownika - dokładnie to, czego potrzebujemy
        # dla aplikacji zasobnika systemowego.
        handle = kernel32.CreateMutexW(None, False, f'Local\\{self.name}')
        last_error = ctypes.get_last_error()

        if not handle:
            debug_print(f"Nie udalo sie utworzyc mutexu instancji (kod {last_error})", 'error')
            return True  # nie blokujemy startu z powodu awarii samej blokady

        self._handle = handle
        if last_error == ERROR_ALREADY_EXISTS:
            self.release()
            return False
        return True

    def _acquire_posix(self) -> bool:  # pragma: no cover
        from .filelock import _try_lock

        lock_file = app_dir() / f'.{self.name}.lock'
        try:
            handle = open(lock_file, 'a+b')
        except OSError:
            return True

        if _try_lock(handle):
            self._handle = handle
            return True

        handle.close()
        return False

    def release(self):
        if self._handle is None:
            return
        try:
            if os.name == 'nt':
                import ctypes
                ctypes.WinDLL('kernel32').CloseHandle(self._handle)
            else:  # pragma: no cover
                self._handle.close()
        except Exception:
            pass
        finally:
            self._handle = None
            self._acquired = False

    def __enter__(self):
        return self.acquire()

    def __exit__(self, exc_type, exc, tb):
        self.release()
        return False
