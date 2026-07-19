# 0008 — Customowe gry we wspólnym katalogu z moderacją

Data: 2026-07-17
Status: przyjęte

## Kontekst

Nie każda niszowa, autorska lub prototypowa gra istnieje w BGG. Osobna tabela
customowych gier komplikowałaby shelf i matchmaking.

## Decyzja

BGG i custom używają tej samej tabeli `games`. Pole `source` rozróżnia pochodzenie,
a customowa gra zawsze powstaje z `is_verified=false` i `created_by_id` pobranym
z tokenu. Tylko twórca może ją edytować lub usunąć; danych BGG nie zmienia się
endpointami custom.

Okładki są przetwarzane na backendzie i zapisywane w prywatnym stagingu Firebase
Storage. Akceptacja customowej gry publikuje `games/{game_id}/cover.webp`. User
nie podaje `cover_url`.

## Konsekwencje

- jeden katalog, jeden model relacji dla shelf i matchmakingu,
- brak duplikowania logiki wyszukiwania,
- publiczny katalog ukrywa niezweryfikowane rekordy,
- usunięcie customowej gry czyści jej zasoby Storage best-effort,
- moderacja korzysta z lokalnej, nieedytowalnej przez API flagi `User.is_admin`
  albo operatorskiego `X-Admin-Key` zgodnie z ADR 0011.
