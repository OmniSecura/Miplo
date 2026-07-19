# Moduł games

Moduł `games` łączy trzy źródła danych w jednym katalogu:

1. cache szczegółów pobieranych z BoardGameGeek XML API 2,
2. masowy, operatorski import rankingu BGG z CSV,
3. gry customowe dodawane przez społeczność.

Półka usera pozostaje osobną domeną opisaną w [`SHELF.md`](SHELF.md). Moduł
`games` udostępnia jej batchowe pobieranie szczegółów BGG i opcjonalny kontekst
półki w `GameDetail`.

## Struktura

| Plik | Odpowiedzialność |
|---|---|
| `core/bgg_client.py` | Jedyny klient BGG: HTTP, globalny throttle, deduplikacja, XML i retry |
| `games/models/game.py` | `Game`, `GameType`, `GameImage`, `GameBarcode` i relacje |
| `games/schemas/game.py` | Walidacja formularzy i kontrakty odpowiedzi |
| `games/services/game_service.py` | Cache BGG, wyszukiwanie, CRUD custom i wszystkie commity |
| `games/services/catalog_import_service.py` | Atomowy import CSV full/update po 1000 rekordów |
| `games/services/bgg_sync_service.py` | Trzy priorytety i budżet nightly sync |
| `games/services/cover_service.py` | Walidacja, WEBP i Firebase Storage dla okładek |
| `games/services/gallery_service.py` | Prywatny staging i publikacja zdjęć galerii |
| `games/services/box_generator_service.py` | Walidacja sześciu ścian, GLB 2.0 i Storage |
| `games/services/moderation_service.py` | Akceptacja, odrzucanie i blokada kontrybucji |
| `games/routers/router.py` | Endpointy HTTP, bez zapytań SQL |
| `games/routers/admin_router.py` | Operatorski import chroniony wspólnym auth admina |
| `games/routers/moderation_router.py` | Endpointy dostępne tylko dla administratora |
| `scripts/nightly_sync.py` | Punkt wejścia dla Cloud Run Job |

## BGG: wyszukiwanie i cache

```text
GET /api/games/search?q=Brass
    ├─ wyniki są lokalnie → zwróć bazę
    └─ brak wyników → BGG /search (bez zapisu)

GET /api/games/bgg/224517
    ├─ świeży kompletny cache → zwróć bazę
    └─ brak / stary / rekord tylko z dumpa → BGG /thing → upsert → zwróć
```

`cached_at = NULL` oznacza rekord utworzony z dumpa rankingowego, bez pobranych
szczegółów. Dzięki temu kliknięcie gry dociąga opis i okładkę, nawet jeśli sam
rekord powstał przed chwilą podczas importu. TTL pełnych szczegółów wynosi
`BGG_CACHE_TTL_SECONDS` (domyślnie 30 dni).

Upsert `/thing` korzysta z dwóch jawnych whitelist. Pola statyczne (tytuł, opis,
rok, gracze, czas, waga i okładka) są odświeżane co 30 dni, ale odpowiedź `NULL`
nie usuwa dobrej wartości lokalnej. `rating`, `bgg_rank` i `users_rated` API
uzupełnia tylko wtedy, gdy są `NULL`; później aktualizuje je tygodniowy CSV.
Żadna ścieżka BGG nie dotyka agregatów Miplo, wymiarów, mediów, barcode ani GLB.

`GET /api/games/{slug}` przyjmuje również zwykłą nazwę. FastAPI dekoduje URL,
a backend normalizuje `Brass Birmingham` do `brass-birmingham`. Stary cache może
uruchomić ograniczony best-effort refresh: jedna gra ma cooldown, a instancja
przyjmuje maksymalnie 32 oczekujące odświeżenia. Gwarantowaną ścieżką operacyjną
pozostaje codzienny `nightly_sync`.

Brak `BGG_API_TOKEN` nie blokuje startu. Katalog, slug i barcode działają,
a operacje wymagające BGG zwracają `503 bgg_not_configured`.

Klient udostępnia także `fetch_games()` dla maksymalnie 20 BGG ID w jednym
`/thing?id=...&stats=1`. Korzysta z niego import kolekcji w domenie `shelf`, aby
200 gier nie oznaczało 200 requestów do BGG.

XML jest pobierany strumieniowo z limitem 5 MB i parsowany przez `defusedxml`;
encje/DTD, nadmiar danych, redirecty i nieoficjalne hosty okładek są odrzucane.
Każda fizyczna próba HTTP, również retry, przechodzi przez semafor oraz minimalny
odstęp 5 sekund. Równoległe żądania o ten sam `bgg_id` współdzielą jeden request.

