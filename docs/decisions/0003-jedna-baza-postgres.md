# 0003 — Jedna baza PostgreSQL z wieloma tabelami

Data: 2026-07-16
Status: przyjęte

## Kontekst
Obawa o przeciążenie jednej bazy, do której uderza cała apka.

## Decyzja
Jedna baza PostgreSQL (Cloud SQL), kilkanaście tabel, `users.id` jako kotwica
dla wszystkich danych usera (shelf_items, wishlist, play_sessions...).

## Dlaczego
- Liczba tabel nie obciąża bazy — obciąża ją ruch bez indeksów i bez cache.
- Kluczowa funkcja (matchmaking "kto w mieście ma grę X") to JOIN między tabelami;
  jedna baza = jedno szybkie zapytanie. Wiele baz = zszywanie w kodzie, wolno.
- Postgres obsługuje tysiące zapytań/s przy dobrych indeksach; MVP jest o rzędy
  wielkości poniżej granicy.

## Dźwignie skalowania (po kolei, gdy ruch przyjdzie)
Indeksy → connection pooling (PgBouncer) → cache (Redis) → większa instancja →
read replica → (dużo później) partycjonowanie/sharding. Wszystkie działają
na JEDNEJ bazie; dzielenie na wiele baz to osobna decyzja, nie lekarstwo na obciążenie.

## Indeksy krytyczne dla matchmakingu
`users.city`, oraz `shelf_items(bgg_id, lendable)` — pod zapytanie
"kto w mieście X ma grę Y do wypożyczenia".
