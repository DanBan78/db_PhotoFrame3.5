# PhotoFrame

Cyfrowa ramka na zdjęcia dla wyświetlacza **Turing Smart Screen 3.5" Rev A**
(320 × 480, podłączany po USB). Aplikacja działa w tle, w zasobniku systemowym,
i wyświetla na ekranie zdjęcia ze wskazanego folderu — opcjonalnie z zegarem
i temperaturą dla wybranej lokalizacji.

## Obsługa z zasobnika systemowego

Ikona w zasobniku jest głównym sposobem sterowania:

| Akcja | Efekt |
| --- | --- |
| Pojedyncze kliknięcie | następne zdjęcie |
| Podwójne kliknięcie | powrót do folderu domyślnego |
| Prawy przycisk | menu: zmiana orientacji, konfiguracja, wyjście |

Pojedyncze i podwójne kliknięcie rozróżniane jest w oknie 400 ms — po pierwszym
kliknięciu aplikacja czeka tę chwilę, żeby sprawdzić, czy nie nadejdzie drugie.

## Folder domyślny, aktywny i historia

To trzy różne pojęcia i warto je rozdzielić:

- **Folder domyślny** (`default_portrait_folder`, `default_landscape_folder`) —
  punkt wyjścia. Ramka zaczyna od niego po każdym uruchomieniu i wraca do niego
  po podwójnym kliknięciu w ikonę. Ustawia się go przyciskiem **SET** w edytorze
  konfiguracji.
- **Folder aktywny** (`active_portrait_folder`, `active_landscape_folder`) —
  to, co jest wyświetlane w tej chwili. Zmienia go wybór folderu w edytorze
  i zapis przyciskiem **Save**. Nie przeżywa restartu aplikacji.
- **Historia** (`tools/portrait_folders_history.txt`,
  `tools/landscape_folders_history.txt`) — lista podpowiedzi w edytorze,
  maksymalnie **8 ostatnio wskazanych folderów**. Najnowszy wpis jest pierwszy,
  przy przepełnieniu wypada najstarszy. Historia nie ma wpływu na działanie
  ramki — folder domyślny zapisany jest w konfiguracji i może w historii
  w ogóle nie występować.

Osobna historia prowadzona jest dla orientacji pionowej i poziomej.

## Edytor konfiguracji

Otwiera się z menu ikony (**Open Configuration**) albo poleceniem
`PhotoFrame.exe --config`. Pola w oknie:

| Pole | Znaczenie |
| --- | --- |
| Portrait photos / Landscape photos | folder aktywny dla danej orientacji; `...` wskazuje nowy folder, `SET` czyni go domyślnym |
| Frame orientation | pion albo poziom — decyduje, z którego folderu lecą zdjęcia |
| Rotate 180° | obrót obrazu, gdy ramka wisi do góry nogami |
| Change interval | co ile sekund zmienia się zdjęcie (4–300 s, skok co 4 s) |
| Random order | kolejność losowa zamiast alfabetycznej |
| Dopasuj / Wypełnij ekran | tryb skalowania, patrz niżej |
| Show clock | zegar na zdjęciu |
| Temperatura + szer. / dł. | temperatura dla podanych współrzędnych |

Zmiany zapisane przyciskiem **Save** ramka podchwytuje w około sekundę — nie
trzeba jej restartować.

## Tryby skalowania

Proporcje zdjęcia są zachowane w obu trybach, obraz nigdy nie jest rozciągany:

- **fit** (Dopasuj) — całe zdjęcie mieści się na ekranie, wolne miejsce
  wypełniają czarne pasy.
- **fill** (Wypełnij ekran) — zdjęcie pokrywa cały ekran, nadmiar wychodzi poza
  kadr i zostaje przycięty, obraz jest wyśrodkowany.

## Zegar i temperatura

Oba napisy pojawiają się **2 sekundy po** wyświetleniu zdjęcia, żeby nie
zasłaniać kadru w momencie zmiany. Zegar ląduje w losowo wybranym rogu (nigdy
dwa razy z rzędu w tym samym), a temperatura w rogu po przekątnej.