### Warunki korzystania z BGG

Backend wysyła token aplikacji wyłącznie jako serwerowy Bearer i nigdy nie zwraca
go klientowi. Przed publicznym wdrożeniem operator rejestruje aplikację w BGG,
akceptuje aktualne warunki/licencję odpowiednią dla modelu biznesowego i okresowo
weryfikuje ich zmiany. Frontend musi pokazać „Powered by BoardGameGeek data” z
linkiem do BGG; backend zwraca te dane atrybucyjne w `GET /health`.

## Import pełnego rankingu BGG

Endpoint operatorski to `POST /api/admin/games/import`. Wymaga aktywnego Firebase
admina albo `X-Admin-Key`; osobny `X-Import-Key` został usunięty. Limit wynosi
`2/day`. Formularz zawiera plik `.csv` oraz enum `mode=update|full` (domyślnie
`update`, widoczny jako dropdown w Swaggerze).

Plik ma limit 50 MB i musi mieć content type `text/csv` albo
`application/vnd.ms-excel`. Wymagane kolumny:

```text
id,name,yearpublished,rank,bayesaverage,average,usersrated,is_expansion
```

Import działa atomowo, jest blokowany per proces i dodatkowo PostgreSQL advisory
lockiem między instancjami. Upsert jest batchowany po 1000 rekordów.

- `update`: istniejące gry aktualizują tylko `rating`, `bgg_rank`, `users_rated`
  oraz `year_published`; nowe `bgg_id` są dodawane;
- `full`: dodatkowo aktualizuje `title` oraz `is_expansion`; służy głównie do
  pierwszego seedu;
- oba tryby nigdy nie zmieniają slugu, cache szczegółów, pól Miplo, mediów,
  wymiarów, modelu, barcode ani moderacji.

Plik jest parsowany z `UploadFile`, nie trafia do Firebase ani repo. Błędny
nagłówek zwraca `invalid_csv_format`, przekroczenie limitu `csv_too_large`, a
równoległy import `import_already_running`.

## Nightly sync

`python -m services.scripts.nightly_sync` uzupełnia dane w kolejności:

1. gry na półkach lub ocenione, które mają `cached_at=NULL`;
2. stare gry używane przez userów;
3. najwyżej sklasyfikowane gry bez pobranych szczegółów.

Job pobiera paczki po 20, respektuje globalny throttle i budżet czasu. Błąd jednej
paczki zwiększa licznik `failed`, ale nie przerywa całego przebiegu. Produkcyjnie
uruchamia go Cloud Scheduler jako Cloud Run Job codziennie o 03:00.

## Gry customowe

`POST /api/games` przyjmuje `multipart/form-data`. Pole `game_types` to lista
wartości enuma `GameTypeName` (multipart powtarza pole, Swagger renderuje
multi-select), np. `game_types=Euro&game_types=Familijna`. Backend:

- usuwa HTML z tytułu i opisu,
- waliduje liczbę graczy, rok, czas, wymiary i URL,
- generuje unikalny slug,
- ustawia `source="custom"`, `is_verified=false`,
- zapisuje `created_by_id` z tokenu, nigdy z payloadu,
- opcjonalną okładkę przepisuje do WEBP i wysyła do
  `games/{game_id}/cover.webp`.

Edycja i usunięcie customowej gry są dostępne wyłącznie jej twórcy. Gry BGG
zwracają `403 cannot_edit_bgg_game`. Przy usunięciu backend best-effort czyści
okładkę i przyszły `box_model.glb` z Firebase Storage.

Okładka przechodzi cztery warstwy ochrony: limit body → odczyt chunkami do 2 MB
→ allowlista Content-Type → Pillow i limit 24 Mpx. Oryginał nie trafia do chmury;
publikowany jest wyłącznie przepisany WEBP (maksymalny bok 800 px, bez EXIF).

## Galeria społecznościowa

Do zweryfikowanej gry BGG lub custom każdy aktywny user może zaproponować zdjęcie
wnętrza lub komponentów przez `POST /api/games/{slug}/images`. Niezweryfikowaną
customową grę uzupełnia tylko jej twórca. Limit wynosi 12 zdjęć na grę. Każde
zdjęcie ma limit 2 MB i 24 Mpx, jest przepisywane do WEBP (maks. 1600 px) i trafia
do prywatnej ścieżki z losowym UUID.

Odpowiedź ma `status="pending"`. Zdjęcie nie pojawia się w `GameDetail.images`
do chwili akceptacji administratora. Moderator dostaje podpisany URL ważny
15 minut, a po akceptacji obiekt staje się publiczny pod niezmiennym, losowym URL-em.
Autor może wycofać własne zdjęcie; właściciel customowej gry i administrator mogą
również usuwać materiały przypisane do tej gry.

