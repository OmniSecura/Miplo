# Konfiguracja backendu

Jedynym źródłem konfiguracji jest `core/config.py` (`pydantic-settings`). Lokalnie
wartości są czytane z `services/.env`, a na produkcji powinny być przekazane jako
zmienne środowiskowe z Secret Managera. Brak wymaganej wartości kończy start
aplikacji czytelnym błędem walidacji.

Punktem wyjścia jest `services/.env.example`. Pliku `.env`, klucza Firebase ani
sekretów operatorskich nie wolno commitować.

## Baza danych

| `ENV` | Baza | Wymagane wartości |
|---|---|---|
| `local` | SQLite | `SQLITE_PATH` (domyślnie `local.db`) |
| `dev` | PostgreSQL + psycopg3 | `POSTGRES_USER`, `POSTGRES_PASSWORD`; host, port i nazwa mają wartości domyślne |
| `prod` | PostgreSQL + psycopg3 | pełny `DATABASE_URL` zaczynający się od `postgresql+psycopg://` |

`DB_ECHO=true` włącza logowanie SQL i nie powinno być używane produkcyjnie bez
konkretnej potrzeby diagnostycznej.

## Firebase

| Zmienna | Wymagana | Znaczenie |
|---|---:|---|
| `FIREBASE_ADMIN_CREDENTIALS` | tak | ścieżka do JSON konta serwisowego |
| `FIREBASE_STORAGE_BUCKET` | tak | nazwa bucketa bez `gs://` |

Firebase Auth i bucket są inicjalizowane fail-fast w lifespanie aplikacji.

## HTTP i rate limiting

| Zmienna | Domyślna wartość | Znaczenie |
|---|---|---|
| `ALLOWED_ORIGINS` | localhost:3000 i localhost:4173 | lista originów CORS rozdzielona przecinkami |
| `ALLOWED_HOSTS` | localhost, 127.0.0.1, testserver | jawna allowlista nagłówka Host |
| `RATE_LIMIT_STORAGE_URI` | `memory://` | backend limiterów; na prod wymagany Redis/Rediss |
| `GLOBAL_IP_RATE_LIMIT` | `120/minute` | limit przed routingiem, auth i walidacją |

Pamięciowy limiter nie synchronizuje liczników między instancjami Cloud Run,
dlatego `ENV=prod` odrzuca `memory://`, wildcard CORS oraz wildcard hostów.

## BoardGameGeek

| Zmienna | Domyślna wartość | Znaczenie |
|---|---|---|
| `BGG_API_BASE` | `https://boardgamegeek.com/xmlapi2` | bazowy URL XML API 2, wyłącznie HTTPS |
| `BGG_API_TOKEN` | brak | Bearer token aplikacji BGG |
| `BGG_CACHE_TTL_SECONDS` | `86400` | TTL pełnych danych, dozwolone 60–604800 s |
| `MODEL_GENERATION_CONCURRENCY` | `1` | liczba równoległych generatorów GLB na instancję |
| `MODEL_GENERATION_TIMEOUT_SECONDS` | `90` | maks. oczekiwanie requestu na wolny slot generatora |

Brak tokenu nie blokuje startu ani endpointów cache-only. Operacje wychodzące do
BGG zwracają `503 bgg_not_configured`.

## Sekrety operatorskie

| Zmienna | Endpoint | Reguła |
|---|---|---|
| `GAMES_IMPORT_KEY` | `POST /api/games/import` | 32–256 znaków; wymagany razem z Firebase tokenem jako `X-Import-Key` |
| `ADMIN_API_KEY` | `/api/admin/moderation/*` | 32–256 znaków; alternatywa dla Firebase admina jako `X-Admin-Key` |

To dwa różne sekrety. `X-Admin-Key` nie uruchamia importu katalogu, a
`X-Import-Key` nie daje dostępu do moderacji. Żaden nie może znaleźć się w
publicznym bundle'u web/mobile.

## Przykładowe uruchomienie

```powershell
services\.venv\Scripts\uvicorn.exe services.app.server:app --reload
```

Konfigurację należy sprawdzać przez start aplikacji, nie przez endpoint zwracający
sekrety — takiego endpointu celowo nie ma.

