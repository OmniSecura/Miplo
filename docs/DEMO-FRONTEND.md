# Miplo — wytyczne UI/UX aplikacji mobilnej

Przewodnik **krok po kroku** dla AI/projektanta budującego frontend natywnej
**aplikacji mobilnej** Miplo. Kolejność faz jest wiążąca: buduj je po kolei, bo
każda następna opiera się na poprzedniej. Językiem całego interfejsu jest polski.

Miplo to cyfrowa półka i społeczność dla graczy planszowych: odkrywanie gier,
prowadzenie własnej kolekcji, udostępnianie gier do wypożyczenia, ocenianie oraz
proponowanie zdjęć, kodów kreskowych i teksturowanych modeli 3D pudełek.

Zakres **nie** obejmuje panelu administratora, interfejsu moderacji, importu
katalogu ani żadnych sekretów — te funkcje żyją poza aplikacją mobilną.

Struktura dokumentu: §1 zasady → §2 paleta i design system → §3 nawigacja →
§4 sesja/API → **§5 plan budowy fazami (główna część)** → §6 enumy →
§7 modele odpowiedzi → §8 błędy → §9 poza zakresem → §10 kryteria ukończenia.

---

## 1. Zasady projektowe (mobile)

- **Mobile-first, kciukiem.** Główne akcje w dolnej, dosięgalnej strefie ekranu.
  Respektuj safe-area (notch, systemowy pasek nawigacji).
- **Aparat to pierwszorzędne narzędzie** — skanowanie kodów i zdjęcia pudełek to
  codzienne czynności; projektuj je jako płynne, natywne przepływy.
- **Karty gier z dużymi okładkami** są sercem UI (okładka 1:1, wyraźna ocena,
  liczba graczy, typy jako chipy).
- **Gesty natywne:** pull-to-refresh na listach, swipe-back, swipe na pozycji
  półki (edytuj / usuń), **bottom sheet** zamiast desktopowych modali.
- **Nieskończone przewijanie** (infinite scroll) zamiast numerowanej paginacji —
  kolejne strony API doładowują się przy dojściu do końca listy.
- **Haptyka** przy kluczowych akcjach (dodanie na półkę, wysłanie oceny, sukces).
- **Dostępność:** kontrast WCAG AA, Dynamic Type, etykiety dla czytników ekranu,
  cele dotykowe min. 44×44 pt.
- **i18n od pierwszego dnia** — teksty z kluczy tłumaczeń, nie na sztywno.
- **Motyw jasny i ciemny** — patrz paleta w §2.

---

## 2. System projektowy — paleta „Wood"

Ciepła, drewniana, kolekcjonerska. Odcienie orzecha, terakoty, miodu i płótna;
akcenty natury (mech, cegła, ochra) do statusów.

### Motyw jasny

| Rola | Nazwa | Hex | Użycie |
|---|---|---|---|
| Primary | Terakota | `#8B4A2B` | przyciski główne, aktywna zakładka, linki |
| Primary — pressed | Orzech ciemny | `#6F3A22` | stan naciśnięty |
| Primary — tło subtelne | Piaskowiec | `#F3E7DD` | chipy aktywne, tło zaznaczeń |
| Akcent (oceny) | Miód / Ochra | `#D89A3E` | gwiazdki ocen, wyróżnienia |
| Akcent — tło subtelne | Miód jasny | `#FBEFD3` | |
| Tekst główny | Espresso | `#2C2016` | nagłówki, treść |
| Tekst drugorzędny | Taupe | `#6B5A4A` | metadane, podpisy |
| Tekst wyciszony | Len szary | `#9B8B79` | placeholdery |
| Tło ekranu | Płótno / Krem | `#FAF5EE` | tło aplikacji |
| Powierzchnia / karta | Biel ciepła | `#FFFDFA` | karty, bottom sheet, pasek zakładek |
| Obramowania / dividery | Piasek | `#E7DBCD` | |
| Sukces | Mech | `#5B7A4A` | tło `#E8EFE0` — „wypożyczalna", potwierdzenia |
| Błąd | Cegła | `#A33A2E` | tło `#F6E2DE` — błędy, akcje destrukcyjne |
| Ostrzeżenie | Ochra ziemista | `#B5822A` | tło `#FBEFD3` — „oczekuje na moderację" |
| Informacja | Łupek ciepły | `#6E6270` | tło `#ECE6EC` — podpowiedzi neutralne |
| Badge oceny BGG | Espresso | `#2C2016` | tekst biały |
| Badge oceny Miplo | Terakota | `#8B4A2B` | tekst biały |

### Motyw ciemny (te same role)

| Rola | Hex |
|---|---|
| Tło ekranu | `#1E160F` |
| Powierzchnia / karta | `#2A2018` |
| Obramowania | `#3A2E23` |
| Tekst główny | `#F0E6DA` |
| Tekst drugorzędny | `#C3B2A0` |
| Primary (jaśniejsza terakota) | `#C77B4E` (tekst na niej: espresso `#2C2016`) |
| Akcent (miód) | `#E0A94E` |
| Sukces / Błąd / Ostrzeżenie | `#7A9A66` / `#C85A4C` / `#D19A45` |

