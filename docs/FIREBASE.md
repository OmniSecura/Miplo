# Firebase Auth w Miplo

Jak ogarnąć Firebase od zera do działającego `GET /me`. Uzasadnienie decyzji:
`decisions/0001-firebase-zamiast-wlasnego-auth.md`.

## Podział odpowiedzialności

| Firebase | Nasza baza (tabela `users`) |
|---|---|
| hasła, reset hasła | `firebase_uid` (most do Firebase) |
| rejestracja, logowanie | profil: display_name, city, bio, avatar |
| OAuth (Google, Apple), MFA | `is_active` (soft delete po naszej stronie) |
| weryfikacja maila, lockout | wszystko, co domenowe (półka, matchmaking…) |

Backend NIE loguje i NIE rejestruje userów. Backend tylko **weryfikuje tokeny**
i przy pierwszym zweryfikowanym tokenie zakłada lokalny rekord (find-or-create
w `core/auth.py`). Endpoint rejestracji nie istnieje i ma nie istnieć.

## Jak działa flow (całość)

```
1. Klient (web/PWA) loguje się przez Firebase SDK
   (email+hasło / Google / Apple — konfigurowane w konsoli, nie w kodzie)
2. Firebase SDK zwraca klientowi ID token (JWT, ważny ~1h,
   SDK odświeża go sam — backend tego nie dotyka)
3. Klient wysyła każdy request z nagłówkiem:  Authorization: Bearer <ID_TOKEN>
4. Backend: get_current_user() → firebase_admin.auth.verify_id_token()
   → weryfikacja podpisu/expiry → uid, email, name
5. Szukamy usera po firebase_uid; brak = pierwszy login = INSERT (find-or-create)
6. Endpoint dostaje gotowego, lokalnego Usera. Dalej wszystko chodzi po users.id
```

Zły token → `401 {"detail": {"error_code": "invalid_token"}}`. Wygasły →
`401 ... "token_expired"` (frontend: odśwież token przez SDK i ponów). Brak tokenu →
`401 ... "unauthorized"`. Konto dezaktywowane → `403 ... "user_inactive"`.
Pełny katalog kodów: `services/app/core/errors.py` (enum `ErrorCode`) oraz
[`ERRORS.md`](ERRORS.md).

## Setup krok po kroku

