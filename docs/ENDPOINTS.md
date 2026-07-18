# Endpointy API Miplo

Aktualny katalog endpointów. Prefix API: `/api`. Interaktywny kontrakt OpenAPI:
`GET /docs` po uruchomieniu serwera.

## Wspólne zasady

- `Auth: tak` oznacza nagłówek `Authorization: Bearer <Firebase ID token>`.
- Błędy domenowe mają format `{"detail":{"error_code":"..."}}`.
- `401` oznacza brak/niepoprawny token, `403` brak uprawnień, `429` limit.
- `READ_LIMIT`: 60/min, `WRITE_LIMIT`: 20/min, `DELETE_LIMIT`: 5/h,
  upload avatara: 5/min, customowa gra: 5/h, galeria: 10/h, model 3D: 3/h,
  import katalogu: 1/h, import kolekcji BGG: 2/h.
- Wewnętrzne `users.id` i `firebase_uid` nigdy nie są zwracane.

Swagger dzieli operacje wyłącznie tagami: `users`, `games`, `BGG games`,
`custom games`, `game gallery`, `3D models`, `shelf`, `moderation` i `system`. To nadal
jeden serwis, jeden prefix i jeden dokument OpenAPI.

## System

### `GET /health`

Auth: nie. Sprawdza proces i połączenie z bazą. Zwraca również metadane wymaganej
atrybucji BGG:

```json
{
  "status": "ok",
  "database": "reachable",
  "attribution": {
    "name": "Powered by BoardGameGeek data",
    "url": "https://boardgamegeek.com"
  }
}
```

### `GET /` i `GET /docs`

Auth: nie. Otwierają Swagger UI; nie są częścią domenowego API.

## Users

### `GET /api/me`

Auth: tak. Zwraca profil zalogowanego usera: `tag`, `email`, `display_name`,
`city`, `bio`, `avatar_url`, `created_at`. Nie zwraca `id`, `firebase_uid`,
`is_active` ani `updated_at`.

### `PUT /api/me`

Auth: tak. JSON. Edytuje wyłącznie profil wynikający z tokenu. Przyjmuje `tag`,
`display_name`, `city`, `bio`. Nie pozwala ustawić avatara ani pól technicznych.

### `POST /api/me/avatar`

Auth: tak. `multipart/form-data`, pole `file`. Akceptuje JPEG/PNG/WEBP do 2 MB,
optymalizuje do WEBP 400×400 i zapisuje w Firebase Storage. Zwraca `UserProfile`.

### `DELETE /api/me/avatar`

Auth: tak. Usuwa blob i ustawia `avatar_url=NULL`. Odpowiedź `204`.

### `POST /api/me/deactivate`

Auth: tak. Soft delete: ustawia `is_active=false`; konto znika z publicznych
widoków, dane pozostają. Odpowiedź `204`.

### `POST /api/me/activate`

Auth: tak, dopuszcza nieaktywne konto. Ustawia `is_active=true`. Odpowiedź `204`.

### `DELETE /api/me`

Auth: tak, dopuszcza nieaktywne konto. Twardo usuwa lokalne dane i konto Firebase
zgodnie z RODO/Apple. Odpowiedź `204`.

### `GET /api/users/{tag}`

Auth: tak. Zwraca publiczny profil po technicznym tagu `[a-z0-9_]{3,30}`.
Nieaktywne lub nieistniejące konto daje `404 user_not_found`.

## Shelf — półka usera

### `GET /api/me/shelf`

Auth: tak. Zwraca `{items,total,page,size,pages}` dla aktualnego usera. Parametry:

- `page >= 1`, `size` od 1 do 100;
- `lendable` — filtr wypożyczalności;
- `search` — 2–100 znaków, częściowy tytuł gry;
- `condition` — dropdown `new | good | used | damaged`;
- `players` — od 1 do 50;
- `sort` — dropdown `added_at | title | game_rating | miplo_rating`.

`sort=miplo_rating` zwraca na razie `501 ratings_not_available`. Widok własny
zawiera prywatne pole `notes`.

### `POST /api/me/shelf`

