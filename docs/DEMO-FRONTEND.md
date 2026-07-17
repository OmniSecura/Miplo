# Miplo — brief kompletnego demo frontendu

Ten dokument można przekazać Claude Design jako źródło wymagań do zbudowania
działającego demo frontendu Miplo. Opisuje wyłącznie funkcje dostępne użytkownikowi
końcowemu. Nie należy tworzyć panelu administracyjnego, UI moderacji ani ujawniać
sekretów operatorskich.

## Gotowy prompt dla Claude Design

> Zaprojektuj i zaimplementuj responsywne demo aplikacji Miplo na podstawie całego
> poniższego dokumentu. Miplo to cyfrowa półka i społeczność dla graczy planszowych.
> Frontend ma korzystać z istniejącego REST API FastAPI oraz Firebase Auth.
> Przygotuj dopracowane widoki desktop i mobile, kompletne stany loading/empty/error,
> walidację formularzy i warstwę klienta API. Nie twórz panelu moderatora ani
> interfejsu operatorskiego. Nie wymyślaj endpointów, których nie ma w kontrakcie.
> Jeśli backend nie jest dostępny podczas projektowania, dodaj przełączalny mock
> adapter zachowujący dokładnie te same modele odpowiedzi.

## 1. Produkt i charakter interfejsu

Miplo jest aplikacją do odkrywania gier planszowych, oglądania szczegółów pudełka,
tworzenia społecznościowych wpisów oraz proponowania zdjęć, kodów kreskowych i
teksturyzowanych modeli 3D pudełek.

Interfejs powinien być:

- nowoczesny, przyjazny i kolekcjonerski, ale nie infantylny;
- czytelny na telefonie — skanowanie barcode i przesyłanie zdjęć będą często
  wykonywane mobilnie;
- oparty na kartach gier z dużymi okładkami, czytelną oceną BGG i liczbą graczy;
- dostępny: kontrast WCAG AA, pełna obsługa klawiatury, widoczny focus, etykiety
  formularzy i tekstowe alternatywy dla ikon;
- przygotowany do i18n od pierwszego dnia. Teksty UI mają pochodzić z kluczy
  tłumaczeń, a nie być wpisane bezpośrednio w komponentach. Na demo wystarczy język
  polski.

Sugerowany stack: React + TypeScript, React Router, TanStack Query, React Hook Form,
Zod, Firebase Web SDK oraz React Three Fiber/Three.js do podglądu GLB. Można użyć
innego równoważnego stacku, jeżeli zachowa ten sam kontrakt.

## 2. Zasady integracji

- Bazowy URL API pochodzi ze zmiennej środowiskowej, np. `VITE_API_BASE_URL`.
- Endpointy domenowe mają prefix `/api`; `/health` nie ma prefixu.
- Firebase Web SDK realizuje rejestrację, logowanie, reset hasła i odświeżanie
  tokenu. Backend nie ma endpointu rejestracji ani logowania.
- Do chronionych requestów wysyłaj:

```http
Authorization: Bearer <Firebase ID token>
```

- Po zalogowaniu wywołaj `GET /api/me`. Pierwsze poprawne wywołanie automatycznie
  tworzy lokalny profil Miplo.
- Przy `401 token_expired` odśwież Firebase ID token jeden raz i ponów request.
- Przy kolejnym `401` wyloguj lokalną sesję i pokaż ekran logowania.
- `429` obsłuż komunikatem i odliczaniem na podstawie `Retry-After`, jeżeli nagłówek
  jest dostępny.
- Nie zapisuj Firebase ID tokenu w `localStorage`. Korzystaj z mechanizmu sesji
  Firebase SDK.
- Nigdy nie umieszczaj we frontendzie `ADMIN_API_KEY`, `GAMES_IMPORT_KEY`, klucza
  Firebase Admin ani tokenu BGG. Konfiguracja Firebase Web jest publiczną
  konfiguracją klienta i nie zastępuje reguł bezpieczeństwa.

