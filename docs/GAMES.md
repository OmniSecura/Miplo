# Moduł games

Moduł `games` łączy trzy źródła danych w jednym katalogu:

1. cache szczegółów pobieranych z BoardGameGeek XML API 2,
2. masowy, operatorski import rankingu BGG z CSV/JSON,
3. gry customowe dodawane przez społeczność.

Półka usera pozostaje osobną domeną opisaną w [`SHELF.md`](SHELF.md). Moduł
`games` udostępnia jej batchowe pobieranie szczegółów BGG i opcjonalny kontekst
półki w `GameDetail`.

## Struktura

| Plik | Odpowiedzialność |
|---|---|
| `core/bgg_client.py` | Jedyny klient BGG: HTTP, Bearer token, XML, timeout i retry HTTP 202 |
| `games/models/game.py` | `Game`, `GameType`, `GameImage`, `GameBarcode` i relacje |
| `games/schemas/game.py` | Walidacja formularzy i kontrakty odpowiedzi |
| `games/services/game_service.py` | Cache BGG, wyszukiwanie, CRUD custom i wszystkie commity |
| `games/services/catalog_import_service.py` | Batchowy import CSV/JSON |
| `games/services/cover_service.py` | Walidacja, WEBP i Firebase Storage dla okładek |
| `games/services/gallery_service.py` | Prywatny staging i publikacja zdjęć galerii |
| `games/services/box_generator_service.py` | Walidacja sześciu ścian, GLB 2.0 i Storage |
| `games/services/moderation_service.py` | Akceptacja, odrzucanie i blokada kontrybucji |
| `games/routers/router.py` | Endpointy HTTP, bez zapytań SQL |
| `games/routers/moderation_router.py` | Endpointy dostępne tylko dla administratora |

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
`BGG_CACHE_TTL_SECONDS` (domyślnie 24 h).

`GET /api/games/{slug}` przyjmuje również zwykłą nazwę. FastAPI dekoduje URL,
a backend normalizuje `Brass Birmingham` do `brass-birmingham`. Stary cache jest
zwracany od razu i odświeżany best-effort w tle z nową sesją bazy.

Brak `BGG_API_TOKEN` nie blokuje startu. Katalog, slug i barcode działają,
a operacje wymagające BGG zwracają `503 bgg_not_configured`.

Klient udostępnia także `fetch_games()` dla maksymalnie 20 BGG ID w jednym
`/thing?id=...&stats=1`. Korzysta z niego import kolekcji w domenie `shelf`, aby
200 gier nie oznaczało 200 requestów do BGG.

### Warunki korzystania z BGG

Backend wysyła token aplikacji wyłącznie jako serwerowy Bearer i nigdy nie zwraca
go klientowi. Przed publicznym wdrożeniem operator rejestruje aplikację w BGG,
akceptuje aktualne warunki/licencję odpowiednią dla modelu biznesowego i okresowo
weryfikuje ich zmiany. Frontend musi pokazać „Powered by BoardGameGeek data” z
linkiem do BGG; backend zwraca te dane atrybucyjne w `GET /health`.

## Import pełnego rankingu BGG

Endpoint operatorski:

```http
POST /api/games/import
Authorization: Bearer <firebase-id-token>
X-Import-Key: <GAMES_IMPORT_KEY>
Content-Type: multipart/form-data
file: boardgames_ranks.csv
```

Obsługiwane są `.csv` oraz `.json`. Limit pliku to 32 MB, limit rekordów 250 000,
a zapis odbywa się batchami po 1000. Import jest idempotentny po `bgg_id`:
ponowne wysłanie pliku aktualizuje ranking, ocenę i liczbę głosów zamiast tworzyć
duplikaty.

Minimalny CSV musi mieć kolumny `id,name`. Pełny dump BGG może zawierać:

```text
id,name,yearpublished,rank,average,usersrated,is_expansion
```

JSON może być tablicą rekordów albo obiektem z polem `items`/`games`:

```json
[
  {
    "id": 224517,
    "name": "Brass: Birmingham",
    "yearpublished": 2018,
    "rank": 1,
    "average": 8.61,
    "usersrated": 50000,
    "is_expansion": false
  }
]
```

Plik istnieje tylko jako `UploadFile` podczas requestu. Backend nie zapisuje go
w repo ani w Firebase. JSON jest ograniczony tym samym limitem 32 MB; CSV jest
czytany strumieniowo. Nie uruchamiamy automatycznego 20-minutowego enrichmentu
top 5000 w `BackgroundTasks`: Cloud Run nie gwarantuje dokończenia takiego joba.
Szczegóły są dociągane leniwie przez `/games/bgg/{bgg_id}`.

## Gry customowe

`POST /api/games` przyjmuje `multipart/form-data`. Pole `game_types` jest tekstem
JSON, np. `["Euro", "Familijna"]`. Backend:

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

Gra ma wiele typów przez `game_game_types`. Kategorie BGG są mapowane na bardziej
czytelne polskie typy, np. `Economic → Euro`. Nieznana kategoria nie jest tracona:
powstaje nowy `GameType` z automatycznym slugiem.

Celowo nie używamy kodowego `Enum`: katalog kategorii BGG jest otwarty i zmienny,
a jedna gra może należeć do wielu typów. Tabela słownikowa i relacja many-to-many
pozwalają dodać nowy typ bez wdrażania kodu ani migracji enumu.

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
BGG_CACHE_TTL_SECONDS=86400
GAMES_IMPORT_KEY=<losowy-sekret-minimum-32-bajty>
ADMIN_API_KEY=<inny-losowy-sekret-minimum-32-bajty>
```

Token BGG i oba klucze operatorskie trafiają wyłącznie do `.env`/Secret Managera.

## Lokalna baza i migracje

`Base.metadata.create_all()` tworzy brakujące tabele, ale nie zmienia istniejących.
Dla zachowania lokalnego katalogu użyj skryptu
`services/scripts/migrate_local_game_media.py`; przed zmianą automatycznie tworzy
kopię pliku SQLite. Na dev/prod zastosuj migrację
`database/sql/migrations/0002_game_media_moderation.sql`, a następnie
`database/sql/migrations/0003_game_barcodes.sql` i
`database/sql/migrations/0004_game_language_enum.sql` oraz
`database/sql/migrations/0005_exact_barcode_formats.sql` (docelowo Alembic).
Tabela półki jest dodawana później przez `0006_shelf_items.sql`.

## Testy

```powershell
services\.venv\Scripts\python.exe -B -m unittest services.tests.test_games -v
```

Testy nie łączą się z BGG ani Firebase. Aktualne 30 przypadków pokrywa import
idempotentny, filtrowanie, ownership, prywatną galerię, rolę admina, blokadę
kontrybucji, moderację modelu, barcode per język i jego atomową podmianę,
strukturę binarną GLB, retry BGG oraz walidację obrazów.