Auth: tak. Dodaje zweryfikowaną grę do półki aktualnego usera. JSON zawiera
`game_slug` oraz opcjonalnie `lendable`, `lending_deposit`, `lending_notes`,
`condition`, `notes`. Kaucja: `0.00–9999.00`, notatki: maks. 500 znaków.
Odpowiedź `201`. Duplikat daje `409 game_already_on_shelf`, a brak publicznej gry
`404 game_not_found`.

### `PUT /api/me/shelf/{game_slug}`

Auth: tak. Częściowo aktualizuje dane własnego egzemplarza; pominięte pola
pozostają bez zmian. `game_slug` identyfikuje grę, a właściciel zawsze pochodzi z
tokenu. Odpowiedź `200`, brak pozycji: `404 game_not_on_shelf`.

### `DELETE /api/me/shelf/{game_slug}`

Auth: tak. Usuwa wyłącznie wpis aktualnego usera. Nie usuwa gry z katalogu ani
przyszłej oceny usera. Odpowiedź `204`.

### `GET /api/me/shelf/stats`

Auth: tak. Zwraca `total_games`, `lendable_games` oraz `total_playing_time` jako
sumę katalogowych czasów rozgrywek w minutach.

### `POST /api/me/shelf/import`

Auth: tak. Limit `2/hour`. Body:

```json
{"bgg_username":"BoardGamer_1","import_ratings":false}
```

Importuje posiadane gry addytywnie, paczkami po 20 BGG ID, z limitem 180 sekund.
Odpowiedź zawiera `imported`, `skipped`, `failed`, `ratings_imported` i
`total_in_bgg`. Timeout zwraca wynik częściowy. `import_ratings=true` daje obecnie
`501 ratings_not_available`, dopóki nie powstanie moduł ratings.

### `GET /api/users/{tag}/shelf`

Auth: tak. Zwraca półkę aktywnego usera po publicznym tagu, z paginacją i filtrem
`lendable`. Nie zawiera prywatnego `notes`. Kaucja i warunki są zwracane tylko dla
pozycji z `lendable=true`. Niezweryfikowane gry są ukryte.

## Games — publiczny katalog i BGG

### `GET /api/games/search?q={tekst}`

Auth: nie. Szuka częściowo i case-insensitive w lokalnym katalogu. Jeśli nie ma
lokalnych wyników, odpytuje BGG. `q`: 2–100 znaków. Wynik BGG nie jest zapisywany
do chwili wywołania endpointu `/games/bgg/{bgg_id}`.

### `GET /api/games`

Auth: nie. Zwraca paginację `{items,total,page,size,pages}` wyłącznie z bazy.

Parametry:

- `page` >= 1, domyślnie 1,
- `size` 1–100, domyślnie 20,
- `search` — część tytułu,
- `players` — gra obsługująca konkretną liczbę graczy,
- `game_type` — slug lub nazwa typu,
- `source` — `bgg` albo `custom`,
- `include_expansions` — domyślnie `false`.

Publiczny katalog zawsze zwraca wyłącznie zweryfikowane gry.

### `GET /api/games/bgg/{bgg_id}`

Auth: tak. Pobiera lub odświeża pełne szczegóły z BGG i zapisuje cache. Bez tokenu
BGG zwraca `503 bgg_not_configured`. Limit `WRITE_LIMIT` chroni token BGG.

### `GET /api/games/by-barcode/{barcode}`

Auth: nie. Lookup po poprawnym EAN-8/UPC-A/EAN-13. `404 barcode_not_found`, gdy
kod nie jest przypisany. Endpoint uwzględnia wyłącznie zatwierdzone kody oraz
zweryfikowane gry; oczekująca propozycja nigdy nie wpływa na wynik skanowania.

### `GET /api/games/{slug}`

Auth: opcjonalny. Pełny widok gry. Bez tokenu działa publicznie; z poprawnym
tokenem dodaje `on_my_shelf` i `my_shelf_item`. Błędny token daje `401`, nie jest
ignorowany. Parametr może być slugiem lub zwykłą nazwą, np.
`Brass Birmingham` jest normalizowane do `brass-birmingham`. Stary cache BGG jest
zwracany od razu i odświeżany best-effort w tle.

### `POST /api/games/{slug}/barcodes`

Auth: tak. `application/x-www-form-urlencoded` z dwoma polami. Swagger pokazuje
`language_code` jako dropdown z wartościami `pl` i `en`:

