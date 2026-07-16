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
        ├── moduł users        (tożsamość, profil, miasto)
        ├── moduł games        (proxy + cache do BGG)
        ├── moduł shelf         (półka, gry usera)   [dojdzie]
        ├── moduł matchmaking   (kto w okolicy ma X)  [dojdzie]
        └── moduł venues        (mapa miejscówek)     [dojdzie]
        │
        ▼
PostgreSQL (Cloud SQL) — jedna baza, users.id jako kotwica dla wszystkiego
Redis — cache danych z BGG (24h)
Secret Manager — hasła do bazy, klucz admina Firebase
```

## Zasady, które trzymają porządek

- Moduły gadają ze sobą przez warstwę `service`, nie sięgają sobie do modeli.
  Dzięki temu późniejsze wydzielenie modułu do osobnego serwisu jest łatwe.
- Każdy moduł "posiada" swoje tabele; brak dzikich joinów w poprzek domen.
- Firebase dotykany tylko w `core/auth.py`. Reszta kodu nie wie, że istnieje.
- Autoryzacja (kto co może) zawsze po naszej stronie — tożsamość bierzemy
  ze zweryfikowanego tokenu, nigdy z tego, co klient poda w payloadzie.

## Kluczowe źródło danych

BoardGameGeek XML API 2 — dane gier, oceny, ranking, okładki, kolekcje userów.
Wymogi: cache (~24h), atrybucja "Powered by BoardGameGeek data". Tylko odczyt
kolekcji po publicznym nicku — NIE logowanie przez BGG (nieoficjalne, ryzykowne).