### 1. Projekt w konsoli Firebase
1. [console.firebase.google.com](https://console.firebase.google.com) → **Add project** (np. `miplo-dev`; docelowo osobny projekt na dev i prod).
2. **Build → Authentication → Get started**.
3. Zakładka **Sign-in method** — włącz:
   - **Email/Password** (na start),
   - **Google** (jedno kliknięcie),
   - **Apple** — dopiero przy aplikacji mobilnej (wymóg App Store, gdy są inne logowania społecznościowe).

### 2. Klucz admina (dla backendu)
1. Konsola → ⚙ **Project settings → Service accounts → Generate new private key**.
2. Zapisz plik JSON **poza repo** (albo w ignorowanym katalogu `secrets/`).
   `.gitignore` już kryje `firebase-admin*.json`, `service-account*.json`, `secrets/`, `*-credentials.json`.
3. W `services/.env`:
   ```
   FIREBASE_ADMIN_CREDENTIALS=C:/sciezka/do/firebase-admin.json
   ```
4. Na produkcji (Cloud Run): klucz w **GCP Secret Manager**, montowany jako
   plik/zmienna — nigdy w obrazie ani w repo.

Klucz admina daje pełną kontrolę nad projektem Firebase — traktuj jak hasło roota.
Wyciek = natychmiastowa rotacja (Service accounts → wygeneruj nowy, unieważnij stary).

### 3. Inicjalizacja w backendzie
Dzieje się samo: `server.py` woła `core.auth.init_firebase()` w lifespanie —
raz, przy starcie. Zły/nieistniejący klucz wywala start serwera (fail-fast),
a nie pierwszy request usera.

## Jak przetestować bez frontendu

1. Konsola → **Authentication → Users → Add user** (email + hasło).
2. Weź **Web API Key**: ⚙ Project settings → General.
3. Wymień email+hasło na ID token (to samo robi klient przez SDK):
   ```bash
   curl -s -X POST \
     "https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key=WEB_API_KEY" \
     -H "Content-Type: application/json" \
     -d '{"email":"test@example.com","password":"haslo123","returnSecureToken":true}'
   ```
   Z odpowiedzi weź pole `idToken`.
4. Strzel w API:
   ```bash
   curl -s http://localhost:8000/api/me -H "Authorization: Bearer <idToken>"
   ```
   Pierwszy strzał zakłada lokalnego usera i zwraca `200` z profilem (DoD ✓).

### Emulator (opcjonalnie, dev offline)
`firebase emulators:start --only auth` + zmienna `FIREBASE_AUTH_EMULATOR_HOST=localhost:9099`
przed startem uvicorna — `verify_id_token` akceptuje wtedy tokeny emulatora.
Nie ustawiaj tej zmiennej nigdzie poza lokalną maszyną.

## Firebase Storage (avatary oraz media gier)

Podjęta decyzja: publiczne media Miplo przechowujemy w Firebase Storage. Obecnie
są to:

- `avatars/{firebase_uid}/avatar.webp` — avatar usera,
- `games/{game_id}/cover.webp` — okładka customowej gry,
- `games/{game_id}/gallery/{uuid}.webp` — zatwierdzone zdjęcie galerii,
- `games/{game_id}/box_model.glb` — zatwierdzony model pudełka,
- `games/{game_id}/submissions/...` i `models/submissions/...` — prywatny staging.

Publiczny jest wyłącznie odczyt zatwierdzonych obiektów. Staging nie dostaje
publicznego ACL; administrator ogląda go przez podpisany URL ważny 15 minut.
Upload, promocję i usuwanie wykonuje backend przez Admin SDK. Uzasadnienie:
decyzje `0005`, `0008`, `0009` i `0010`.

### Setup
1. Konsola → **Build → Storage → Get started**. UWAGA: Storage może wymagać
   planu **Blaze** (pay-as-you-go) i podpięcia karty. Limity oraz ceny zmieniają
   się w czasie, dlatego przed produkcją sprawdź aktualny cennik i ustaw alert budżetu.
   Alternatywa na dev: serwowanie mediów lokalnie przez `StaticFiles`
   i podmiana na Storage przy deployu.
2. Nazwę bucketa (np. `miplo-dev.firebasestorage.app` — bez `gs://`) wpisz do
   `services/.env` jako `FIREBASE_STORAGE_BUCKET`.
3. **Reguły bezpieczeństwa** (zakładka Rules): zablokuj wszystko dla klientów —
   backend i tak chodzi przez Admin SDK, który omija reguły:
   ```
   rules_version = '2';
   service firebase.storage {
     match /b/{bucket}/o {
       match /{allPaths=**} {
         allow read, write: if false;
       }
     }
   }
   ```
   Publiczny odczyt mediów nadaje jawnie backend (`blob.make_public()`)
   per plik — reguły klienckie nie muszą (i nie powinny) nic otwierać.

### Test manualny
Upload avatara przez Swagger (`POST /api/me/avatar`, pole `file`) lub utworzenie
customowej gry z okładką (`POST /api/games`) powinno po publikacji zwrócić URL
`https://storage.googleapis.com/...`, który działa bez logowania. Galerię i GLB
należy dodatkowo sprawdzić w pełnym flow: zgłoszenie → prywatny podgląd moderatora
→ akceptacja → publiczny URL.

## Usuwanie konta (RODO / wymóg Apple)

`DELETE /me` robi trzy rzeczy, w tej kolejności:
1. usuwa avatar z bucketa (padnięcie Storage nie blokuje reszty — tylko warning),
2. twarde `DELETE` naszego rekordu (dane osobowe znikają z naszej bazy),
3. `firebase_admin.auth.delete_user(uid)` — konto znika z Firebase.

Gdyby krok 3 padł, dane z naszej bazy już nie istnieją, a user przy kolejnym
logowaniu dostałby świeży, pusty profil — bez wycieku starych danych.

## Zasady

- Tożsamość ZAWSZE z tokenu (`verify_id_token`), nigdy z payloadu requestu.
- Firebase Auth jest dotykany wyłącznie w `services/app/core/auth.py`. Bucket
  inicjalizuje `core/storage.py`, a pliki obsługują wyspecjalizowane serwisy
  avatara, okładek, galerii i modeli 3D.
- Backend nie przechowuje żadnych tokenów ani haseł. Refresh robi klient (SDK).
- Osobne projekty Firebase dla dev i prod = osobne klucze, osobni userzy testowi.
