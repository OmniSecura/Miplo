# Autoryzacja — jak to działa

Dokumentacja aktualnego stanu warstwy auth. Setup Firebase krok po kroku:
`FIREBASE.md`. Uzasadnienie decyzji: `decisions/0001-firebase-zamiast-wlasnego-auth.md`.

## Zasada naczelna

Firebase odpowiada za **tożsamość** (logowanie, rejestracja, hasła, OAuth, MFA).
My odpowiadamy za **autoryzację** (kto co może w Miplo) i dane domenowe.
Nie piszemy własnych haseł ani tokenów. Endpoint rejestracji nie istnieje —
konto lokalne powstaje samo przy pierwszym zweryfikowanym tokenie.

## Przepływ requestu

```
Authorization: Bearer <ID_TOKEN>
        │
        ▼
get_current_user()                        core/auth.py
  1. brak nagłówka?          → 401 unauthorized
  2. verify_id_token(check_revoked=True)
                             → 401 token_expired  (frontend: odśwież przez SDK)
                             → 401 token_revoked  (odwołany/disabled/usunięty)
                             → 401 invalid_token  (podróbka/uszkodzony)
                             → 503 auth_provider_unavailable
  3. SELECT po firebase_uid  → brak = pierwszy login = INSERT (find-or-create;
                               wyścig dwóch requestów obsłużony przez IntegrityError)
  4. is_active == False?     → 403 user_inactive
  5. zwraca lokalny obiekt User  → endpoint pracuje na nim, Firebase znika z pola widzenia
```

Tożsamość ZAWSZE z tokenu. Żaden payload nie zawiera i nie może zawierać
identyfikatora konta.

## Pliki i odpowiedzialności

| Plik | Rola |
|---|---|
| `core/auth.py` | JEDYNE miejsce dotykające Firebase: init, weryfikacja z revocation check oraz bezpieczny cykl usunięcia konta |
| `core/errors.py` | Enum `ErrorCode` (kontrakt z frontendem) + `ApiError` ze skrótami (`unauthorized()`, `forbidden()`, `not_found()`, `bad_request()`, `too_many_requests()`) |
| `core/security/limiter.py` | Limity nazwane (READ/WRITE/DELETE), klucz per firebase_uid dla zalogowanych, 429 z kodem błędu. Każdy endpoint MUSI mieć dekorator |
| `users/services/user_service.py` | Cały CRUD usera; jedyne miejsce z commitami |
| `users/routers/router.py` | Endpointy — zero SQLAlchemy, zero Firebase |

## Endpointy

| Endpoint | Auth | Limit | Zwraca |
|---|---|---|---|
| `GET /api/me` | ✔ | 60/min | `UserProfile` |
| `PUT /api/me` | ✔ | 20/min | `UserProfile` (po zmianie) |
| `POST /api/me/avatar` | ✔ | 5/min | `UserProfile` (multipart, pole `file`; jpeg/png/webp ≤2 MB → webp 400×400 w Firebase Storage) |
| `DELETE /api/me/avatar` | ✔ | 20/min | `204` (blob z bucketa + `avatar_url = NULL`; idempotentne) |
| `POST /api/me/deactivate` | ✔ | 5/h | `204` (soft delete: tylko flaga `is_active`, odwracalne) |
| `POST /api/me/activate` | ✔ (działa dla nieaktywnych) | 20/min | `204` (reaktywacja po soft delete) |
| `DELETE /api/me` | ✔ (działa dla nieaktywnych) | 5/h | `204` (twarde usunięcie: nasza baza → Firebase; RODO/Apple) |
| `GET /api/users/{tag}` | ✔ | 60/min | `UserPublic` (404 gdy brak lub nieaktywny) |

Konto zdeaktywowane: wszystkie endpointy zwracają `403 user_inactive` poza
dwoma wyjątkami — `POST /me/activate` (inaczej deaktywacja byłaby
nieodwracalna) i `DELETE /me` (prawo do bycia zapomnianym z RODO nie może
być zablokowane flagą). Oba i tak wymagają ważnego tokenu tego konta.

`PUT /me`: pole pominięte = bez zmian, jawny `null` = wyczyszczenie pola,
nieznane pole = 422 (`extra="forbid"`). Zajęty `tag` = 409 `tag_taken`.

## Identyfikacja graczy: tag vs display_name

