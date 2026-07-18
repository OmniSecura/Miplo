# Moduł ratings

`ratings` przechowuje oceny i opcjonalne recenzje społeczności Miplo niezależnie
od ocen BoardGameGeek i od posiadania gry na półce. User może ocenić grę bez jej
posiadania, a usunięcie pozycji z półki nie usuwa opinii.

## Tożsamość gry i oceny

Frontend zawsze wskazuje grę publicznym `slug`, np. `brass-birmingham`. W tabeli
`game_ratings` relacja używa wewnętrznego `game_id` z FK do `games.id`. Klucz PK
jest niezmienny i wydajny w joinach; slug nie jest duplikowany w każdej ocenie.
Odpowiedzi API zwracają `game_slug` oraz losowy `public_id` UUID oceny, nigdy
`user_id`, `game_id` ani wewnętrznego SERIAL oceny.

## Reguły

- jedna ocena usera na grę (`UNIQUE(user_id, game_id)`);
- skala `1.0–10.0`, wyłącznie kroki `0.5`;
- ocena jest wymagana, recenzja opcjonalna (`10–5000` znaków);
- recenzja jest tekstem zwykłym: backend usuwa HTML oraz odrzuca znaki sterujące
  i kontrolki kierunku tekstu;
- `contains_spoilers` pozwala frontendowi zasłonić treść;
- ukryta przez moderatora ocena znika z publicznego API i wszystkich agregatów;
- zapis, edycja i usunięcie zawsze dotyczą usera z Firebase ID tokenu.

## Agregaty i próg zaufania

`games` przechowuje denormalizowane `miplo_rating`, `miplo_ratings_count` i
`miplo_reviews_count`. Serwis przelicza je po create/update/delete/hide/restore,
a import BGG robi jedno przeliczenie batchowe.

Surowa średnia jest przechowywana od pierwszej oceny, lecz API pokazuje
`miplo_rating` dopiero od trzech widocznych ocen. Wcześniej zwraca `null`, aby
pojedynczy głos nie wyglądał jak oficjalny wynik społeczności. `combined_rating`
jest średnią BGG i Miplo ważoną liczbą ocen; przed osiągnięciem progu odpowiada
ocenie BGG.

## Endpointy

| Metoda | Endpoint | Auth | Działanie |
|---|---|---|---|
| `POST` | `/api/games/{slug}/ratings` | tak | wystawienie oceny |
| `PUT` | `/api/games/{slug}/ratings` | tak | edycja własnej oceny/recenzji |
| `DELETE` | `/api/games/{slug}/ratings` | tak | usunięcie własnej oceny |
| `GET` | `/api/games/{slug}/ratings` | opcjonalny | publiczna lista ocen |
| `GET` | `/api/games/{slug}/ratings/summary` | opcjonalny | BGG, Miplo, rozkład i kontekst usera |
| `GET` | `/api/me/ratings` | tak | moje oceny |
| `GET` | `/api/me/ratings/stats` | tak | moje statystyki |
| `GET` | `/api/users/{tag}/ratings` | tak | publiczne oceny aktywnego usera |
| `POST` | `/api/games/{slug}/ratings/{rating_id}/report` | tak | zgłoszenie recenzji |

Zapisy mają limit `20/hour`, zgłoszenia `10/hour`, odczyty `60/minute`.
Lista recenzji ma maksymalny rozmiar strony 50 i filtry `with_review`,
`min_rating`, `max_rating` oraz sortowanie `newest | rating_desc | rating_asc`.

## Moderacja

Kolejka korzysta z tego samego mechanizmu co pozostała administracja:
`X-Admin-Key` albo aktywny Firebase user z `is_admin=true`.

- `GET /api/admin/moderation/reviews` — nierozwiązane zgłoszenia;
- `POST /api/admin/moderation/reviews/{rating_id}/hide` — ukrycie i przeliczenie;
- `POST /api/admin/moderation/reviews/{rating_id}/restore` — przywrócenie i przeliczenie.

`restore` można wywołać także dla nadal widocznej recenzji: oznacza wtedy
odrzucenie bezzasadnych zgłoszeń i usuwa ją z kolejki. Udane zgłoszenie usera
zwraca `{"message_code":"review_reported"}`, który frontend tłumaczy przez i18n.

Autor nie może zgłosić własnej recenzji (`cannot_report_own_review`), a jeden user nie może zgłosić
tej samej recenzji drugi raz. Różni userzy mogą zgłosić tę samą recenzję;
każde zgłoszenie zwiększa `report_count`. Kolejka moderatora jest sortowana
malejąco po liczbie nierozwiązanych zgłoszeń. W publicznych ścieżkach
`rating_id` jest UUID.

## BGG i półka

Odświeżenie BGG i tygodniowy CSV mają osobne jawne whitelisty; żadna nie zawiera
pola Miplo ani mediów/customizacji. `POST /api/me/shelf/import` z
`import_ratings=true` przenosi dostępne oceny BGG, zaokrąglając je do najbliższego
kroku 0.5 i oznaczając `source=bgg_import`. Istniejącej oceny usera nigdy nie
nadpisuje. Sortowanie półki po `miplo_rating` jest aktywne i respektuje próg 3.

## Migracje i testy

- PostgreSQL: `database/sql/migrations/0007_ratings.sql`;
- pełne DDL: `database/sql/tables/game_ratings/game_ratings.sql`;
- istniejące SQLite: `services/scripts/migrate_local_ratings.py local.db`.

Skrypt SQLite jest idempotentny, wykonuje kopię przez `sqlite3.backup()` i
sprawdza klucze obce. Reakcje „pomocna recenzja” są świadomie odłożone do
osobnego ticketu.