## 3. Nawigacja i ekrany

### Publiczne

1. Landing page
   - krótka prezentacja Miplo;
   - wyszukiwarka gier;
   - sekcja popularnych/najwyżej sklasyfikowanych gier z katalogu;
   - widoczna atrybucja „Powered by BoardGameGeek” z linkiem do BGG.

2. Katalog gier `/games`
   - grid/lista kart;
   - wyszukiwanie po tytule;
   - filtry: liczba graczy, typ gry, źródło `bgg/custom`, dodatki tak/nie;
   - paginacja i wybór 20/50/100 elementów;
   - filtry zapisane w query string URL;
   - skeletony, pusty wynik i retry po błędzie.

3. Wyniki wyszukiwania `/search?q=...`
   - pokaż wszystkie wyniki, nawet gdy mają podobne nazwy, wraz z rokiem;
   - wynik istniejący lokalnie otwiera stronę po zwróconym `slug`;
   - wynik z BGG, którego jeszcze nie ma lokalnie, ma `bgg_id` i wymaga zalogowania,
     aby pobrać pełne dane;
   - nigdy nie wyliczaj slugu we frontendzie — źródłem prawdy jest backend.

4. Szczegóły gry `/games/:slug`
   - okładka, tytuł, rok, rating, waga, ranking BGG, liczba ocen;
   - zakres graczy, czas rozgrywki, typy, opis i instrukcja;
   - wszystkie zaakceptowane barcode z oznaczeniem języka;
   - galeria zaakceptowanych zdjęć;
   - podgląd modelu GLB, jeżeli `model_3d_url` jest dostępny;
   - przy braku GLB pokaż lekki proceduralny model pudełka albo placeholder;
   - CTA logowania dla działań społecznościowych;
   - formularze propozycji ukryj, gdy
     `community_contributions_enabled === false`.

5. Profil publiczny `/u/:tag`
   - `display_name`, `tag`, avatar, miasto, bio i data dołączenia;
   - nie oczekuj ani nie pokazuj wewnętrznego ID użytkownika.

6. Skaner barcode `/scan`
   - kamera mobilna lub ręczne wpisanie kodu;
   - po rozpoznaniu wywołaj lookup;
   - znaleziony kod otwiera grę po `slug` z odpowiedzi;
   - brak kodu prowadzi do wyszukiwarki, a po wyborze gry otwiera formularz
     propozycji barcode z zachowanym zeskanowanym numerem.

### Po zalogowaniu

7. Logowanie/rejestracja `/auth`
   - Firebase Auth: email/hasło i ewentualni skonfigurowani providerzy;
   - reset hasła realizowany wyłącznie przez Firebase;
   - po rejestracji ustaw `displayName` w Firebase przed pierwszym `GET /api/me`,
     jeśli użytkownik podał nazwę na formularzu;
   - tag tworzy backend automatycznie. Użytkownik może go później zmienić.

8. Mój profil `/me`
   - edycja `tag`, `display_name`, `city`, `bio`;
   - osobny upload/usunięcie avatara;
   - data dołączenia;
   - sekcja konta: dezaktywacja, ponowna aktywacja i trwałe usunięcie;
   - trwałe usunięcie wymaga wyraźnego potwierdzenia, np. wpisania `USUŃ`.

9. Dodawanie gry custom `/games/new`
   - formularz multipart: tytuł, opis, gracze, czas, rok, typy, wymiary,
     bezpieczny link HTTPS do instrukcji i opcjonalna okładka;
   - `game_types` wysyłaj jako JSON string, np. `["Euro","Ekonomiczna"]`;
   - slug generuje backend, nie pokazuj pola slug;
   - po `201` pokaż ekran „Gra oczekuje na moderację”. Nie publikuj jej od razu;
   - aktualnie nie istnieje endpoint „moje zgłoszenia”, więc po odświeżeniu strony
     nie można pobrać listy oczekujących gier użytkownika. Nie symuluj tej funkcji
     jako działającej z prawdziwym API.

