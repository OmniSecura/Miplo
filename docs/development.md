# Development setup

## Wymagania

- Python 3.11+;
- [uv](https://docs.astral.sh/uv/);
- Docker Desktop z Docker Compose;
- klucz Firebase Admin wyłącznie do lokalnego projektu developerskiego.

## Pierwsze uruchomienie

Z katalogu repozytorium:

```powershell
# Zależności produkcyjne i narzędzia developerskie z uv.lock.
uv sync --project services --all-extras --no-install-project

# Hooki uruchamiane przy każdym commit.
services\.venv\Scripts\pre-commit.exe install

# Konfiguracja aplikacji.
Copy-Item services/.env.example services/.env
New-Item -ItemType Directory -Force secrets
# Umieść klucz pod: secrets/firebase-admin-dev.json
```

Uzupełnij `services/.env`, szczególnie `FIREBASE_STORAGE_BUCKET` i opcjonalnie
`BGG_API_TOKEN`. Plik `.env` oraz katalog `secrets/` są ignorowane przez Git i Docker.

`RATE_LIMIT_STORAGE_URI=memory://` działa przy uruchomieniu bez Redisa. Docker Compose
nadpisuje je na `redis://redis:6379/1`. Nie ustawiamy osobnego `REDIS_URL`: dane BGG
są cache'owane w PostgreSQL, a Redis przechowuje obecnie wyłącznie liczniki limitów.

## Uruchomienie lokalne bez kontenera API

```powershell
docker compose up -d db redis
services\.venv\Scripts\uvicorn.exe services.app.server:app --reload
```

## Uruchomienie całego środowiska w Dockerze

```powershell
docker compose up --build
docker compose logs -f api
```

API: `http://localhost:8000`, Swagger: `http://localhost:8000/docs`.

Compose montuje `secrets/firebase-admin-dev.json` tylko do `/run/secrets` i nigdy
nie kopiuje go do obrazu. PostgreSQL oraz Redis są wystawione wyłącznie na
`127.0.0.1`, a kod aplikacji jest montowany read-only z hot reloadem.

Zatrzymywanie:

```powershell
docker compose down       # dane zostają w wolumenach
docker compose down -v    # usuwa także lokalne dane PostgreSQL i Redis
```

## Przed commitem

Hooki wykonują się automatycznie. Pełna kontrola ręczna:

```powershell
services\.venv\Scripts\pre-commit.exe run --all-files
uv run --project services ruff check services
uv run --project services ruff format --check services
uv run --project services mypy --config-file services/pyproject.toml services/app
uv run --project services pytest services/tests
```

## Docker

```powershell
docker build -t miplo:local ./services
docker image inspect miplo:local
```

Produkcyjny obraz działa jako użytkownik `miplo` (UID 1001), korzysta z `${PORT}`
i uruchamia `uvicorn services.app.server:app`. Do obrazu trafiają tylko zależności
produkcyjne, aplikacja i skrypty operatorskie — bez testów, `.env` i sekretów.