### Typografia, kształty, komponenty

- Krój **Inter** (lub systemowy: SF Pro / Roboto). Nagłówki 600, tekst 400/500.
  Skala 28 / 22 / 18 / 16 / 14 / 12 pt. Wspieraj Dynamic Type.
- Karty: radius 16, cień subtelny `0 2 8 rgba(44,32,22,0.08)`. Inputy/przyciski:
  radius 12. Chipy: pill. Bottom sheet: górne rogi 20 + uchwyt.
- Okładki gier: 1:1, radius 12. Placeholder gdy `cover_url=null`: ikona pionka
  na tle Piaskowiec `#F3E7DD`.
- Komponenty bazowe: pasek zakładek, nagłówek ekranu z akcją, przycisk
  (primary / secondary / ghost / destructive), pole z etykietą i błędem pod
  polem, picker (bottom sheet), chip filtra, karta gry, karta pozycji półki,
  toast/snackbar, bottom sheet potwierdzenia, skeleton loader, pusty stan
  (ilustracja + tekst + CTA), kontrolka oceny 1–10 z połówkami, FAB.

---

## 3. Nawigacja

Dolny **pasek 4 zakładek**, każda to niezależny stos nawigacyjny (lepiej nawet kółko kllikamy, jest animacja jak leci na środek i wokół niego pojawiają się kółka z opcjami które wymieniłem, lub lekko oddala się od prawego dolnego rogu iwtedy się wokół niego pojawiają):

1. **Odkrywaj** — katalog, wyszukiwanie, szczegóły gry, profile publiczne.
2. **Skaner** — skanowanie kodu kreskowego.
3. **Półka** — moja kolekcja (wymaga logowania).
4. **Profil** — mój profil, moje oceny, konto (wymaga logowania).

Przeglądanie (Odkrywaj, Skaner) działa **bez logowania**. Wejście na Półkę lub
Profil bez sesji, a także każda akcja społecznościowa (dodanie na półkę, ocena,
propozycja) otwiera ekran logowania jako bramkę. Atrybucja „Powered by
BoardGameGeek data" (link do boardgamegeek.com) w zakładce Profil → „O aplikacji"
oraz w stopce ekranu szczegółów gry.

---

## 4. Uwierzytelnianie i sesja

- Logowanie, rejestracja i reset hasła realizuje **Firebase Auth (mobile SDK)**.
  Backend nie ma własnych endpointów logowania.
- Do chronionych requestów dołączaj nagłówek
  `Authorization: Bearer <Firebase ID token>`.
- Po zalogowaniu wywołaj **`GET /api/me`** — pierwsze poprawne wywołanie zakłada
  lokalny profil Miplo (tag generuje backend).
- `401 token_expired` → odśwież token raz i ponów. Kolejny `401` → wyloguj sesję
  i pokaż logowanie. `429` → komunikat z odliczaniem z nagłówka `Retry-After`.
- Token trzymaj wyłącznie w sesji Firebase SDK / bezpiecznym magazynie
  systemowym (Keychain / Keystore). Bazowy URL API z konfiguracji builda;
  endpointy domenowe mają prefix `/api`, `/health` nie ma prefiksu.
- Nigdy nie umieszczaj w aplikacji `ADMIN_API_KEY`, klucza Firebase Admin ani
  tokenu BGG.

---

## 5. Plan budowy — fazy