10. Edycja własnej gry custom
    - używa `PUT /api/games/{slug}` jako multipart;
    - dostępna tylko właścicielowi customowej gry;
    - zmiana ponownie kieruje grę do moderacji i może czasowo ukryć ją w katalogu;
    - nowy slug zawsze bierz z odpowiedzi po zapisie.

11. Galeria społecznościowa
    - upload jednego JPEG/PNG/WEBP do 2 MB i opcjonalny podpis;
    - po `202` pokaż status „oczekuje na akceptację”;
    - nie dodawaj zdjęcia do publicznej galerii przed akceptacją;
    - odpowiedź zwraca `public_id`, który można wykorzystać do wycofania własnej
      propozycji.

12. Propozycja barcode
    - formularz ma pole barcode i dropdown języka;
    - dozwolone języki: `pl` — Polski, `en` — Angielski;
    - wysyłaj `application/x-www-form-urlencoded`, nie JSON;
    - backend sprawdza format i sumę kontrolną EAN-8, UPC-A lub EAN-13;
    - propozycja ma status `pending` i staje się publiczna dopiero po moderacji.

13. Generator modelu pudełka 3D
    - jeden formularz z sześcioma wymaganymi zdjęciami: `front`, `back`, `left`,
      `right`, `top`, `bottom`;
    - pokaż graficzną instrukcję znaczenia każdej ścianki;
    - każde zdjęcie: JPEG/PNG/WEBP, maksymalnie 2 MB;
    - dla każdej ścianki dropdown rotacji: `0`, `90`, `180`, `270` stopni;
    - wartości rotacji wysyłaj jako tekstowe pola multipart;
    - przed wysłaniem pokaż miniatury i pozwól poprawić orientację;
    - po `202` polluj `GET /api/games/{slug}` z rosnącym interwałem, maksymalnie
      przez kilka minut;
    - statusy: `pending`, `processing`, `awaiting_review`, `ready`, `failed`;
    - `awaiting_review` oznacza poprawnie wygenerowany prywatny kandydat, nie model
      publiczny. Jeżeli istniał poprzedni zaakceptowany model, nadal go pokazuj;
    - nie renderuj prywatnego modelu kandydata — publiczne API nie zwraca jego URL.

## 4. Endpointy używane przez demo

### System i użytkownicy

| Metoda | Endpoint | Auth | Zastosowanie |
|---|---|---:|---|
| GET | `/health` | nie | healthcheck i atrybucja BGG |
| GET | `/api/me` | tak | mój profil / utworzenie lokalnego profilu |
| PUT | `/api/me` | tak | edycja mojego profilu, JSON |
| POST | `/api/me/avatar` | tak | upload avatara, multipart |
| DELETE | `/api/me/avatar` | tak | usunięcie avatara |
| POST | `/api/me/deactivate` | tak | odwracalna dezaktywacja |
| POST | `/api/me/activate` | tak | reaktywacja konta |
| DELETE | `/api/me` | tak | trwałe usunięcie konta |
| GET | `/api/users/{tag}` | nie | profil publiczny |

### Gry

| Metoda | Endpoint | Auth | Zastosowanie |
|---|---|---:|---|
| GET | `/api/games/search?q={query}` | nie | lokalne wyniki lub proxy BGG |
| GET | `/api/games` | nie | zweryfikowany katalog i filtry |
| GET | `/api/games/{slug}` | nie | szczegóły zweryfikowanej gry |
| GET | `/api/games/bgg/{bgg_id}` | tak | pobranie pełnych danych BGG do cache |
| GET | `/api/games/by-barcode/{barcode}` | nie | lookup zeskanowanego kodu |
| POST | `/api/games` | tak | utworzenie gry custom, multipart |
| PUT | `/api/games/{slug}` | tak | edycja własnej gry custom, multipart |
| DELETE | `/api/games/{slug}` | tak | usunięcie własnej gry custom |
| POST | `/api/games/{slug}/images` | tak | propozycja zdjęcia galerii |
| DELETE | `/api/games/{slug}/images/{public_id}` | tak | wycofanie dozwolonego zdjęcia |
| POST | `/api/games/{slug}/barcodes` | tak | propozycja barcode per język |
| POST | `/api/games/{slug}/3d-model` | tak | propozycja teksturowanego GLB |
| DELETE | `/api/games/{slug}/3d-model` | tak | wycofanie propozycji modelu |

