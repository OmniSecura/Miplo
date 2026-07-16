# 0002 — Monolit modularny zamiast mikroserwisów

Data: 2026-07-16
Status: przyjęte

## Kontekst
Rozważane: monolit, mikroserwisy, monorepo z wieloma serwisami, osobne repo per serwis.
Naturalny odruch ciągnie ku mikroserwisom.

## Decyzja
Jeden serwis FastAPI podzielony na moduły domenowe (users, games, shelf, matchmaking,
venues), jedno repo, jedno wdrożenie na Cloud Run.

## Dlaczego
- Mikroserwisy rozwiązują problemy, których na MVP nie ma (niezależne skalowanie,
  wiele zespołów, izolacja awarii), a dokładają natychmiastowy koszt (sieć między
  serwisami, transakcje rozproszone, N× deploye/monitoring).
- Solo-developer + zero userów → mikroserwisy to "distributed monolith": cała
  złożoność rozproszenia, żadnej z zalet.
- Czyste granice między modułami (komunikacja przez `service`) pozwalają rozciąć
  po szwach później, jeśli zajdzie konkretna potrzeba.

## Kiedy zrewidować
Gdy pojawi się konkretny sygnał: moduł o radykalnie innym profilu obciążenia,
inny runtime (np. ML), zespół wchodzący sobie w drogę, albo inne wymogi compliance.
