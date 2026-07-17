# Kontrakt błędów API

Błędy domenowe mają stabilny, niezależny od języka format:

```json
{
  "detail": {
    "error_code": "game_not_found",
    "details": {}
  }
}
```

`details` jest opcjonalne i może zawierać dane techniczne, np. `max_bytes` albo
`retry_after`. Frontend mapuje `error_code` na tekst przez i18n. Opublikowanego
kodu nie zmieniamy ani nie wykorzystujemy później w innym znaczeniu.

Walidacja strukturalna Pydantic/FastAPI zwraca standardowe `422` z listą pól w
`detail`; błędy domenowe używają obiektu z `error_code`.
`validation_error` pozostaje zarezerwowany na przyszłe ujednolicenie odpowiedzi
422 i obecnie nie zastępuje natywnego formatu FastAPI.

## Auth i users

| Kod | Typowy status | Znaczenie |
|---|---:|---|
| `unauthorized` | 401 | brak poświadczeń |
| `invalid_token` | 401 | niepoprawny lub odwołany Firebase ID token |
| `token_expired` | 401 | wygasły token; klient powinien odświeżyć go przez Firebase SDK |
| `forbidden` | 403 | ogólny brak uprawnień |
| `admin_required` | 403 | lokalny user nie jest administratorem |
| `admin_api_key_not_configured` | 503 | operatorska ścieżka kluczem nie jest skonfigurowana |
| `invalid_admin_api_key` | 401 | błędny `X-Admin-Key` |
| `user_not_found` | 404 | profil nie istnieje albo jest nieaktywny |
| `user_inactive` | 403 | konto jest zdezaktywowane |
| `tag_taken` | 409 | publiczny tag jest zajęty |

`cannot_edit_other_user`, `display_name_too_long` i `city_required` pozostają
zarezerwowane w enumie jako stabilne kody kontraktu; obecna walidacja lub
struktura endpointów zwykle odrzuca te przypadki wcześniej.

## Games, BGG i import

| Kod | Typowy status | Znaczenie |
|---|---:|---|
| `game_not_found` | 404 | brak publicznej gry lub wskazanego slugu |
| `game_title_exists` | 409 | konflikt tytułu customowej gry |
| `cannot_edit_bgg_game` | 403 | próba edycji rekordu BGG endpointem custom |
| `not_game_owner` | 403 | operacja niedozwolona dla tego usera |
| `invalid_game_types` | 400 | niepoprawna lista typów |
| `invalid_player_range` | 400 | `max_players < min_players` |
| `bgg_not_configured` | 503 | brak tokenu BGG |
| `bgg_unavailable` | 502 | timeout, odpowiedź techniczna lub błędny XML BGG |
| `bgg_rate_limited` | 503 | BGG zwróciło limit |
| `invalid_bgg_username` | 400 | niepoprawny nick BGG w izolowanym kliencie |
| `invalid_import_file` | 400 | niepoprawny CSV/JSON |
| `catalog_import_failed` | 500 | awaria importera |
| `import_not_configured` | 503 | brak `GAMES_IMPORT_KEY` |
| `invalid_import_key` | 403 | błędny `X-Import-Key` |

`collection_import_failed` jest zachowany dla przyszłego modułu shelf; endpoint
importu kolekcji obecnie nie istnieje.

## Barcode

| Kod | Typowy status | Znaczenie |
|---|---:|---|
| `barcode_not_found` | 404 | brak zatwierdzonego mapowania |
| `invalid_barcode_format` | 400 | niepoprawny format lub suma kontrolna |
| `game_barcode_exists` | 409 | kod należy już do rekordu/propozycji |
| `barcode_proposal_pending` | 409 | dla gry i języka istnieje oczekująca propozycja |
| `barcode_proposal_not_found` | 404 | moderator wskazał nieistniejące UUID |
| `barcode_not_pending` | 409 | ponowna decyzja dla rozpatrzonego zgłoszenia |

`game_already_has_barcode` jest historycznym kodem zachowanym zgodnie z zasadą
nieusuwania opublikowanych kodów; nowy model pozwala na barcode per język.

## Pliki, media i moderacja

| Kod | Typowy status | Znaczenie |
|---|---:|---|
| `file_too_large` | 400 | przekroczony limit bajtów lub pikseli |
| `invalid_file_type` | 400 | niedozwolony Content-Type albo niepoprawne bajty obrazu |
| `avatar_upload_failed` | 502 | awaria uploadu avatara |
| `cover_upload_failed` | 502 | awaria okładki lub jej publikacji |
| `image_upload_failed` | 502 | awaria galerii |
| `gallery_limit_reached` | 409 | osiągnięto limit zdjęć gry |
| `image_not_found` | 404 | brak zdjęcia |
| `all_sides_required` | 400 | brakuje co najmniej jednej z sześciu tekstur |
| `model_generation_failed` | stan modelu | job GLB zakończył się błędem |
| `model_already_processing` | 409 | istnieje aktywna propozycja modelu |
| `model_not_found` | 404 | brak kandydata modelu |
| `model_not_ready_for_review` | 409 | model nie jest w stanie moderowalnym |
| `media_not_pending` | 409 | medium zostało już rozpatrzone |
| `contributions_locked` | 403 | administrator zamknął kontrybucje dla gry |

## Infrastruktura

| Kod | Status | Znaczenie |
|---|---:|---|
| `length_required` | 411 | request z body nie zawiera `Content-Length` |
| `payload_too_large` | 413 | body przekracza limit middleware |
| `rate_limit_exceeded` | 429 | przekroczony limit SlowAPI |
| `internal_error` | 500 | nieobsłużony wyjątek; traceback pozostaje wyłącznie w logach |

Źródłem prawdy dla nazw jest enum `ErrorCode` w `services/app/core/errors.py`.