Nie używaj w demo:

- żadnego endpointu `/api/admin/moderation/*`;
- `POST /api/games/import` — to chronione narzędzie operatorskie;
- nieistniejącego `/api/me/collection/import`;
- planowanych, ale jeszcze niezaimplementowanych domen shelf, matchmaking i venues.

## 5. Najważniejsze modele odpowiedzi

### UserProfile

```json
{
  "tag": "omnisecura",
  "email": "user@example.com",
  "display_name": "Bartosz",
  "city": "Kraków",
  "bio": "Lubię ciężkie euro.",
  "avatar_url": "https://storage.googleapis.com/.../avatar.webp?v=...",
  "created_at": "2026-07-18T12:00:00Z"
}
```

`UserPublic` nie zawiera `email`. Żaden profil nie zawiera `id`, `firebase_uid`,
`is_active`, `is_admin` ani `updated_at`.

### Wynik wyszukiwania

```json
{
  "bgg_id": 224517,
  "slug": null,
  "title": "Brass: Birmingham",
  "year_published": 2018,
  "cover_url": null,
  "in_database": false
}
```

Jeżeli `in_database=true`, odpowiedź ma lokalny `slug`. Jeżeli `false`, po kliknięciu
zalogowany klient wywołuje `/api/games/bgg/{bgg_id}` i pobiera slug z odpowiedzi.

### GameDetail — pola istotne dla UI

```json
{
  "id": 1,
  "bgg_id": 224517,
  "slug": "brass-birmingham",
  "title": "Brass: Birmingham",
  "year_published": 2018,
  "min_players": 2,
  "max_players": 4,
  "playing_time": 120,
  "rating": "8.56",
  "weight": "3.90",
  "cover_url": "https://cf.geekdo-images.com/...",
  "game_types": ["Euro", "Economic"],
  "description": "...",
  "instruction_url": null,
  "box_width": "29.50",
  "box_height": "29.50",
  "box_depth": "7.00",
  "model_3d_url": null,
  "model_status": null,
  "source": "bgg",
  "is_verified": true,
  "bgg_rank": 1,
  "users_rated": 59269,
  "is_expansion": false,
  "barcodes": [
    {"barcode": "5901549927658", "language_code": "pl"}
  ],
  "images": [
    {
      "public_id": "9bea5aa0-814a-4f4a-a2dd-b48fd78c601e",
      "image_url": "https://storage.googleapis.com/.../image.webp",
      "caption": "Komponenty w pudełku",
      "created_at": "2026-07-18T12:00:00Z"
    }
  ],
  "created_at": "2026-07-18T12:00:00Z",
  "community_contributions_enabled": true
}
```

Pola liczbowe typu `Decimal` mogą przyjść w JSON jako tekst — klient powinien
bezpiecznie je formatować, nie zakładając wyłącznie typu JavaScript `number`.

### Paginacja

```json
{
  "items": [],
  "total": 142,
  "page": 1,
  "size": 20,
  "pages": 8
}
```

## 6. Obsługa błędów i stanów

Docelowy błąd domenowy:

```json
{
  "detail": {
    "error_code": "game_not_found",
    "details": {}
  }
}
```

Frontend mapuje `error_code` na klucze i18n. Nie pokazuje użytkownikowi surowych
wyjątków ani technicznego `details`. Obsłuż co najmniej:

