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

Walidacja Pydantic/FastAPI również korzysta z tego kontraktu. Zwraca `422` oraz
`validation_error`; `details.errors` zawiera wyłącznie stabilną lokalizację pola
i techniczną regułę, bez angielskiego komunikatu i wartości wejściowej:

```json
{
  "detail": {
    "error_code": "validation_error",
    "details": {"errors": [{"field": "rating", "rule": "multiple_of"}]}
  }
}
```

## Auth i users

| Kod | Typowy status | Znaczenie |
|---|---:|---|
| `unauthorized` | 401 | brak poświadczeń |
| `invalid_token` | 401 | niepoprawny Firebase ID token |
| `token_expired` | 401 | wygasły token; klient powinien odświeżyć go przez Firebase SDK |
| `token_revoked` | 401 | token odwołany, konto disabled albo usunięte; wymagane ponowne logowanie |
| `auth_provider_unavailable` | 503 | Firebase Auth chwilowo niedostępny |
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
| `invalid_csv_format` | 400 | błędny typ, rozszerzenie lub wymagany nagłówek CSV |
| `csv_too_large` | 413 | plik importu przekracza 50 MB |
| `import_already_running` | 409 | import działa już w procesie lub innej instancji |
| `catalog_import_failed` | 500 | awaria importera |

`invalid_import_file`, `import_not_configured` i `invalid_import_key` pozostają
historycznymi kodami kontraktu. Nowy import używa wspólnego auth administratora.

## Shelf

| Kod | Typowy status | Znaczenie |
|---|---:|---|
| `game_already_on_shelf` | 409 | user ma już tę grę na półce lub wystąpił wyścig zapisu |
| `game_not_on_shelf` | 404 | wskazana gra nie znajduje się na półce aktualnego usera |
| `collection_import_failed` | 502 | nieoczekiwana awaria importu kolekcji BGG |
| `ratings_not_available` | 501 | historyczny, opublikowany kod; bieżący moduł ratings już go nie zwraca |

`collection_import_timeout` jest zarezerwowany w enumie, ale obecny kontrakt nie
kończy timeoutu błędem: po 180 sekundach zwraca częściowy `CollectionImportResult`
z nieprzetworzonymi grami doliczonymi do `failed`. `invalid_condition` pozostaje
kodem zarezerwowanym; niepoprawna wartość enumu jest obecnie standardowym `422`.

## Ratings i recenzje

| Kod | Typowy status | Znaczenie |
|---|---:|---|
| `already_rated` | 409 | user już ocenił grę; do zmiany służy PUT |
| `not_rated_yet` | 404 | brak własnej oceny do edycji/usunięcia |
| `invalid_rating_value` | 422 | niepoprawny zakres filtrów ocen |
| `review_too_short` | 422 | zarezerwowany kod; schemat Pydantic zwraca obecnie standardowe 422 |
| `review_already_reported` | 409 | ten user już zgłosił wskazaną recenzję |
| `cannot_report_own_review` | 403 | user próbuje zgłosić własną recenzję |
| `rating_hidden` | 403 | ukrytej przez moderatora oceny nie można edytować |
| `rating_not_found` | 404 | brak publicznej oceny/recenzji o wskazanym UUID |

`invalid_rating_value` z body jest zwykle standardowym błędem walidacji 422;
kod domenowy jest używany dla zależności między filtrami `min_rating` i
`max_rating`.

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
| `cover_source_unavailable` | 502 | cover wymagany jako front modelu jest niedostępny lub niepoprawny |
| `image_upload_failed` | 502 | awaria galerii |
| `gallery_limit_reached` | 409 | osiągnięto limit zdjęć gry |
| `image_not_found` | 404 | brak zdjęcia |
| `all_sides_required` | 400 | brakuje wymaganej tekstury; front jest opcjonalny tylko przy istniejącym coverze |
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
| `rate_limit_exceeded` | 429 | przekroczony limit globalny lub endpointu |
| `rate_limit_backend_unavailable` | 503 | współdzielony backend limitera jest niedostępny |
| `internal_error` | 500 | nieobsłużony wyjątek; traceback pozostaje wyłącznie w logach |
| `route_not_found` | 404 | wskazana ścieżka API nie istnieje |
| `method_not_allowed` | 405 | endpoint istnieje, ale nie obsługuje tej metody HTTP |

Udane operacje, które potrzebują komunikatu dla UI, zwracają analogiczny
`message_code`. Zgłoszenie recenzji zwraca `{"message_code":"review_reported"}`.

Źródłem prawdy dla nazw jest enum `ErrorCode` w `services/app/core/errors.py`.