```text
barcode=5901549927658
language_code=pl
```

Tworzy moderowaną propozycję barcode dla konkretnej wersji językowej. Język jest
enumem: `pl` (polski) albo `en` (angielski); wejście `PL` jest normalizowane.
Odpowiedź `202` zawiera `public_id` i `status="pending"`. Jednocześnie może istnieć
tylko jedna oczekująca propozycja dla pary gra–język. Barcode jest globalnie
unikalny i musi mieć poprawną sumę kontrolną EAN-8, UPC-A albo EAN-13.

Gra może mieć po jednym zatwierdzonym barcode dla każdego języka. Jeśli język ma
już zatwierdzony kod, nowy nie nadpisuje go od razu — stary działa aż do akceptacji
zamiennika przez administratora.

Przykładowa odpowiedź `202`:

```json
{
  "public_id": "3d348762-a533-42c7-887e-9439a32c1453",
  "barcode": "5901549927658",
  "language_code": "pl",
  "status": "pending",
  "created_at": "2026-07-18T12:00:00Z"
}
```

## Games — customowe gry

### `POST /api/games`

Auth: tak. Limit 5/h. `multipart/form-data`:

- wymagane: `title`, `min_players`, `max_players`, `game_types`,
- opcjonalne: `description`, `playing_time`, `box_width`,
  `box_height`, `box_depth`, `year_published`, `instruction_url`, `cover`,
- `game_types` to JSON string, np. `["Euro","Familijna"]`.

Tworzy `source=custom`, `is_verified=false`, automatyczny slug i właściciela
z tokenu. Opcjonalna okładka jest przepisywana do WEBP 800 px i pozostaje
prywatna do akceptacji gry przez administratora. Odpowiedź `201`.

### `PUT /api/games/{slug}`

Auth: tak. `multipart/form-data`; te same opcjonalne pola co przy tworzeniu.
Tylko twórca i tylko dla `source=custom`. Zmiana tytułu generuje nowy unikalny
slug. BGG game daje `403 cannot_edit_bgg_game`, cudza gra `403 not_game_owner`.

### `DELETE /api/games/{slug}`

Auth: tak. Tylko twórca customowej gry. Usuwa rekord, relacje typów oraz zasoby
`cover.webp`/`box_model.glb` z Firebase Storage best-effort. Odpowiedź `204`.

## Games — galeria

### `POST /api/games/{slug}/images`

Auth: tak. Dla zweryfikowanej gry BGG lub custom zdjęcie może zaproponować każdy
aktywny user; przed publikacją customowej gry wyłącznie jej twórca.
`multipart/form-data`: wymagane `file`, opcjonalny `caption`. JPEG/PNG/WEBP do
2 MB i 24 Mpx jest przepisywany do WEBP maks. 1600 px. Limit 12 zdjęć na grę.
Odpowiedź `202` ze statusem `pending`; zdjęcie pozostaje prywatne do akceptacji.

### `DELETE /api/games/{slug}/images/{image_id}`

Auth: tak. Zdjęcie może usunąć jego autor, twórca customowej gry albo administrator.
Usuwa rekord oraz jego blob. Odpowiedź `204`.

Zaakceptowane zdjęcia są zwracane w tablicy `images` obiektu `GameDetail`.

## Games — modele 3D

### `POST /api/games/{slug}/3d-model`

Auth: tak. Dla customowej gry wyłącznie twórca; dla BGG dowolny zalogowany user.
Limit 3/h. `multipart/form-data` z sześcioma polami: `file_front`, `file_back`,
`file_left`, `file_right`, `file_top`, `file_bottom`. Każdy obraz ma limit 2 MB,
a cały formularz 14 MB. Odpowiedź `202` i `model_status="pending"`.

Znaczenie plików jest stałe: `front` = duże wieko, `back` = duży spód,
`left/right` = pionowe krawędzie, `top/bottom` = poziome krawędzie. Opcjonalne
pola formularza `rotation_front`, `rotation_back`, `rotation_left`,
`rotation_right`, `rotation_top`, `rotation_bottom` przyjmują wyłącznie
`0`, `90`, `180` albo `270` stopni zgodnie z ruchem wskazówek zegara.
Backend automatycznie poprawia oczywisty obrót 90° wynikający z proporcji, ale
wartość rotation pozwala frontendowi poprawić także zdjęcie odwrócone o 180°.