- `unauthorized`, `invalid_token`, `token_expired`;
- `user_inactive`, `forbidden`, `not_game_owner`;
- `game_not_found`, `barcode_not_found`, `game_title_exists`;
- `invalid_barcode_format`, `game_barcode_exists`, `barcode_proposal_pending`;
- `contributions_locked`, `model_already_processing`, `gallery_limit_reached`;
- `file_too_large`, `invalid_file_type`, `payload_too_large`;
- `bgg_not_configured`, `bgg_unavailable`, `bgg_rate_limited`;
- `rate_limit_exceeded`, `internal_error`.

Aktualnie błędy walidacji frameworka `422` mogą mieć jeszcze domyślny format
FastAPI `{"detail":[...]}`. Klient powinien tymczasowo obsłużyć oba kształty i
przypisać drugi do ogólnego klucza `validation_error`.

Nie używaj toastu do wszystkiego. Błąd pola pokazuj pod polem, błąd strony w
dedykowanym stanie, a toast stosuj do potwierdzeń i błędów akcji w tle.

## 7. Bezpieczeństwo po stronie frontendu

- Dane tekstowe renderuj jako tekst, nigdy przez `dangerouslySetInnerHTML`.
- URL-e z API przekazuj tylko do oczekiwanych komponentów obraz/PDF/GLB; nie twórz
  z nich wykonywalnego HTML.
- Walidacja klienta poprawia UX, ale backend pozostaje źródłem prawdy.
- Przed uploadem sprawdź MIME i rozmiar, ale nie zakładaj, że zastępuje to kontrolę
  backendu.
- Dla lokalnych preview używaj `URL.createObjectURL` i zawsze wykonuj
  `URL.revokeObjectURL`.
- Nie loguj tokenów, pełnych odpowiedzi auth ani sekretów do konsoli/analityki.
- Akcje destrukcyjne wymagają potwierdzenia; przycisk blokuj podczas requestu,
  aby uniknąć podwójnych wysłań.
- Nie pokazuj kontrolek społecznościowych, gdy konto jest zdezaktywowane albo gra
  ma zablokowane kontrybucje.

## 8. Mocki do wersji demonstracyjnej

Mock adapter powinien mieć ten sam interfejs co prawdziwy klient API i realistyczne
opóźnienie 250–700 ms. Przygotuj:

- minimum 12 gier, kilka o podobnej nazwie, BGG i custom;
- grę z pełnym GLB, grę bez modelu i grę w `processing`;
- galerię, brak galerii i zablokowane kontrybucje;
- znaleziony i nieznaleziony barcode;
- profile aktywnego użytkownika i publiczny profil innego gracza;
- przełączane scenariusze 401, 404, 409, 422 i 429.

Mocki muszą dać się wyłączyć jedną zmienną środowiskową. Nie mieszaj mockowanych
obiektów z prawdziwym Firebase Auth w sposób, który mógłby trafić na produkcję.

## 9. Kryteria ukończenia demo

- Wszystkie publiczne ekrany działają bez logowania.
- Firebase Auth i automatyczne dołączanie tokenu działają dla tras chronionych.
- Search poprawnie rozróżnia wynik lokalny od wyniku BGG i nigdy nie zgaduje slugu.
- Katalog zachowuje filtry i paginację w URL.
- Szczegóły gry obsługują brakujące dane, galerię, barcode i model GLB.
- Custom game wysyła poprawny multipart i pokazuje oczekiwanie na moderację.
- Galeria, barcode oraz model 3D mają jasny status zgłoszenia.
- Formularz 3D wymaga sześciu zdjęć i oferuje rotacje 0/90/180/270.
- Język barcode jest dropdownem Polski/Angielski.
- Profil nie pokazuje wewnętrznych identyfikatorów.
- Nie ma panelu moderatora, klucza admina ani narzędzia importu katalogu.
- Interfejs jest responsywny, dostępny i ma komplet stanów loading/empty/error.

