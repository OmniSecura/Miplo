# Architektura — Miplo

Skrót aktualnej architektury. Indeks dokumentacji znajduje się w
[`README.md`](README.md), uzasadnienia wyborów w [`decisions/`](decisions/README.md),
a pełny katalog HTTP w [`ENDPOINTS.md`](ENDPOINTS.md).

## Ogólny kształt

Miplo jest modularnym monolitem: jeden serwis FastAPI, jedna baza i jeden deploy,
ale kod jest podzielony na niezależne domeny.

```text
Aplikacja web/PWA (później mobile)
        │ HTTPS + Firebase ID token
        ▼
FastAPI / Cloud Run
        ├── core       — config, baza, auth, BGG, limity, błędy
        ├── users      — lokalny profil i avatar
        ├── games      — katalog BGG, import dumpa i customowe gry
        ├── shelf      — półka usera                         [przyszły ticket]
        ├── matchmaking                                      [przyszły ticket]
        └── venues                                            [przyszły ticket]
        │
        ├── PostgreSQL / Cloud SQL — dane relacyjne i cache BGG
        ├── Firebase Storage       — prywatny staging i zatwierdzone publiczne media
        └── Secret Manager         — sekrety DB, Firebase, BGG i importu
```

## Granice modułów

- Każda domena ma układ `models / schemas / services / routers`.
- Router waliduje protokół HTTP i wywołuje serwis. Nie wykonuje zapytań ani
  commitów. Wszystkie operacje bazodanowe należą do warstwy `service`.
- `core/auth.py` jest jedynym miejscem weryfikującym Firebase ID token.
- `core/storage.py` udostępnia bucket. Operacje na plikach są zamknięte w
  wyspecjalizowanych serwisach avatara, okładek, galerii i modeli 3D.
- Tożsamość i właściciel zasobu zawsze pochodzą ze zweryfikowanego tokenu,
  nigdy z identyfikatora przesłanego w body.
- API nie ma `/v1`. Wersjonowanie w URL pojawi się dopiero, gdy będzie istniał
  niezależny klient, którego nie możemy aktualizować razem z backendem.
- Błędy są stabilnymi kodami, np.
  `{"detail":{"error_code":"game_not_found"}}`; tekst tłumaczy frontend.

## Games i BoardGameGeek

`core/bgg_client.py` jest jedynym klientem BoardGameGeek XML API 2. Wymusza
Bearer token, limit odpowiedzi, timeout 10 s i retry odpowiedzi HTTP 202.

Pełne rekordy BGG są cache'owane w PostgreSQL przez 24 godziny. Search najpierw
sprawdza bazę, a przy braku wyniku pyta BGG. Sama lista wyników z BGG nie jest
zapisywana; upsert następuje po wybraniu konkretnej gry. Oficjalny dump rankingów
można załadować operatorskim endpointem CSV/JSON. Rekord z dumpa ma
`cached_at=NULL`, co oznacza „podstawowy wpis bez pobranych szczegółów”.

Redis nie uczestniczy obecnie w cache katalogu. Można go dodać później jako
krótkotrwały cache odpowiedzi, ale źródłem prawdy pozostaje PostgreSQL.

Publicznego importu kolekcji BGG nie ma. Został celowo usunięty do czasu modułu
`shelf` i trwałego systemu zadań; długa operacja nie powinna działać jako zwykły
request ani nietrwały `BackgroundTasks`.

Wymagana atrybucja BGG jest zwracana przez `/health`; frontend powinien pokazać
„Powered by BoardGameGeek data” z linkiem do `https://boardgamegeek.com`.

## Customowe gry

Gry BGG i customowe korzystają z jednej tabeli `games`. `source` rozróżnia ich
pochodzenie. Customowa gra powstaje jako `is_verified=false`, a jej
`created_by_id` pochodzi z tokenu. Wyłącznie twórca może ją edytować lub usunąć;
rekordów `source=bgg` nie zmienia się tymi endpointami.

Okładka customowej gry jest limitowana, dekodowana przez Pillow, pozbawiana
metadanych i przepisywana do WEBP. Galeria, okładka i GLB trafiają do prywatnego
stagingu i stają się publiczne dopiero po moderacji. Klient nie może ustawić
żadnego URL-a zasobu samodzielnie.

Administrator uwierzytelnia się lokalnym userem z bazodanowym `is_admin=true` albo
uniwersalnym `X-Admin-Key` z Secret Managera. Chronione endpointy pozwalają
akceptować/odrzucać niezależnie grę, zdjęcia, model i barcode oraz zamknąć lub
otworzyć dalsze kontrybucje do konkretnej gry. Barcode ma osobną tabelę i dokładnie
jeden zatwierdzony rekord na język gry. Klucz operatorski nigdy nie trafia do
publicznego frontendu.

## Środowiska bazy

- `ENV=local` — SQLite i automatyczne `create_all`, wyłącznie do szybkiego dev.
- `ENV=dev` — PostgreSQL URL budowany z `POSTGRES_*`.
- `ENV=prod` — pełny `DATABASE_URL` dostarczony jako sekret.

`create_all` nie jest systemem migracji. Zmiany istniejącej bazy PostgreSQL należy
wdrażać Alembikiem lub kontrolowanym SQL-em z `database/sql/`. Aktualna kolejność
to `0002_game_media_moderation.sql`, następnie `0003_game_barcodes.sql`.
Po nich stosujemy `0004_game_language_enum.sql`, ograniczając wersje do `pl/en`.

## Powiązane decyzje

Pełny, aktualny indeks ADR znajduje się w [`decisions/README.md`](decisions/README.md).
