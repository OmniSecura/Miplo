# Architektura — Miplo

Skrót jak system jest zbudowany. Uzasadnienia poszczególnych decyzji: `decisions/`.

## Ogólny kształt

Monolit modularny: jeden serwis FastAPI podzielony wewnętrznie na moduły domenowe,
jedna baza PostgreSQL, jedno wdrożenie na Cloud Run.

```
Aplikacja (web/PWA, później mobile)
        │  HTTPS + token Firebase
        ▼
FastAPI (Cloud Run)  ── weryfikuje token Firebase, dalej pracuje na users.id
        │
        ├── moduł users         (tożsamość, profil, avatar)
        ├── moduł games         (proxy + cache do BGG)   [dojdzie]
        ├── moduł shelf         (półka, gry usera)       [dojdzie]
        ├── moduł matchmaking   (kto w okolicy ma X)     [dojdzie]
        └── moduł venues        (mapa miejscówek)        [dojdzie]
        │
        ▼
PostgreSQL (Cloud SQL) — jedna baza, users.id jako kotwica dla wszystkiego
Firebase Storage (GCS) — avatary graczy (webp, publiczny odczyt)
Redis — cache danych z BGG (24h)
Secret Manager — hasła do bazy, klucz admina Firebase
```

## Zasady, które trzymają porządek

- Każdy moduł ma stały układ folderów: `models / schemas / services / routers`.
  Routery nie dotykają bazy — WSZYSTKIE operacje na bazie (i commity) robi
  warstwa `service`.
- Moduły gadają ze sobą przez warstwę `service`, nie sięgają sobie do modeli.
  Dzięki temu późniejsze wydzielenie modułu do osobnego serwisu jest łatwe.
- Każdy moduł "posiada" swoje tabele; brak dzikich joinów w poprzek domen.
- Firebase Auth dotykany tylko w `core/auth.py`, Storage tylko w `core/storage.py`
  i `users/services/avatar_service.py`. Reszta kodu nie wie, że Firebase istnieje.
  Szczegóły integracji: `docs/FIREBASE.md`, decyzja: `decisions/0005-firebase-storage-avatary.md`.
- Autoryzacja (kto co może) zawsze po naszej stronie — tożsamość bierzemy
  ze zweryfikowanego tokenu, nigdy z tego, co klient poda w payloadzie.
- API bez wersjonowania w URL (brak `/v1/`) — jeden klient (nasz front),
  wersjonujemy dopiero, gdy pojawi się konsument, którego nie kontrolujemy.
- Błędy API to kody, nie teksty: `{"detail": {"error_code": "user_not_found"}}`.
  Tłumaczenie kodu na komunikat w języku usera robi frontend (i18n) — kod
  raz opublikowany jest wieczny i niezależny od języka.

## Kluczowe źródło danych

BoardGameGeek XML API 2 — dane gier, oceny, ranking, okładki, kolekcje userów.
Wymogi: cache (~24h), atrybucja "Powered by BoardGameGeek data". Tylko odczyt
kolekcji po publicznym nicku — NIE logowanie przez BGG (nieoficjalne, ryzykowne).