## Model pudełka 3D

`POST /api/games/{slug}/3d-model` przyjmuje sześć wymaganych obrazów:
`front`, `back`, `left`, `right`, `top`, `bottom`. Przed publikacją customowej gry
może go wysłać tylko twórca; po zweryfikowaniu gry BGG lub custom nową wersję może
zaproponować dowolny aktywny user, o ile administrator nie zablokował kontrybucji.

Kontrakt ścian jest jednoznaczny:

- `front` — duże wieko (`box_width × box_height`),
- `back` — duży spód (`box_width × box_height`),
- `left/right` — krawędzie `box_depth × box_height`,
- `top/bottom` — krawędzie `box_width × box_depth`.

Góra każdego zdjęcia powinna wskazywać stronę oznaczoną jako góra pudełka.
Backend respektuje EXIF i automatycznie obraca o 90° zdjęcie, którego proporcje
wyraźnie nie pasują do ścianki. Dodatkowe pola `rotation_<side>` (`0/90/180/270`,
zgodnie z ruchem wskazówek zegara) pozwalają frontendowi przesłać korektę z
podglądu — szczególnie ważną dla obrotu 180°, którego nie da się niezawodnie
wywnioskować z samych pikseli bez rozpoznawania treści.

```text
null/failed/ready → pending → processing → awaiting_review → ready
                                            └──────────────→ odrzucenie
```

Niepoprawny obraz jest odrzucany synchronicznie kodem 400. `failed` oznacza
błąd późniejszego generowania, bazy albo Storage. Kandydat GLB pozostaje prywatny;
`model_3d_url` zmienia się dopiero po akceptacji moderatora. Podczas moderacji
zamiennika poprzedni zaakceptowany model nadal może być renderowany.

Kolejne `POST /3d-model` jest propozycją zamiennika, nie bezpośrednią edycją
publicznego pliku. Autor może wycofać swoją oczekującą propozycję, ale nie może
usunąć zaakceptowanego wcześniej modelu. Odrzucenie propozycji także przywraca
stan `ready` starego modelu.

Generowanie działa podczas aktywnego requestu w ograniczonym slocie CPU, a nie
w FastAPI `BackgroundTasks` — Cloud Run nie gwarantuje pracy po odpowiedzi.
Odpowiedź `202` przychodzi po ustawieniu `awaiting_review` albo `failed`.
Osierocony `pending`/`processing` przestaje blokować nową propozycję po 15 minutach.

Generator tworzy dwa node'y (`BoxBase`, `BoxLid`) bez CSG. Tekstury boków są
dzielone UV między widoczny pasek denka i nałożone wieko. Sześć zoptymalizowanych
JPEG jest osadzonych wewnątrz jednego GLB — oryginały nie trafiają na dysk ani
do chmury. JPEG należy do rdzenia glTF 2.0; WebP wymaga opcjonalnego rozszerzenia.

Układ osi jest stały: `X=box_width`, `Y=box_height`, `Z=box_depth`. Wieko jest
współosiowe z denkiem i nasuwa się właśnie wzdłuż grubości `box_depth`; niewielki
zewnętrzny rant odpowiada grubości tektury i luzowi montażowemu. Spód rantu ma
matowy czarny materiał, więc przez fizyczną szczelinę nie prześwituje tło sceny.

## Moderacja i blokada kontrybucji

Kolejki pod `/api/admin/moderation` dopuszczają uniwersalny nagłówek
`X-Admin-Key: <ADMIN_API_KEY>` albo aktywnego usera Firebase z `is_admin=true`.
Pole usera jest wyłącznie bazodanowe i nie występuje w schematach profilu.
Pierwszego administratora nadaj kontrolowanym SQL-em:

```sql
UPDATE users SET is_admin = TRUE WHERE tag = 'twoj_tag';
```

`ADMIN_API_KEY` ma minimum 32 znaki, jest porównywany w stałym czasie i pochodzi
wyłącznie z `.env`/Secret Managera. To sekret operatorski do Swaggera, skryptu lub
prywatnego panelu po stronie serwera — nie może trafić do bundle'a web/mobile.
Podany, ale błędny `X-Admin-Key` kończy request kodem `401 invalid_admin_api_key`
bez fallbacku do tokenu Firebase.

Administrator osobno akceptuje/odrzuca customową grę, zdjęcie, model i barcode. Może też
wykonać `contributions/lock` albo `contributions/unlock`. Blokada odrzuca edycję
customowej gry, nowe zdjęcia, model 3D i barcode; nadal pozwala właścicielowi
usuwać własne dane.

