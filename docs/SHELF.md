# Moduł shelf

Moduł `shelf` przechowuje informację „jakie gry posiada user” oraz dane jego
konkretnego egzemplarza. Nie kopiuje danych katalogowych gry i nie przechowuje
ocen użytkownika — oceny należą do osobnej domeny `ratings`.

## Granice odpowiedzialności

- `games` jest wspólnym katalogiem i źródłem tytułu, okładki, liczby graczy,
  czasu rozgrywki, ratingu BGG i modelu 3D;
- `shelf_items` łączy lokalnego usera z grą i przechowuje `lendable`, kaucję,
  warunki wypożyczenia, stan egzemplarza, prywatną notatkę i datę dodania;
- `user_id` zawsze pochodzi ze zweryfikowanego Firebase ID tokenu. Nie występuje
  w żadnym schemacie wejściowym;
- na półkę można dodać wyłącznie zweryfikowaną grę z publicznego katalogu;
- usunięcie usera albo gry usuwa powiązane wpisy przez `ON DELETE CASCADE`.

## Model i prywatność

Para `(user_id, game_id)` jest unikalna, więc user może mieć tylko jeden wpis
danej gry. `condition` jest stabilnym enumem API i przyjmuje `new`, `good`, `used`
albo `damaged`. W bazie pozostaje `VARCHAR(20)`, aby rozszerzenie listy nie wymagało
zmiany natywnego enumu PostgreSQL.

Widok własny zawiera prywatne `notes`. Widok cudzej półki nigdy go nie zwraca.
`lending_deposit` i `lending_notes` są publiczne tylko wtedy, gdy `lendable=true`;
przy `lendable=false` backend zwraca dla nich `null`, nawet jeśli user zachował
wcześniejsze ustawienia na później. Oba widoki zwracają katalogowy czas rozgrywki
jako `game_playing_time`.

## Endpointy

Wszystkie endpointy półki wymagają aktywnego usera.

| Metoda | Endpoint | Znaczenie |
|---|---|---|
| `GET` | `/api/me/shelf` | moja półka, filtry, sortowanie i paginacja |
| `POST` | `/api/me/shelf` | dodanie zweryfikowanej gry |
| `PUT` | `/api/me/shelf/{game_slug}` | edycja mojego egzemplarza |
| `DELETE` | `/api/me/shelf/{game_slug}` | usunięcie gry z mojej półki |
| `GET` | `/api/me/shelf/stats` | agregaty mojej półki |
| `POST` | `/api/me/shelf/import` | import posiadanych gier z kolekcji BGG |
| `GET` | `/api/users/{tag}/shelf` | publiczny, bezpiecznie ograniczony widok cudzej półki |

`GET /api/me/shelf` przyjmuje `page`, `size`, `lendable`, `search`, `condition`,
`players` i `sort`. Enum sortowania zawiera `added_at`, `title`, `game_rating`
oraz `miplo_rating`. Sort Miplo jest aktywny; gry poniżej progu trzech ocen mają
publiczne `game_miplo_rating=null` i są ustawiane za zaufanymi wynikami.

Przykład dodania gry:

```json
{
  "game_slug": "brass-birmingham",
  "lendable": true,
  "lending_deposit": "50.00",
  "lending_notes": "Odbiór osobisty, maksymalnie tydzień.",
  "condition": "good",
  "notes": "Prywatna notatka właściciela."
}
```

Pola nieznane są odrzucane. Kaucja mieści się w zakresie `0.00–9999.00` i ma
maksymalnie dwa miejsca po przecinku. Notatki mają maksymalnie 500 znaków oraz
odrzucają znaki sterujące i kontrolki kierunku tekstu.

API półki nie przyjmuje ani nie zwraca technicznego `games.id`. Frontend zawsze
korzysta z unikalnego `game_slug` otrzymanego z katalogu lub szczegółów gry.
Wewnętrzny `game_id` pozostaje wyłącznie kluczem obcym w PostgreSQL.

## Kontekst półki na stronie gry

`GET /api/games/{slug}` pozostaje publiczny, ale obsługuje opcjonalny token.
Bez nagłówka autoryzacji zwraca:

```json
{
  "on_my_shelf": false,
  "my_shelf_item": null
}
```

Z poprawnym tokenem pola opisują wyłącznie półkę aktualnego usera. Nagłówek
`Authorization` obecny, lecz niepoprawny, nie jest traktowany jako anonimowy —
kończy się `401`.

## Import kolekcji BGG

`POST /api/me/shelf/import` przyjmuje:

```json
{
  "bgg_username": "BoardGamer_1",
  "import_ratings": false
}
```

Nick jest ograniczony do 50 znaków ASCII `[A-Za-z0-9_]`. Import:

1. pobiera posiadane gry z kolekcji BGG;
2. usuwa duplikaty BGG ID;
3. pobiera brakujące lub stare szczegóły paczkami po maksymalnie 20 ID;
4. zachowuje 5 sekund odstępu między zewnętrznymi requestami;
5. pomija gry już obecne na półce;
6. zatwierdza wszystkie nowe wpisy jednym końcowym commitem.

Limit operacji wynosi `2/hour`, a budżet czasu 180 sekund. Po przekroczeniu czasu
zwracany jest bezpiecznie częściowy wynik z licznikami `imported`, `skipped` i
`failed`. Import nigdy nie usuwa istniejących pozycji. Wyścig z równoległym
„Dodaj na półkę” jest izolowany SAVEPOINT-em i liczy się jako `skipped`.

`import_ratings=true` przenosi dostępne oceny usera z BGG. Wynik jest zaokrąglany
do kroku 0.5, zapisywany ze `source=bgg_import` i nigdy nie nadpisuje istniejącej
oceny Miplo. `ratings_imported` podaje liczbę faktycznie dodanych ocen.

## Zapytania i wydajność

Listowanie wykonuje jedno zapytanie agregujące `COUNT` i jedno zapytanie danych z
jawnym JOIN-em `shelf_items × games`, niezależnie od liczby pozycji. Nie ładuje
galerii, barcode, typów ani pozostałych relacji gry, dzięki czemu nie występuje
N+1. Statystyki `COUNT`, liczba wypożyczalnych i suma czasu rozgrywek są liczone
w jednym zapytaniu SQL.

## Migracje

- pełne DDL: `database/sql/tables/shelf_items/shelf_items.sql`;
- migracja PostgreSQL: `database/sql/migrations/0006_shelf_items.sql`;
- lokalne `ENV=local`: tabela zostanie utworzona przez `create_all` przy starcie;
  SQLite ma jawnie włączone `PRAGMA foreign_keys=ON`, aby CASCADE działało także
  lokalnie.


## Testy

```powershell
services\.venv\Scripts\python.exe -B -m unittest services.tests.test_shelf -v
```

Testy modułu shelf pokrywają CRUD i ownership, prywatność, filtry, brak N+1,
statystyki, opcjonalny auth, kontekst gry, batchowy import ocen,
moderację katalogu oraz kaskadowe usuwanie.
