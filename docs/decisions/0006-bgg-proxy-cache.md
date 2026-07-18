# 0006 — BGG przez backend z cache w PostgreSQL

Data: 2026-07-17  
Status: przyjęte

> TTL 24 h został zastąpiony przez strategię 30 dni + tygodniowy CSV w ADR 0016.

## Kontekst

Miplo potrzebuje katalogu dziesiątek tysięcy gier. Bezpośrednie requesty klientów
do BoardGameGeek utrudniają kontrolę limitów, ujawniają token aplikacji i łamią
założenie server-side cache.

## Decyzja

Jedynym klientem BGG jest `core/bgg_client.py`. Frontend rozmawia tylko z FastAPI.
Pełne dane są cache'owane w tabeli `games`; wyszukiwanie zewnętrzne nie zapisuje
50 wyników, lecz dopiero wybór konkretnej gry (`/games/bgg/{bgg_id}`) robi upsert.
TTL wynosi domyślnie 24 godziny.

## Konsekwencje

- token BGG pozostaje po stronie serwera,
- można centralnie egzekwować timeout, retry HTTP 202 i rate limiting,
- katalog działa z lokalnego cache również podczas awarii BGG,
- pierwszy fetch niecache'owanej gry zależy od dostępności BGG,
- frontend musi pokazać wymaganą atrybucję „Powered by BoardGameGeek data”.

Brak tokenu w dev nie blokuje serwera; tylko endpointy wychodzące do BGG zwracają
`bgg_not_configured`.