Temperatura pochodzi z serwisu [Open-Meteo](https://open-meteo.com/), który nie
wymaga rejestracji ani klucza API. Odczyt odświeżany jest raz na 30 minut w tle,
więc wyświetlanie zdjęcia nigdy nie czeka na sieć. Gdy sieć nie odpowie, ramka
pokazuje ostatnią znaną wartość, a kolejną próbę podejmuje po 5 minutach.

Współrzędne można znaleźć w geokoderze Open-Meteo, na przykład:

```text
https://geocoding-api.open-meteo.com/v1/search?name=Gdansk&language=pl
```

## Plik konfiguracyjny

Konfiguracja leży w `tools/config.yaml`, obok pliku wykonywalnego, w jednej
płaskiej sekcji `photo_frame`. Starszy układ (sekcje `config`, `photos`,
`slideshow`, `display`, `debug`) jest przy pierwszym uruchomieniu automatycznie
przepisywany na nowy, a poprzednia wersja zostaje jako `config.yaml.backup`.

| Klucz | Domyślnie | Znaczenie |
| --- | --- | --- |
| `com_port` | `COM3` | port szeregowy wyświetlacza |
| `debug_enabled` | `true` | zapis komunikatów do `log.log` |
| `debug_level` | `info` | `info` lub `error` — przy `error` w logu lądują tylko błędy |
| `show_time` | `false` | zegar na zdjęciu |
| `show_temperature` | `false` | temperatura na zdjęciu |
| `latitude` | puste | szerokość geograficzna, np. `54.3556` |
| `longitude` | puste | długość geograficzna, np. `18.4910` |
| `brightness` | `85` | jasność podświetlenia, 0–100 |
| `interval` | `30` | sekundy między zdjęciami |
| `orientation_portrait` | `true` | `true` = pion, `false` = poziom |
| `scale_mode` | `fit` | `fit` albo `fill` |
| `inverse` | `false` | obrót obrazu o 180° |
| `shuffle` | `true` | kolejność losowa; `false` = alfabetyczna wg nazwy pliku |
| `default_portrait_folder` | puste | folder domyślny dla pionu |
| `default_landscape_folder` | puste | folder domyślny dla poziomu |
| `active_portrait_folder` | puste | folder aktualnie wyświetlany w pionie |
| `active_landscape_folder` | puste | folder aktualnie wyświetlany w poziomie |

Plik zapisywany jest atomowo i pod blokadą międzyprocesową, więc równoczesny
zapis z aplikacji i z edytora nie może go uszkodzić.

## Uruchamianie ze źródeł

```bash
python main.py              # normalne uruchomienie
python main.py --config     # sam edytor konfiguracji
```

## Budowanie pliku wykonywalnego

```bash
.venv\Scripts\pyinstaller.exe PhotoFrame.spec --noconfirm
```

Wynik trafia do `dist/PhotoFrame`. Do katalogu z `PhotoFrame.exe` trzeba
dołożyć podkatalog `tools` z plikiem `config.yaml` i plikami historii —
**nie mogą one leżeć w `_internal`**, bo ten katalog jest odtwarzany przy
każdym uruchomieniu.

## Rozwiązywanie problemów

Wszystkie komunikaty trafiają do `log.log` obok pliku wykonywalnego. W wersji
okienkowej nie ma konsoli, więc log jest jedynym źródłem informacji.

- **Ramka nie startuje** — sprawdź w logu, czy udało się otworzyć port
  szeregowy. `PermissionError` na porcie COM oznacza, że działa już druga kopia
  aplikacji albo port zajmuje inny program.
- **Menu konfiguracji nic nie robi** — sprawdź w logu wpis
  `Configuration editor opened`.
- **Brak zdjęć** — zajrzyj do logu po wpis `Loaded ... images from ...`,
  pokazuje folder, z którego aplikacja faktycznie czyta.
- **Brak temperatury** — wymaga włączonego `show_temperature` oraz wypełnionych
  współrzędnych; przy braku sieci w logu pojawia się `Nie udalo sie pobrac
  temperatury`.

Aplikacja pilnuje, żeby działała tylko jedna kopia — druga kończy się po cichu,
bo dwie instancje walczyłyby o port szeregowy.

## Plan rozwoju

Rozważana jest wersja samodzielna, bez komputera: ESP32‑S3 czytający zdjęcia
z karty SD i sterujący tym samym wyświetlaczem po USB, obsługiwany dwoma
przyciskami.
