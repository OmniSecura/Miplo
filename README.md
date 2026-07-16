# Miplo

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
├── backend/               # FastAPI (monolit modularny)
│   └── app/
│       ├── core/          # config, baza, auth
│       └── games/         # pierwsza domena: proxy/cache do BGG
```

## Uruchomienie (backend)

> Uzupełnić, gdy backend ruszy. Na razie szkielet.

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -e .
cp .env.example .env    # uzupełnij własne wartości
uvicorn app.main:app --reload
```