- **`tag`** — techniczny, unikalny, `[a-z0-9_]{3,30}`: do URL-i
  (`miplo.app/u/omnisecura`) i wywołań API. Generowany automatycznie przy
  pierwszym logowaniu (z maila/nazwy + sufiks przy kolizji), user może
  zmienić przez `PUT /me`. Wielkie litery w payloadzie są normalizowane
  do małych.
- **`display_name`** — wyświetlane, NIE-unikalne, dowolny Unicode: Anny mogą
  się nazywać Annami. Gdy dwóch userów w jednym widoku ma tę samą nazwę,
  UI dokleja tag w nawiasie: „Anna Kowalska (ania_z_krk)".

Wewnętrzne `id` nie jest potrzebne klientowi do niczego — i dlatego nigdzie
go nie widać.

## Widoczność pól — co API pokazuje i przyjmuje

|  | ustawialne (PUT /me) | widzi właściciel (`UserProfile`) | widzą inni (`UserPublic`) |
|---|---|---|---|
| `id` | **NIE** | **NIE** | **NIE** |
| `firebase_uid` | **NIE** | **NIE** | **NIE** |
| `tag` | tak (`[a-z0-9_]{3,30}`, unikalny) | tak | tak |
| `email` | nie (kopia z Firebase) | tak | **NIE** |
| `display_name` | tak (2–80) | tak | tak |
| `city` | tak (2–120) | tak | tak |
| `bio` | tak (≤2000) | tak | tak |
| `avatar_url` | **NIE przez JSON** — tylko upload/DELETE `/me/avatar`; URL zawsze z naszego Storage | tak | tak |
| `created_at` | nie (nadaje baza) | tak | tak („dołączył(a) X") |
| `updated_at` | **NIE** | **NIE** | **NIE** |
| `is_active` | **NIE** | **NIE** | **NIE** |
| `is_admin` | **NIE** | **NIE** | **NIE** |

Pola czysto backendowe (`id`, `firebase_uid`, `is_active`, `is_admin`, `updated_at`) nie
opuszczają bazy — nie da się ich zobaczyć ani zmienić przez API. Publicznym
identyfikatorem gracza jest wyłącznie `tag`, a `is_active` objawia się
klientowi tylko skutkami: `403 user_inactive` dla właściciela nieaktywnego
konta i `404` na publicznym profilu.

## Kody błędów (kontrakt z frontendem)

Kształt: `{"detail": {"error_code": "...", "details": {...}?}}` — teksty
tłumaczy frontend (i18n). Katalog: enum `ErrorCode` w `core/errors.py`.

| Status | `error_code` | Kiedy |
|---|---|---|
| 401 | `unauthorized` | brak nagłówka `Authorization` |
| 401 | `token_expired` | token wygasł — frontend odświeża przez SDK i ponawia |
| 401 | `invalid_token` | podpis się nie zgadza / revoked / nie-JWT |
| 403 | `user_inactive` | konto zdezaktywowane (soft delete) |
| 403 | `forbidden` | rezerwowy — próba dostępu do cudzych zasobów |
| 400 | `file_too_large` | avatar > 2 MB (`details.max_bytes`) albo > 24 Mpx (`details.max_pixels`) |
| 400 | `invalid_file_type` | content-type spoza jpeg/png/webp albo bajty nie są obrazem |
| 404 | `user_not_found` | publiczny profil nie istnieje lub nieaktywny |
| 409 | `tag_taken` | `PUT /me` z tagiem zajętym przez kogoś innego |
| 422 | (format FastAPI) | walidacja Pydantic — pola i przyczyny w `detail` |
| 429 | `rate_limit_exceeded` | limit requestów; nagłówki `Retry-After`, `X-RateLimit-*` |
| 502 | `avatar_upload_failed` | Firebase Storage nie przyjął pliku (problem po naszej stronie) |

Każde 401 niesie nagłówek `WWW-Authenticate: Bearer`.

## Dostęp administratorski

Zwykłe API zawsze używa Firebase. Wyłącznie router
`/api/admin/moderation/*` ma dodatkową ścieżkę operatorską:

```http
X-Admin-Key: <ADMIN_API_KEY z .env/Secret Managera>
```

Alternatywnie działa Firebase ID token aktywnego lokalnego usera z
`is_admin=true`. Uniwersalny klucz jest porównywany w stałym czasie, nigdy nie
jest logowany ani zwracany i nie może znaleźć się w kodzie frontendu. Podany
błędny klucz daje `401 invalid_admin_api_key`; brak skonfigurowanego sekretu przy
próbie użycia tej ścieżki daje `503 admin_api_key_not_configured`.

## Bezpieczeństwo wejścia

Warstwy obrony, od zewnątrz do środka:

1. **Limit wielkości body** (`core/security/body_limit.py`, czysty ASGI, przed
   routingiem i auth): JSON > 64 KB → `413 payload_too_large`, zwykły multipart
   > 3 MB → `413`, model 3D > 14 MB → `413`, body importu katalogu > 51 MB → `413`;
   body bez `Content-Length` (chunked) →
   `411 length_required`. Pydantic waliduje dopiero po sparsowaniu całego
   JSON-a — bez tego duży payload najpierw zjadałby RAM.
1a. **Avatar — trzy warstwy** (`users/services/avatar_service.py`): rozmiar
   czytany chunkami z limitem 2 MB PRZED złożeniem w RAM → content-type
   z części multipart (jpeg/png/webp) → Pillow: wymiary sprawdzane
   Z NAGŁÓWKA przed dekodowaniem (bomba pikselowa > 24 Mpx odpada bez
   alokacji RAM), potem pełny decode wykrywa nie-obrazy. Wynik zawsze przechodzi przez re-encode
   do webp 400×400 — do bucketa nigdy nie trafiają oryginalne bajty ani
   EXIF (GPS, model telefonu). `avatar_url` nieedytowalny przez JSON.
2. **Schematy Pydantic** (`users/schemas/user.py`):
   - `extra="forbid"` wszędzie — mass assignment (`is_active`, `firebase_uid`
     w payloadzie) kończy się 422;
   - limity długości zgodne z kolumnami bazy;
   - znaki sterujące (kategoria Cc, w tym `\x00`, który wywala Postgresa)
     odrzucane we wszystkich polach; w `bio` dozwolone tylko `\n` i `\t`;
   - znaki przejęcia kierunku tekstu (RTL override — spoofing nazw) odrzucane;
     emoji i pełny "zwykły" Unicode przechodzą;
   - `avatar_url` nie występuje w schemacie wejściowym; klient nie może podać
     żadnego URL-a, bo wartość zapisuje wyłącznie backend po uploadzie do bucketa;
   - `tag`: twardy pattern `^[a-z0-9_]{3,30}$` (w path parametrze też).
3. **SQL**: wyłącznie ORM z bind parameters — zero konkatenacji zapytań.
4. **Dane z tokenu Firebase** traktowane jak każde inne wejście: walidowane
   przez `UserCreate`; jak nie przechodzą, konto powstaje puste (fallback
   w `core/auth.py`), nigdy 500.

Przed routingiem działa dodatkowo `GlobalIpRateLimitMiddleware`. Liczy także
requesty odrzucone przez auth i Pydantic, więc błędne tokeny oraz payloady nie
omijają limitu. Dekoratory SlowAPI pozostają dokładniejszą drugą warstwą.

## Rate limiting

- Konfiguracja w JEDNYM miejscu: `core/security/limiter.py`; limity nakładane
  dekoratorem `@limiter.limit(...)` pod dekoratorem routera.
- Endpoint musi mieć w sygnaturze `request: Request` **i** `response: Response`
  (wymóg slowapi przy `headers_enabled=True` — bez tego 500).
- Klucz: zalogowany per `firebase_uid`, anonim per IP (NAT nie zbija limitu wszystkim).
- Dev: liczniki w pamięci procesu; prod wymusza `redis://`/`rediss://` przy
  starcie, więc wszystkie instancje Cloud Run korzystają ze wspólnych liczników.
- SlowAPIMiddleware celowo nieużywany — nie widzi endpointów w FastAPI ≥0.139,
  więc "globalny default limit" byłby fikcją. Dekorator na każdym endpoincie.

## Usuwanie konta (RODO / wymóg Apple)

`DELETE /me` → (1) konto Firebase zostaje disabled i jego refresh tokeny są
odwołane, (2) avatar i dane SQL są usuwane, (3) tożsamość Firebase jest usuwana.
Jeśli krok SQL zawiedzie, backend best-effort ponownie włącza Firebase. Jeśli
finalne `delete_user` zawiedzie, konto pozostaje disabled, a `check_revoked=True`
uniemożliwia odtworzenie lokalnego profilu starym tokenem.
