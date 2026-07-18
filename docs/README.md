# Dokumentacja Miplo Backend

Ten katalog opisuje aktualny kontrakt backendu. Kod i wygenerowane OpenAPI są
źródłem prawdy dla sygnatur HTTP, a pliki ADR w `decisions/` wyjaśniają, dlaczego
przyjęto konkretne rozwiązania.

## Dokumenty

| Dokument | Zakres                                                      |
|---|-------------------------------------------------------------|
| [`ARCHITECTURE.md`](ARCHITECTURE.md) | granice modularnego monolitu, przepływ danych i środowiska  |
| [`AUTH+USERS.md`](AUTH+USERS.md) | Firebase Auth, lokalny user, profile, bezpieczeństwo wejścia |
| [`FIREBASE.md`](FIREBASE.md) | konfiguracja Firebase Auth i Firebase Storage               |
| [`GAMES.md`](GAMES.md) | BGG, custom games, galeria, GLB, barcode i moderacja        |
| [`SHELF.md`](SHELF.md) | półka usera, wypożyczanie, statystyki i import kolekcji BGG |
| [`ENDPOINTS.md`](ENDPOINTS.md) | pełny katalog aktualnych endpointów HTTP                    |
| [`DEMO-FRONTEND.md`](DEMO-FRONTEND.md) | gotowy brief dla do zbudowania demo frontendu  |
| [`CONFIGURATION.md`](CONFIGURATION.md) | zmienne środowiskowe i zachowanie local/dev/prod            |
| [`ERRORS.md`](ERRORS.md) | stabilny kontrakt `error_code` dla frontendu                |
| [`decisions/README.md`](decisions/README.md) | indeks przyjętych decyzji architektonicznych                |

## Aktualny zakres

- `users`: find-or-create po Firebase UID, profil, avatar, soft delete i RODO;
- `games`: katalog BGG, operatorski import dumpa, custom games i typy many-to-many;
- `shelf`: prywatna półka, publiczne oferty wypożyczenia, statystyki i import BGG;
- community: moderowane okładki, galeria, modele pudełek GLB i barcode per język;
- administracja: Firebase user z `is_admin=true` albo operatorski `X-Admin-Key`;
- przyszłe domeny: ratings, matchmaking i venues.

## Uruchomienie lokalne

1. Skopiuj `services/.env.example` do `services/.env` i uzupełnij wymagane sekrety.
2. Ustaw `ENV=local`; baza SQLite powstanie automatycznie pod `SQLITE_PATH`.
3. Uruchom z katalogu repozytorium:

```powershell
services\.venv\Scripts\uvicorn.exe services.app.server:app --reload
```

Swagger jest dostępny pod `/` i `/docs`, a OpenAPI pod `/openapi.json`.

## Migracje

`Base.metadata.create_all()` tworzy wyłącznie brakujące tabele i jest przeznaczone
dla lokalnego developmentu. Nie zastępuje migracji istniejącego schematu.

- SQLite: `services/scripts/migrate_local_game_media.py local.db`; skrypt tworzy
  backup przed pierwszą zmianą i jest idempotentny.
- PostgreSQL: stosuj kontrolowane migracje w kolejności:
  1. `database/sql/migrations/0002_game_media_moderation.sql`,
  2. `database/sql/migrations/0003_game_barcodes.sql`,
  3. `database/sql/migrations/0004_game_language_enum.sql`,
  4. `database/sql/migrations/0005_exact_barcode_formats.sql`,
  5. `database/sql/migrations/0006_shelf_items.sql`.

Docelowo produkcyjne migracje powinny zostać przeniesione do Alembic.

## Kontrakt API

- prefix domenowy: `/api`, bez `/v1`;
- auth: `Authorization: Bearer <Firebase ID token>`;
- błędy domenowe: `{"detail":{"error_code":"...","details":{...}}}`;
- tekst komunikatu i tłumaczenie należą do frontendu;
- publiczne identyfikatory: `tag`, `slug` oraz losowe UUID mediów/propozycji;
- wewnętrzne `users.id`, `firebase_uid`, `is_active`, `is_admin` i `updated_at`
  nie są zwracane w profilach.

## Weryfikacja

```powershell
services\.venv\Scripts\python.exe -B -m unittest discover -s services/tests -v
```

Aktualny zestaw obejmuje 42 testy (30 `games`, 12 `shelf`) bez połączeń z BGG
i Firebase.
