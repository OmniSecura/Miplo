# 0007 — Operatorski import rankingu BGG i leniwe wzbogacanie

Data: 2026-07-17
Status: przyjęte

> Endpoint, autoryzację, limity i atomowość importu zastępuje ADR 0016.

## Kontekst

Oficjalny dump rankingu BGG zawiera około 150 tys. rekordów i podstawowe dane,
ale nie zawiera okładek ani opisów. Pełne wzbogacenie top 5000 trwa kilkanaście
lub kilkadziesiąt minut.

## Decyzja

Dump jest przyjmowany przez `POST /api/games/import` jako CSV/JSON. Endpoint
wymaga jednocześnie Firebase Auth i operatorskiego `X-Import-Key`, ma limit 1/h,
32 MB na plik i batchuje upsert po 1000 rekordów.

`X-Import-Key` nie jest tokenem BGG ani kluczem moderacji. To dodatkowy, losowy
sekret aplikacji z `GAMES_IMPORT_KEY`. Endpoint wymaga równocześnie poprawnego
Firebase ID tokenu i tego klucza; `User.is_admin` ani `X-Admin-Key` nie zastępują
`X-Import-Key`. Klucz nie trafia do zwykłego frontendu i służy wyłącznie do
kontrolowanego importu operatorskiego.

Rekord z dumpa dostaje `cached_at=NULL`. Pełne dane są dociągane leniwie, gdy
user otwiera grę. Nie uruchamiamy długiego enrichmentu w FastAPI BackgroundTasks,
ponieważ zadanie nie jest trwałe po zakończeniu instancji Cloud Run.

## Konsekwencje

- import jest idempotentny i nie wymaga dostępu do systemu plików serwera,
- katalog i wyszukiwanie działają natychmiast dla całego dumpa,
- okładka pojawia się dopiero po pierwszym pobraniu szczegółów,
- batch commit ogranicza pamięć i długość transakcji; awaria późnego batcha nie
  cofa już poprawnie zapisanych wcześniejszych batchy,
- jeśli w przyszłości potrzebny będzie masowy enrichment, powstanie trwały worker
  (Cloud Run Jobs/Cloud Tasks), nie request HTTP ani BackgroundTasks.