Publiczne wyszukiwanie, katalog, slug i barcode zwracają wyłącznie gry z
`Game.is_verified=true`. Zatwierdzone media są filtrowane niezależnie.

## Typy i kategorie

Gra ma wiele typów przez `game_game_types`. Katalog typów jest ZAMKNIĘTY: enum
`GameTypeName` (`services/app/games/enums.py`) wylicza wszystkie dozwolone
wartości ("Strategia", "Euro", "Familijna", ...). Kategorie BGG są mapowane na
te wartości, np. `Economic → Euro`; kategoria spoza mapy jest pomijana, więc
katalog nigdy nie rośnie poza enum. Custom gry wybierają typy z tego samego
enuma (multi-select w Swaggerze).

Tabela słownikowa `game_types` pozostaje w bazie jako relacja many-to-many —
rekordy powstają leniwie przy pierwszym użyciu wartości enuma. Dodanie nowego
typu to jedna linia w enumie (i opcjonalnie wpis w mapie kategorii BGG).

## Barcode

Barcode nie jest już pojedynczą kolumną w `games`. Tabela `game_barcodes` pozwala
przechować dokładnie jeden zatwierdzony kod dla każdej wersji językowej gry.
Aktualny enum `GameLanguage` dopuszcza wyłącznie `pl` (polski) i `en` (angielski).
Sam kod pozostaje globalnie unikalny.

Akceptowane są tylko poprawne sumy kontrolne EAN-8, UPC-A (12 cyfr) i EAN-13.
Zalogowany user zgłasza propozycję przez `POST /api/games/{slug}/barcodes` z
formularzem `barcode` + `language_code`. Swagger renderuje język jako dropdown
z enumu. Propozycja ma status `pending` i nie działa w publicznym lookupie,
dopóki administrator jej nie zatwierdzi. Jeżeli dany język ma już barcode, stary
kod pozostaje aktywny do momentu zatwierdzenia zamiennika. Akceptacja usuwa poprzedni
rekord dla tego języka i publikuje nowy w jednej transakcji.

Blokada kontrybucji gry blokuje również nowe propozycje barcode. Migracja nie
zgaduje języka historycznej kolumny `games.barcode`: jeśli znajdzie niepuste dane,
zatrzymuje się i wymaga ręcznego przypisania ich do `pl` albo `en`.

## Katalog i dodatki

`GET /api/games` domyślnie ukrywa dodatki (`is_expansion=false`). Parametr
`include_expansions=true` dołącza je do wyników. Pozostałe filtry: `search`,
`players`, `game_type`, `source`, `page`, `size`. Niezweryfikowane rekordy są
dostępne wyłącznie w kolejce administratora.

## Konfiguracja

```env
BGG_API_BASE=https://boardgamegeek.com/xmlapi2
BGG_API_TOKEN=
BGG_CACHE_TTL_SECONDS=2592000
BGG_MAX_CONCURRENT=2
BGG_MIN_REQUEST_INTERVAL=5.0
ADMIN_API_KEY=<losowy-sekret-minimum-32-bajty>
```

Token BGG i klucz operatorski trafiają wyłącznie do `.env`/Secret Managera.

## Lokalna baza i migracje

`Base.metadata.create_all()` tworzy brakujące tabele, ale nie zmienia istniejących.
Dla zachowania lokalnego katalogu użyj skryptu
`services/scripts/migrate_local_game_media.py`; przed zmianą automatycznie tworzy
kopię pliku SQLite. Na dev/prod zastosuj migrację
`database/sql/migrations/0002_game_media_moderation.sql`, a następnie
`database/sql/migrations/0003_game_barcodes.sql` i
`database/sql/migrations/0004_game_language_enum.sql` oraz
`database/sql/migrations/0005_exact_barcode_formats.sql` (docelowo Alembic).
Tabela półki jest dodawana przez `0006_shelf_items.sql`, a oceny i agregaty
przez `0007_ratings.sql`.

## Testy

```powershell
services\.venv\Scripts\python.exe -B -m unittest services.tests.test_games services.tests.test_sync_bgg -v
```

Testy nie łączą się z BGG ani Firebase. Przypadki pokrywają import
idempotentny, filtrowanie, ownership, prywatną galerię, rolę admina, blokadę
kontrybucji, moderację modelu, barcode per język i jego atomową podmianę,
strukturę binarną GLB, throttle 50 requestów, deduplikację, nightly sync,
whitelisty CSV, retry BGG oraz walidację obrazów.
