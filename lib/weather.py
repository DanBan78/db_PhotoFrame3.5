"""Temperatura z Open-Meteo dla lokalizacji podanej w konfiguracji.

Open-Meteo nie wymaga rejestracji ani klucza API. Odpytujemy je rzadko
(domyslnie raz na 30 minut) i trzymamy ostatni odczyt w pamieci, zeby
wyswietlanie zdjecia nigdy nie czekalo na siec.
"""

import json
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

from .debug_utils import debug_print

API_URL = 'https://api.open-meteo.com/v1/forecast'
REFRESH_SECONDS = 30 * 60
REQUEST_TIMEOUT = 8
RETRY_SECONDS = 5 * 60      # po nieudanej probie nie zasypujemy serwera


class WeatherProvider:
    """Ostatnia znana temperatura, odswiezana w tle."""

    def __init__(self, refresh_seconds=REFRESH_SECONDS):
        self.refresh_seconds = refresh_seconds
        self._lock = threading.Lock()
        self._temperature = None      # float albo None, gdy nigdy sie nie udalo
        self._fetched_at = 0.0
        self._next_attempt = 0.0
        self._coords = None
        self._fetching = False

    def set_location(self, latitude, longitude):
        """Ustaw lokalizacje; zmiana wspolrzednych uniewaznia odczyt."""
        try:
            coords = (round(float(latitude), 4), round(float(longitude), 4))
        except (TypeError, ValueError):
            coords = None

        with self._lock:
            if coords != self._coords:
                self._coords = coords
                self._temperature = None
                self._fetched_at = 0.0
                self._next_attempt = 0.0

    def get_temperature(self):
        """Ostatnia znana temperatura w stopniach Celsjusza albo None.

        Nigdy nie blokuje - jesli dane sa nieaktualne, odswiezanie startuje
        w tle i wynik pojawi sie przy kolejnym zdjeciu.
        """
        with self._lock:
            coords = self._coords
            stale = time.time() - self._fetched_at > self.refresh_seconds
            can_try = time.time() >= self._next_attempt and not self._fetching
            if coords and stale and can_try:
                self._fetching = True
                threading.Thread(target=self._refresh, args=(coords,),
                                 name='weather', daemon=True).start()
            return self._temperature

    def _refresh(self, coords):
        temperature = self._fetch(*coords)
        with self._lock:
            self._fetching = False
            if temperature is None:
                self._next_attempt = time.time() + RETRY_SECONDS
            else:
                self._temperature = temperature
                self._fetched_at = time.time()
                self._next_attempt = 0.0

    @staticmethod
    def _fetch(latitude, longitude):
        """Pobierz biezaca temperature; None gdy sie nie udalo."""
        query = urllib.parse.urlencode({
            'latitude': latitude,
            'longitude': longitude,
            'current': 'temperature_2m',
            'timezone': 'auto',
        })
        url = f'{API_URL}?{query}'
        try:
            request = urllib.request.Request(url, headers={'User-Agent': 'PhotoFrame/1.0'})
            with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT) as response:
                payload = json.loads(response.read().decode('utf-8'))
            temperature = payload['current']['temperature_2m']
            debug_print(f"🌡️ Temperatura {temperature}°C dla {latitude},{longitude}")
            return float(temperature)
        except (urllib.error.URLError, OSError) as e:
            debug_print(f"Nie udalo sie pobrac temperatury: {e}", 'error')
        except (KeyError, ValueError, TypeError) as e:
            debug_print(f"Nieoczekiwana odpowiedz serwisu pogodowego: {e}", 'error')
        return None


def format_temperature(temperature):
    """Tekst do wyswietlenia na zdjeciu, np. '21°C'."""
    if temperature is None:
        return ''
    return f"{round(float(temperature)):.0f}°C"


# Wspolna instancja dla calej aplikacji
weather = WeatherProvider()