Generator w tle tworzy dwuczęściowy GLB (`BoxBase` + `BoxLid`) z osadzonymi
teksturami. Sukces przechodzi do `awaiting_review`; publiczny `model_3d_url`
pojawia się dopiero po akceptacji administratora.

Po zweryfikowaniu gry każdy aktywny user może przesłać lepszą propozycję sześciu
grafik. Poprzedni zaakceptowany GLB pozostaje publiczny przez całe generowanie i
moderację zamiennika. Dopiero akceptacja atomowo publikuje nową wersję.

### `DELETE /api/games/{slug}/3d-model`

Auth: tak. Autor propozycji, twórca customowej gry albo administrator może anulować
oczekującą propozycję. Anulowanie nigdy nie usuwa wcześniejszego zaakceptowanego
modelu. Odpowiedź `204`.

## Moderation — tylko administrator

Wszystkie poniższe endpointy wymagają jednego z dwóch mechanizmów:

- `X-Admin-Key: <ADMIN_API_KEY>` — uniwersalny sekret operatorski z `.env`, albo
- `Authorization: Bearer <Firebase ID token>` aktywnego usera z `is_admin=true`.

Jeżeli nagłówek `X-Admin-Key` został podany, ma pierwszeństwo i musi być poprawny;
błędnego klucza nie można obejść równoczesnym tokenem Firebase. Klucza nie wolno
umieszczać we frontendzie publicznej aplikacji. W Swaggerze wpisuje go ręcznie operator.

### Gry customowe

- `GET /api/admin/moderation/games` — kolejka niezweryfikowanych gier, wraz z
  podpisanym podglądem okładki.
- `POST /api/admin/moderation/games/{slug}/approve` — publikuje okładkę i grę.
- `DELETE /api/admin/moderation/games/{slug}` — odrzuca grę i czyści cały prefix Storage.

### Blokada społeczności

- `POST /api/admin/moderation/games/{slug}/contributions/lock` — blokuje edycję,
  nowe zdjęcia, model i barcode.
- `POST /api/admin/moderation/games/{slug}/contributions/unlock` — ponownie je włącza.

Stan jest zwracany publicznie jako `community_contributions_enabled`, aby frontend
mógł ukrywać formularze.

### Zdjęcia

- `GET /api/admin/moderation/images` — oczekujące zdjęcia i podpisane URL-e podglądu.
- `POST /api/admin/moderation/images/{image_id}/approve` — publikuje zdjęcie.
- `DELETE /api/admin/moderation/images/{image_id}` — odrzuca i usuwa blob.

### Modele

- `GET /api/admin/moderation/models` — modele `awaiting_review` i podpisane URL-e.
- `POST /api/admin/moderation/models/{slug}/approve` — publikuje GLB jako model gry.
- `DELETE /api/admin/moderation/models/{slug}` — odrzuca prywatnego kandydata.

### Barcode

- `GET /api/admin/moderation/barcodes` — oczekujące propozycje; pole
  `replaces_barcode` pokazuje kod, który zostanie zastąpiony dla danego języka.
- `POST /api/admin/moderation/barcodes/{barcode_id}/approve` — zatwierdza kod;
  atomowo zastępuje dotychczasowy kod tego samego języka. Odpowiedź `204`.
- `DELETE /api/admin/moderation/barcodes/{barcode_id}` — odrzuca propozycję.

## Games — import operatorski

### `POST /api/games/import`

Auth: tak oraz wymagany `X-Import-Key`. Limit 1/h. `multipart/form-data`, pole
`file` z rozszerzeniem `.csv` lub `.json`, maksymalnie 32 MB. Batchowy upsert po
`bgg_id`; odpowiedź:

```json
{"total_rows":150000,"created":149000,"updated":500,"skipped":500}
```

Endpoint nie przyjmuje zwykłego klucza usera jako wystarczającej autoryzacji.
Sekret operatorski pochodzi z `GAMES_IMPORT_KEY` w Secret Managerze/.env.

## Celowo nieobecne

- endpointy `ratings`, matchmakingu i venues — to kolejne domeny;
- import ocen z BGG: `import_ratings=true` jest jawnie odrzucane do czasu ratings.
