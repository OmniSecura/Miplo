# Miplo

[![CI](https://github.com/OmniSecura/Miplo/actions/workflows/ci.yml/badge.svg)](https://github.com/OmniSecura/Miplo/actions/workflows/ci.yml)

Aplikacja dla planszówkowiczów: wizualna półka 3D z grami, kojarzenie graczy
z okolicy i (docelowo) wypożyczanie gier między użytkownikami.

**Status:** wczesny development (MVP)

## Co to jest

Miplo łączy trzy rzeczy, których razem nie robi żadna istniejąca apka:
- **Półka 3D** — twoje gry jako ładne pudełka 3D (dane i okładki z BoardGameGeek)
- **Społeczność lokalna** — znajdź ludzi z okolicy, którzy mają grę X i chcą zagrać
- **Wypożyczanie P2P** — (późniejszy etap) pożyczaj gry między użytkownikami

Szczegółowa lista funkcji i roadmapa: patrz [VISION.md](./VISION.md).

## Architektura (w skrócie)

- **Backend:** monolit modularny w FastAPI (Python), jedna baza PostgreSQL
- **Auth:** Firebase Auth (logowanie), własna tabela `users` powiązana przez `firebase_uid`
- **Dane gier:** BoardGameGeek XML API 2 (proxy + cache)
- **Hosting:** GCP Cloud Run + Cloud SQL + Secret Manager
- **Frontend web/PWA:** React (w tym repo, katalog `web/`)
- **Mobile:** osobne repo (dojdzie później)

Uzasadnienia decyzji architektonicznych: patrz [docs/decisions/](./docs/decisions/).

Powered by BoardGameGeek data.

## Struktura repo

```
miplo/
├── README.md              # ten plik
├── VISION.md              # wszystkie funkcje, rdzeń → v1 → v2
├── docs/                  # dokumentacja techniczna
│   ├── architecture.md
│   └── decisions/         # ADR – zapisy decyzji i dlaczego
├── services/              # FastAPI (monolit modularny)
│   ├── app/
│   │   ├── core/          # config, baza, auth, bezpieczeństwo
│   │   ├── games/         # katalog BGG/custom i moderacja mediów
│   │   ├── shelf/         # półki użytkowników
│   │   └── ratings/       # oceny i recenzje społeczności
│   ├── tests/
│   └── Dockerfile
└── docker-compose.yml     # lokalne API + PostgreSQL + Redis
```

## Development

Pełna instrukcja: [docs/development.md](docs/development.md). Konfiguracja pipeline'u
i ochrony `main`: [docs/CI.md](docs/CI.md).

Szybki start:

```powershell
uv sync --project services --all-extras --no-install-project
docker compose up -d db redis
services\.venv\Scripts\uvicorn.exe services.app.server:app --reload
```