Buduj fazami po kolei. Każda faza kończy się listą „Gotowe, gdy". Format ekranu:
**Zawartość → Interakcje → Stany → Endpointy** („auth: tak" = wymagany token).

### FAZA 0 — Fundament

**Cel.** Szkielet, który każda następna faza tylko wypełnia treścią.

- Design system z §2 jako komponenty wielokrotnego użytku (przyciski, pola,
  karty, chipy, toast, bottom sheet, skeleton, pusty stan, kontrolka oceny).
- Motyw jasny i ciemny (przełączany za systemem).
- Dolny pasek 4 zakładek + stosy nawigacji (§3); zakładki Półka/Profil pokazują
  bramkę logowania, gdy brak sesji.
- Klient API: bazowy URL, wstrzykiwanie tokenu, mapowanie `error_code` → i18n
  (§8), globalna obsługa `401`/`429`, warstwa mocków dająca się wyłączyć jedną
  flagą (§7 kształty).
- Ekran „zdrowia/offline" oparty o `GET /health` (opcjonalnie na splashu).

**Endpointy.** `GET /health` — auth: nie. Zwraca `{status, database, attribution}`.

**Gotowe, gdy:** aplikacja startuje, przełącza motyw, pokazuje 4 zakładki i
poprawnie mapuje błędy z mocka na komunikaty.

### FAZA 1 — Autoryzacja

**Cel.** Wejście w konto: logowanie, rejestracja, reset, założenie profilu.

**Ekran: Logowanie / Rejestracja (bramka).**
- Zawartość: zakładki „Zaloguj" / „Zarejestruj"; e-mail + hasło; „Nie pamiętam
  hasła" (reset przez Firebase). Przy rejestracji opcjonalna nazwa wyświetlana.
- Interakcje: walidacja pól na żywo; przycisk zablokowany w trakcie requestu;
  po sukcesie logowania → `GET /api/me` i przejście do aplikacji.
- Przy rejestracji ustaw `displayName` w Firebase **przed** pierwszym
  `GET /api/me`. `tag` tworzy backend automatycznie (user zmieni go później).
- Stany: błąd Firebase (złe hasło, zajęty e-mail) pod polem; spinner; offline.

**Endpointy.**
- Logowanie/rejestracja/reset — **Firebase Auth SDK**, bez backendu.
- `GET /api/me` — auth: tak. Zakłada/pobiera profil. Zwraca
  `{tag, email, display_name, city, bio, avatar_url, created_at}` (bez `id`,
  `firebase_uid`, `is_admin`, `is_active`, `updated_at`).

**Gotowe, gdy:** można się zarejestrować, zalogować, zresetować hasło i po
zalogowaniu istnieje profil Miplo z auto-tagiem; wygaśnięcie tokenu wraca na
ekran logowania.

### FAZA 2 — Katalog (wszystkie gry)

**Cel.** Przeglądanie i wyszukiwanie gier. Publiczne, bez logowania. To rdzeń
zakładki **Odkrywaj**.

**Ekran: Katalog (start zakładki Odkrywaj).**
- Zawartość: nagłówek „Odkrywaj" + ikona wyszukiwania + ikona filtra; rząd
  aktywnych chipów filtrów (z „×"); lista kart gier (pseudo-3D pudełko, tytuł,
  rok, badge oceny BGG, badge oceny Miplo jeśli jest, zakres graczy, typy jako chipy);
  na górze bez filtrów sekcja „Najwyżej oceniane".
- Karta używa `BoxCover3D(frontUrl?, sideUrl?, topUrl?, coverUrl?, color?)`.
  Priorytet renderowania: komplet `box_face_front_url` / `box_face_side_url` /
  `box_face_top_url`; gdy któregokolwiek brakuje, użyj `cover_url` na froncie
  oraz koloru klienta na boku i wieczku. Nie pobieraj GLB dla kafelka listy.
- Interakcje: pull-to-refresh; infinite scroll; tap karty → szczegóły gry
  (Faza 4 — na start może być czytelny szkielet); FAB „+" (tylko zalogowany) →
  dodanie gry custom (Faza 5).
- Filtry (bottom sheet): liczba graczy (1–50), typ gry (multi-select z enuma §6),
  źródło (bgg/custom), przełącznik „pokaż dodatki". Filtry w stanie ekranu.
- Stany: skeleton kart; pusty „Brak gier dla tych filtrów" + „Wyczyść filtry";
  błąd + „Ponów".

**Ekran: Wyszukiwanie.**
- Zawartość: pole wyszukiwania (autofocus); lista wyników z okładką, tytułem,
  rokiem, znacznikiem źródła. Wynik lokalny (ma `slug`) → otwiera grę. Wynik
  z BGG (`in_database=false`, ma `bgg_id`, `slug=null`) → przycisk „Pobierz
  dane" (wymaga logowania) — **materializuje** grę i przechodzi do szczegółów po
  slugu z odpowiedzi.
- Interakcje: debounce ~300 ms; pokazuj wszystkie trafienia z rokiem.
  **Nigdy nie licz slugu w aplikacji** — bierz go z backendu.
- Stany: podpowiedź „wpisz min. 2 znaki"; spinner w polu; pusty „Brak wyników".

**Endpointy.**
- `GET /api/games` — auth: nie. Query: `page` (≥1), `size` (1–100), `search`
  (2–100), `players` (1–50), `game_type` (slug/nazwa), `source` (`bgg`|`custom`),
  `include_expansions` (bool). Zwraca paginację kart gry.
- `GET /api/games/search?q={tekst}` — auth: nie. `q` 2–100. Zwraca listę
  `{bgg_id, slug, title, year_published, cover_url, in_database}`. **Nie** tworzy
  gry.
- `GET /api/games/bgg/{bgg_id}` — auth: tak. Jednorazowa **materializacja**: ściąga
  pełne dane z BGG, zapisuje w bazie, nadaje slug, zwraca komplet. Wołaj **tylko**
  na kliknięcie wyniku `in_database=false`.

**Gotowe, gdy:** katalog filtruje, sortuje i przewija; wyszukiwarka rozróżnia
wynik lokalny od BGG i materializuje grę z BGG do bazy (dostaje slug).

### FAZA 3 — Profil gracza i jego półka

**Cel.** Konto usera: profil, edycja, kolekcja (półka) z pełnym CRUD, statystyki,
import z BGG oraz podgląd cudzych profili i półek. Zakładki **Profil** i **Półka**.

**Ekran: Mój profil (start zakładki Profil).**
- Zawartość: avatar, `display_name`, `@tag`, miasto, bio, data dołączenia; kafle
  statystyk ocen (średnia, liczba, mini-histogram); lista skrótów: „Edytuj
  profil", „Moje oceny" (Faza 4), „Dodaj grę" (Faza 5), „Ustawienia konta"
  (Faza 5), „O aplikacji" (atrybucja BGG), „Wyloguj".
- Endpointy: `GET /api/me` (auth: tak); `GET /api/me/ratings/stats` (auth: tak —
  średnia, liczba, histogram).

**Ekran: Edycja profilu.**
- Pola: `tag` (`[a-z0-9_]{3,30}`, unikalny), `display_name`, `city`, `bio`.
  Sekcja avatara: podgląd + „Zmień zdjęcie" (aparat/galeria, kadr do kwadratu) +
  „Usuń avatar".
- Endpointy:
  - `PUT /api/me` — auth: tak. JSON `{tag?, display_name?, city?, bio?}`. Nie
    ustawia avatara ani pól technicznych. Konflikt tagu → błąd walidacji.
  - `POST /api/me/avatar` — auth: tak. `multipart/form-data`, pole `file`
    (JPEG/PNG/WEBP ≤2 MB). Backend → WEBP 400×400. Zwraca profil.
  - `DELETE /api/me/avatar` — auth: tak. → `204`.

**Ekran: Moja półka (start zakładki Półka).**
- Zawartość: rząd kafli statystyk (liczba gier, wypożyczalne, łączny czas gry
  w formacie h/min); nagłówek z ikonami filtra i sortowania; lista kart pozycji
  (pseudo-3D pudełko, tytuł, chip stanu egzemplarza, badge „wypożyczalna" z
  kaucją). Przekaż do `BoxCover3D` pola `game_box_face_front_url`,
  `game_box_face_side_url`, `game_box_face_top_url`; fallbackiem jest
  `game_cover_url` + kolor klienta.
- Interakcje: pull-to-refresh; infinite scroll; **swipe na pozycji** →
  „Edytuj" / „Usuń"; tap → bottom sheet edycji; FAB „+" → dodanie gry
  (przejście do katalogu) lub „Importuj z BGG".
- Filtry (bottom sheet): `lendable`, `search` (2–100), `condition`
  (new/good/used/damaged), `players` (1–50). Sortowanie (`sort`): `added_at`,
  `title`, `game_rating`, `miplo_rating`.
- Stany: skeleton; pusty „Twoja półka jest pusta" + CTA „Przeglądaj katalog" /
  „Importuj kolekcję z BGG".
- Endpointy:
  - `GET /api/me/shelf` — auth: tak. Query: `page`, `size` (1–100), `lendable`,
    `search`, `condition`, `players`, `sort`. Zwraca paginację pozycji (z
    prywatnym `notes`).
  - `GET /api/me/shelf/stats` — auth: tak. Zwraca
    `{total_games, lendable_games, total_playing_time}`.

**Bottom sheet: Edycja „Mojej kopii".**
- Pola: przełącznik `lendable`; kaucja `lending_deposit` (0–9999 zł, aktywna gdy
  wypożyczalna); publiczne warunki `lending_notes` (≤500 zn.); stan `condition`
  (picker); prywatna notatka `notes` (≤500 zn., tylko właściciel). „Zapisz" /
  „Usuń z półki" (osobne potwierdzenie).
- Endpointy:
  - `POST /api/me/shelf` — auth: tak. Body `{game_slug, lendable?,
    lending_deposit?, lending_notes?, condition?, notes?}` → `201`. Duplikat →
    `409 game_already_on_shelf`; brak gry → `404 game_not_found`.
  - `PUT /api/me/shelf/{game_slug}` — auth: tak. Częściowa edycja → `200`; brak
    pozycji → `404 game_not_on_shelf`.
  - `DELETE /api/me/shelf/{game_slug}` — auth: tak → `204`.

**Ekran/sheet: Import kolekcji BGG.**
- Zawartość: pole „nick BGG"; checkbox „Importuj również moje oceny z BGG"
  (`import_ratings`); info „do 3 minut"; w trakcie pasek postępu + **blokada
  ponownego wysłania**; po sukcesie liczniki `imported`, `skipped`, `failed`,
  `ratings_imported`, `total_in_bgg`. Import **tylko dodaje** gry.
- Endpoint: `POST /api/me/shelf/import` — auth: tak (limit 2/godz). Body
  `{bgg_username, import_ratings}`. Timeout serwera zwraca wynik częściowy.

**Ekran: Profil publiczny gracza `/u/{tag}`.**
- Zawartość: avatar, `display_name`, `@tag`, miasto, bio, data dołączenia;
  zakładki „Półka" i „Oceny" (Faza 4). Nigdy nie pokazuj wewnętrznego `id`.
- Endpointy:
  - `GET /api/users/{tag}` — auth: tak. Publiczny profil (`[a-z0-9_]{3,30}`); brak
    → `404 user_not_found`. Bez `email`.
  - `GET /api/users/{tag}/shelf` — auth: tak. Publiczna półka; filtr `lendable`.
    **Bez** prywatnych `notes`; kaucja i warunki tylko dla `lendable=true`.

**Gotowe, gdy:** user edytuje profil i avatar, zarządza półką (dodaj/edytuj/
usuń, filtry, sort, statystyki), importuje kolekcję z BGG i ogląda cudze profile
oraz publiczne półki bez prywatnych notatek.

### FAZA 4 — Strona gry, oceny i recenzje

**Cel.** Pełny widok gry (rdzeń produktu) plus system ocen. Rozbudowuje kartę,
do której linkuje katalog z Fazy 2.

**Ekran: Szczegóły gry (przewijany, sekcjami).**
- **HERO — widok 3D pudełka (centralny element, górne ~45% ekranu).** To znak
  rozpoznawczy Miplo, więc otwiera stronę i jest największym elementem:
  - gdy `model_3d_url` istnieje → **interaktywny model GLB** wyśrodkowany na
    scenie: obrót gestem (drag), pinch-zoom, delikatna autorotacja w spoczynku,
    miękkie oświetlenie na tle w kolorze Płótno/Krem. Podpis „Model 3D
    społeczności". Ikona pełnego ekranu → tryb pełnoekranowy z obrotem.
  - gdy brak modelu → duża okładka 1:1 na środku, a pod nią lekki proceduralny
    placeholder pudełka; dla zalogowanego (i gdy `community_contributions_enabled
    =true`) przycisk-zachęta „Stwórz model 3D tej gry" → generator z Fazy 5.
  - podczas `model_status ∈ {pending, processing, awaiting_review}` pokaż nad
    hero subtelny pasek „Twój model jest w przygotowaniu"; **nie renderuj**
    kandydata `awaiting_review` (API nie zwraca jego URL) — jeśli istniał
    wcześniejszy zaakceptowany model, w hero nadal pokazuj ten stary.
- Pod hero — tytuł, rok, typy jako chipy, źródło.
- Oceny obok siebie: **BGG** (`rating`, `users_rated`, `bgg_rank`) i **Miplo**
  (`miplo_rating`, `miplo_ratings_count`). Gdy `miplo_rating=null` → „Za mało
  ocen" zamiast `0`.
- Metadane: zakres graczy, czas, waga, opis, link do instrukcji.
- Barcode'y: lista zatwierdzonych kodów z językiem (pl/en).
- Galeria: poziomy karuzel zaakceptowanych zdjęć (`images[]`) — zdjęcia
  komponentów, osobno od hero 3D.
- Sekcja ocen społeczności: podsumowanie (średnia + histogram 1–10) i lista
  recenzji (infinite scroll); spoilery zasłonięte do tapnięcia; przy cudzej
  recenzji akcja „Zgłoś".
- Blok zalogowanego (przyklejony u dołu): „Dodaj na półkę" **albo** karta „Moja
  kopia" (z `on_my_shelf`/`my_shelf_item`, edycja jak w Fazie 3); moja ocena
  (kontrolka 1–10 co 0.5; jeśli `my_rating` — pokaż z edycją/usunięciem);
  przyciski kontrybucji (Faza 5) **ukryte gdy** `community_contributions_enabled
  =false`.
- Stany: skeleton sekcji; „Nie znaleziono gry" (404); stary cache serwowany od
  razu (możliwe ciche „odświeżanie w tle").

**Endpointy (szczegóły + oceny).**
- `GET /api/games/{slug}` — auth: opcjonalny. `slug` może być zwykłą nazwą
  (backend normalizuje). Z tokenem dokłada `on_my_shelf`, `my_shelf_item`,
  `my_rating`, `my_review`. Zwraca pełny `GameDetail` (§7).
- `GET /api/games/{slug}/ratings/summary` — auth: nie. Średnia, liczba, histogram.
- `GET /api/games/{slug}/ratings` — auth: nie. Paginowana lista recenzji.
- `POST /api/games/{slug}/ratings` — auth: tak. Body `{rating (1–10 co 0.5),
  review?, contains_spoilers}`. Ponowna ocena → `409 already_rated` (użyj `PUT`).
- `PUT /api/games/{slug}/ratings` — auth: tak. Edycja własnej oceny.
- `DELETE /api/games/{slug}/ratings` — auth: tak → `204`.
- `POST /api/games/{slug}/ratings/{rating_id}/report` — auth: tak. Body
  `{reason, details?}`; sukces `message_code=review_reported`. Nie zgłosisz
  własnej (`cannot_report_own_review`); ponownie → `review_already_reported`.

**Ekran: Moje oceny (skrót z Profilu) i Oceny gracza `/u/{tag}`.**
- Moje oceny: kafle statystyk; lista (okładka, tytuł, moja ocena, fragment
  recenzji, źródło `miplo`/`bgg_import`); filtr „z recenzją", sort; ocenę ukrytą
  moderacją oznacz **neutralnym** statusem, bez `hidden_reason`.
- Endpointy: `GET /api/me/ratings` (auth: tak, paginacja);
  `GET /api/me/ratings/stats` (auth: tak); `GET /api/users/{tag}/ratings`
  (auth: tak).

**Gotowe, gdy:** strona gry otwiera się interaktywnym **hero 3D** (albo okładką +
zachętą do stworzenia modelu, gdy brak GLB), pokazuje komplet danych, galerię,
barcode, oceny ze spoilerami; zalogowany dodaje/edytuje/usuwa ocenę i zgłasza
recenzje; przełącznik „Dodaj na półkę"/„Moja kopia" działa na `on_my_shelf`.

### FAZA 5 — Skaner, kontrybucje, gry c ustom, konto

**Cel.** Funkcje społecznościowe i domknięcie konta.

**Ekran: Skaner kodu (zakładka Skaner).**
- Zawartość: pełnoekranowy podgląd aparatu z celownikiem; latarka; „Wpisz kod
  ręcznie". Formaty EAN-8/UPC-A/EAN-13. Rozpoznano → lookup → gra po `slug`. Brak
  → „Nie znaleziono": (a) wyszukaj po nazwie, (b) po wybraniu gry otwórz
  propozycję barcode z **zachowanym** numerem.
- Uprawnienia: prośba o aparat z uzasadnieniem; stan „brak uprawnień" z linkiem
  do ustawień i alternatywą ręczną.
- Endpoint: `GET /api/games/by-barcode/{barcode}` — auth: nie. Poprawny
  EAN-8/UPC-A/EAN-13. Zwraca kartę gry albo `404 barcode_not_found` (tylko
  zatwierdzone kody i zweryfikowane gry).

**Ekran: Dodaj grę custom (FAB w katalogu / skrót w profilu).**
- Pola: tytuł, opis, min/max graczy, czas, rok, wymiary pudełka, link HTTPS do
  instrukcji, okładka (upload), **typy gry jako multi-select** z enuma (§6). Slug
  generuje backend — **nie pokazuj pola slug**. Po `201` ekran „Gra oczekuje na
  moderację". Brak endpointu „moje zgłoszenia" — nie symuluj listy oczekujących.
- Endpoint: `POST /api/games` — auth: tak (limit 5/godz). `multipart/form-data`.
  Wymagane `title`, `min_players`, `max_players`, `game_types`. Opcjonalne
  `description`, `playing_time`, `box_width/height/depth`, `year_published`,
  `instruction_url`, `cover`. **`game_types` wysyłaj jako powtarzane pole**
  (`game_types=Euro`, `game_types=Ekonomiczna`). → `201`.

**Ekran: Edycja gry custom (tylko właściciel).**
- Ten sam formularz, wypełniony; info, że zmiana **wraca do moderacji**; osobna
  „Usuń grę".
- Endpointy: `PUT /api/games/{slug}` — auth: tak, `multipart/form-data`, tylko
  twórca i `source=custom` (BGG → `403 cannot_edit_bgg_game`, cudza →
  `403 not_game_owner`); nowy `slug` z odpowiedzi. `DELETE /api/games/{slug}` —
  auth: tak, tylko twórca → `204`.

**Kontrybucje (wejście z ekranu gry, ukryte gdy `contributions` off).**
- **Propozycja zdjęcia:** jedno zdjęcie (aparat/galeria) + podpis, JPEG/PNG/WEBP
  ≤2 MB; status „oczekuje na akceptację"; `public_id` do wycofania.
  - `POST /api/games/{slug}/images` — auth: tak. `multipart`: `file` (wymagane),
    `caption` (opc.). → `202` `pending`. Limit 12/grę (`gallery_limit_reached`).
  - `DELETE /api/games/{slug}/images/{public_id}` — auth: tak → `204`.
- **Propozycja barcode:** pole kodu (prefill ze skanera) + picker języka pl/en;
  walidacja sumy kontrolnej w aplikacji.
  - `POST /api/games/{slug}/barcodes` — auth: tak. `x-www-form-urlencoded`:
    `barcode`, `language_code`. → `202` (`pending`). Błędy:
    `invalid_barcode_format`, `game_barcode_exists`, `barcode_proposal_pending`.
- **Generator modelu 3D:** zawsze pokazuje 5 slotów
  (`back/left/right/top/bottom`) z graficzną legendą; każde ≤2 MB. Jeśli
  `cover_url` istnieje, pokaż jego miniaturę jako zablokowany front z podpisem
  „Front z okładki gry" — nie wysyłaj `file_front` ani `rotation_front`. Jeśli
  `cover_url=null`, pokaż szósty, wymagany slot `front`. Picker rotacji
  `0/90/180/270` dotyczy wyłącznie przesyłanych zdjęć. Po wysłaniu odpytuj
  `GET /api/games/{slug}` rosnącym interwałem;
  statusy `model_status`: `pending → processing → awaiting_review →
  (ready|failed)`. Kandydata `awaiting_review` **nie renderuj**; poprzedni
  zaakceptowany model pokazuj dalej.
  - `POST /api/games/{slug}/3d-model` — auth: tak. `multipart`: 5 wymaganych
    plików, a `file_front` tylko bez covera; opc. `rotation_*`
    (`0/90/180/270` jako tekst), formularz ≤14 MB. → `202` `pending`.
    Trwa → `model_already_processing`; problem z istniejącym coverem →
    `cover_source_unavailable`.
  - `DELETE /api/games/{slug}/3d-model` — auth: tak → `204` (wycofanie kandydata;
    nigdy nie usuwa zaakceptowanego modelu).

**Ekran: Ustawienia konta.**
- „Dezaktywuj konto" (odwracalne), „Reaktywuj", strefa niebezpieczna „Usuń konto
  na stałe" (bottom sheet z wpisaniem `USUŃ`). Akcje destrukcyjne blokują
  przycisk na czas requestu.
- Endpointy: `POST /api/me/deactivate` → `204`; `POST /api/me/activate` → `204`
  (dopuszcza nieaktywne); `DELETE /api/me` → `204` (trwałe, dopuszcza nieaktywne).
  Wszystkie auth: tak.

**Gotowe, gdy:** skaner prowadzi do gry lub propozycji kodu; można dodać/edytować
grę custom; kontrybucje (zdjęcie, barcode, model 3D) mają jasny status; konto da
się dezaktywować, reaktywować i trwale usunąć.

---

## 6. Dane słownikowe (enumy)

**Typy gry (`GameTypeName`, multi-select):** Strategia, Euro, Ekonomiczna,
Familijna, Imprezowa, Karciana, Kościana, Abstrakcyjna, Wojenna, Bitewna,
Przygodowa, Eksploracja, Kooperacyjna, Fantasy, Sci-Fi, Horror, Logiczna,
Dedukcja, Dla dzieci, Quiz, Słowna, Sportowa, Wyścigowa, Humor, Cywilizacja,
Rolnictwo, Przemysł / Produkcja, Budowa Miasta, Budowa Terytorium.

**Stan egzemplarza (`condition`):** `new`, `good`, `used`, `damaged`.
**Sortowanie półki (`sort`):** `added_at`, `title`, `game_rating`, `miplo_rating`.
**Języki barcode (`language_code`):** `pl`, `en`.
**Powód zgłoszenia (`reason`):** `spam`, `offensive`, `spoilers`, `off_topic`.
**Ocena (`rating`):** 1–10 z krokiem 0.5.

---

## 7. Kluczowe modele odpowiedzi

Liczby `Decimal` (oceny, kaucja, wymiary) mogą przyjść jako **tekst** (`"8.56"`) —
formatuj bezpiecznie, nie zakładaj typu liczbowego.

**Karta gry (element listy):**
```json
{ "slug": "brass-birmingham", "title": "Brass: Birmingham", "year_published": 2018,
  "min_players": 2, "max_players": 4, "rating": "8.56",
  "cover_url": "https://cf.geekdo-images.com/...", "game_types": ["Euro", "Ekonomiczna"],
  "source": "bgg", "bgg_rank": 1, "users_rated": 59269, "is_expansion": false,
  "miplo_rating": "8.2", "miplo_ratings_count": 14 }
```

**Wynik wyszukiwania:**
```json
{ "bgg_id": 224517, "slug": null, "title": "Brass: Birmingham",
  "year_published": 2018, "cover_url": null, "in_database": false }
```
`in_database=true` → jest lokalny `slug`. `false` → kliknięcie (zalogowany) woła
`/api/games/bgg/{bgg_id}` i bierze `slug` z odpowiedzi.

**GameDetail (pola dla UI):**
```json
{ "slug": "brass-birmingham", "title": "Brass: Birmingham", "year_published": 2018,
  "min_players": 2, "max_players": 4, "playing_time": 120,
  "rating": "8.56", "weight": "3.90", "cover_url": "https://cf.geekdo-images.com/...",
  "game_types": ["Euro", "Ekonomiczna"], "description": "...", "instruction_url": null,
  "box_width": "29.50", "box_height": "29.50", "box_depth": "7.00",
  "model_3d_url": "https://storage.googleapis.com/.../box_model.glb?v=...",
  "box_face_front_url": "https://storage.googleapis.com/.../face_front.webp?v=...",
  "box_face_side_url": "https://storage.googleapis.com/.../face_side.webp?v=...",
  "box_face_top_url": "https://storage.googleapis.com/.../face_top.webp?v=...",
  "model_status": "ready", "source": "bgg", "is_verified": true,
  "bgg_rank": 1, "users_rated": 59269, "is_expansion": false,
  "miplo_rating": "8.2", "miplo_ratings_count": 14, "miplo_reviews_count": 6,
  "barcodes": [{ "barcode": "5901549927658", "language_code": "pl" }],
  "images": [{ "public_id": "9bea5aa0-...", "image_url": "https://.../i.webp",
               "caption": "Komponenty", "created_at": "2026-07-18T12:00:00Z" }],
  "on_my_shelf": true, "my_rating": "9.0", "my_review": "Świetna gra.",
  "my_shelf_item": { "lendable": true, "lending_deposit": "50.00",
    "lending_notes": "Odbiór osobisty", "condition": "good", "notes": "Prywatna notatka",
    "added_at": "2026-07-18T12:00:00Z", "game_slug": "brass-birmingham",
    "game_title": "Brass: Birmingham", "game_cover_url": "https://cf.geekdo-images.com/...",
    "game_min_players": 2, "game_max_players": 4, "game_playing_time": 120,
    "game_rating": "8.56", "game_miplo_rating": null,
    "game_model_3d_url": "https://storage.googleapis.com/.../box_model.glb?v=...",
    "game_box_face_front_url": "https://storage.googleapis.com/.../face_front.webp?v=...",
    "game_box_face_side_url": "https://storage.googleapis.com/.../face_side.webp?v=...",
    "game_box_face_top_url": "https://storage.googleapis.com/.../face_top.webp?v=..." },
  "community_contributions_enabled": true, "created_at": "2026-07-18T12:00:00Z" }
```

**Profil:**
```json
{ "tag": "omnisecura", "email": "user@example.com", "display_name": "Bartosz",
  "city": "Kraków", "bio": "Lubię ciężkie euro.",
  "avatar_url": "https://.../avatar.webp?v=...", "created_at": "2026-07-18T12:00:00Z" }
```
Profil publiczny nie ma `email`. Żaden nie ma `id`, `firebase_uid`, `is_active`,
`is_admin`, `updated_at`.

**Ocena / recenzja:**
```json
{ "public_id": "…", "rating": "9.0", "review": "Świetna gra.", "contains_spoilers": false,
  "created_at": "2026-07-18T12:00:00Z",
  "author": { "tag": "omnisecura", "display_name": "Bartosz",
              "avatar_url": "https://.../avatar.webp" } }
```

**Paginacja (wszystkie listy):**
```json
{ "items": [], "total": 142, "page": 1, "size": 20, "pages": 8 }
```

---

## 8. Obsługa błędów i stanów

Błąd domenowy:
```json
{ "detail": { "error_code": "game_not_found", "details": {} } }
```
Mapuj `error_code` na klucze i18n; **nie pokazuj** surowego wyjątku ani `details`.
Obsłuż co najmniej: `unauthorized`, `invalid_token`, `token_expired`,
`user_inactive`, `forbidden`, `not_game_owner`, `game_not_found`,
`barcode_not_found`, `game_title_exists`, `game_already_on_shelf`,
`game_not_on_shelf`, `already_rated`, `not_rated_yet`, `rating_hidden`,
`review_already_reported`, `cannot_report_own_review`, `invalid_barcode_format`,
`game_barcode_exists`, `barcode_proposal_pending`, `contributions_locked`,
`model_already_processing`, `gallery_limit_reached`, `file_too_large`,
`invalid_file_type`, `payload_too_large`, `bgg_not_configured`, `bgg_unavailable`,
`bgg_rate_limited`, `rate_limit_exceeded`, `internal_error`.

Walidacja `422` ma ten sam kształt: `error_code=validation_error`, a
`details.errors[]` zawiera `field` i `rule` — nie pokazuj `rule` wprost, mapuj
przez i18n (błąd pod właściwym polem). Sukces zgłoszenia recenzji zwraca
`message_code=review_reported`.

Wzorce: błąd pola → pod polem; błąd ekranu → dedykowany stan z „Ponów";
potwierdzenia i błędy akcji w tle → toast; akcje destrukcyjne → potwierdzenie
w bottom sheet + zablokowany przycisk. Nie pokazuj kontrolek społecznościowych,
gdy konto jest zdezaktywowane lub gra ma zablokowane kontrybucje. Dane tekstowe
renderuj jako tekst (nie HTML); URL-e z API tylko do komponentów obraz/PDF/GLB.

---

## 9. Poza zakresem

Panel moderatora i endpointy `/api/admin/*`; `POST /api/admin/games/import`;
domeny matchmaking i venues; reakcje „pomocne/niepomocne" na recenzje; jakiekolwiek
klucze/sekrety w aplikacji klienckiej.

---

## 10. Kryteria ukończenia

- Fazy 0–5 zrealizowane w kolejności; każda z listą „Gotowe, gdy" spełniona.
- Autoryzacja: rejestracja, logowanie, reset, auto-tag, obsługa wygaśnięcia tokenu.
- Katalog: filtry, sort, pull-to-refresh, infinite scroll; wyszukiwarka rozróżnia
  wynik lokalny od BGG i materializuje grę (nadaje slug), nigdy nie zgaduje slugu.
- Profil i półka: edycja profilu i avatara, CRUD półki (swipe, bottom sheet),
  statystyki, import BGG; publiczna półka bez prywatnych notatek.
- Strona gry: **hero 3D** (interaktywny GLB u góry ekranu; obrót, zoom,
  autorotacja) lub okładka + zachęta do stworzenia modelu przy braku GLB;
  brakujące dane, galeria, barcode, oceny ze spoilerami, przełącznik „Dodaj na
  półkę"/„Moja kopia"; „Za mało ocen" przy braku `miplo_rating`;
  ocenianie/edycja/usunięcie/zgłoszenie recenzji.
- Skaner: uprawnienia aparatu, ręczny kod, ścieżka propozycji przy braku trafienia.
- Gry custom: poprawny multipart, `game_types` jako powtarzane pole, ekran
  oczekiwania na moderację; kontrybucje z jasnym statusem; formularz 3D wymaga
  5 zdjęć oraz frontu tylko przy braku covera; rotacje 0/90/180/270 dotyczą
  przesyłanych ścian.
- Konto: dezaktywacja, reaktywacja, trwałe usunięcie.
- Profil nie pokazuje wewnętrznych identyfikatorów; brak panelu moderatora,
  klucza admina i importu katalogu.
- Interfejs dostępny (WCAG AA, Dynamic Type, VoiceOver/TalkBack), paleta „Wood"
  w motywie jasnym i ciemnym, komplet stanów loading/empty/error.
