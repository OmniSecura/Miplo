# Operacje — synchronizacja z BoardGameGeek

## Zasady ogólne

- Token `BGG_API_TOKEN` i `ADMIN_API_KEY` są sekretami serwerowymi.
- Frontend nigdy nie pobiera dumpa ani nie wywołuje endpointów `/api/admin/*`.
- Wszystkie requesty XML API przechodzą przez throttle klienta BGG.
- Dopóki throttle jest per proces, produkcyjne API powinno mieć jedną instancję
  wykonującą ruch do BGG albo zostać rozszerzone o wspólny token bucket w Redis.
- Cloud Run Job `nightly_sync` konfiguruj z `task count = 1` i bez równoległych
  prób tego samego harmonogramu.

## Co tydzień — niedziela

1. Pobierz świeży `boardgames_ranks.csv` z
   `https://boardgamegeek.com/data_dumps/bg_ranks` po zalogowaniu do BGG.
2. Wywołaj `POST /api/admin/games/import` jako `multipart/form-data`:
   - `X-Admin-Key: <ADMIN_API_KEY>` albo Firebase token admina,
   - `file`: pobrany CSV,
   - `mode=update`.
3. Sprawdź `total_rows`, `inserted`, `updated`, `skipped`, `errors` i
   `duration_seconds`. `errors` powinno wynosić `0`; `inserted` oznacza nowe BGG ID.

`mode=full` służy do pierwszego seedu lub świadomej odbudowy podstaw katalogu.
Nie uruchamiaj go rutynowo na produkcji — może zmienić tytuł i flagę dodatku.

Import działa synchronicznie i dla pełnego dumpa może trwać 1–3 minuty.
Usługa Cloud Run obsługująca ten endpoint musi mieć timeout żądania ustawiony
na co najmniej **300 sekund**. Nie ustawiamy tego w FastAPI ani w `.env`, ponieważ
jest to parametr infrastruktury wdrożeniowej Cloud Run.

## Codziennie — 03:00

Cloud Scheduler uruchamia Cloud Run Job wykonujący z katalogu repo:

```powershell
python -m services.scripts.nightly_sync
```

Job priorytetowo pobiera szczegóły gier z półek i ocen, potem stare dane tych gier,
a pozostały budżet przeznacza na najwyższy ranking bez `cached_at`. Zwraca w logu
JSON ze statystykami. Nie wymaga publicznego endpointu ani sekretu HTTP.

Zalecane parametry:

```env
NIGHTLY_SYNC_BUDGET=1800
NIGHTLY_SYNC_LEVEL1_LIMIT=200
NIGHTLY_SYNC_LEVEL2_LIMIT=100
BGG_MIN_REQUEST_INTERVAL=5.0
```

## Reakcja na błędy

- `bgg_rate_limited`: nie ponawiaj ręcznie w pętli; sprawdź liczbę instancji i logi;
- `bgg_unavailable`: katalog cache działa dalej; kolejny job spróbuje ponownie;
- `invalid_csv_format`: zweryfikuj źródło i pełny nagłówek pliku;
- `csv_too_large`: nie dziel pliku w sposób tworzący duplikaty; najpierw sprawdź,
  czy pobrano oficjalny dump i czy nie został uszkodzony;
- `import_already_running`: poczekaj na bieżący atomowy import.

## Kontrola po wdrożeniu

1. `GET /health` — baza musi być `reachable`.
2. Wykonaj import `mode=update` na pliku testowym.
3. Uruchom nightly job z małym budżetem w środowisku dev.
4. Potwierdź, że `miplo_rating`, media, barcode, slug i `cached_at` nie zmieniły
   się po tygodniowym imporcie CSV.
