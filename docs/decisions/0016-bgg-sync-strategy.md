# ADR 0016: rozdzielone rytmy i kontrolowana synchronizacja BGG

Data: 2026-07-18  
Status: przyjęte

## Kontekst

TTL 24 h traktował opisy, ranking i dane Miplo tak, jakby zmieniały się w tym
samym tempie. Równoległe requesty nie miały globalnego odstępu, a wiele wejść w
tę samą grę mogło wysłać identyczne zapytania. Import używał osobnego sekretu i
nie rozróżniał pierwszego seedu od tygodniowej aktualizacji.

## Decyzja

- szczegóły statyczne `/thing` mają TTL 30 dni;
- `rating`, `bgg_rank`, `users_rated` aktualizuje tygodniowy CSV; API tylko
  uzupełnia te pola, gdy są puste;
- każdy fizyczny request i retry BGG przechodzi przez semafor oraz odstęp 5 s;
- równoległe fetch tej samej gry współdzielą jedno zadanie;
- publiczny stale detail może dodać tylko ograniczony best-effort refresh:
  cooldown per gra i maksymalnie 32 pending na instancję;
- gwarantowane wzbogacanie wykonuje budżetowany Cloud Run Job `nightly_sync`;
- import przenosimy do `/api/admin/games/import`, chronimy wspólnym mechanizmem
  admina, limitem `2/day`, limitem CSV 50 MB i PostgreSQL advisory lockiem;
- `mode=update` oraz `mode=full` mają jawne whitelisty; import jest atomowy;
- dane Miplo nigdy nie należą do whitelist BGG.

## Konsekwencje

ADR 0016 zastępuje TTL z ADR 0006, strategię importu i `X-Import-Key` z ADR 0007
oraz zakaz każdego publicznego best-effort refreshu z ADR 0015. Nadal nie używamy
BackgroundTasks do pracy krytycznej — nightly sync jest osobnym jobem, a refresh
po publicznym GET jest tylko optymalizacją, ograniczoną i bez wpływu na odpowiedź.

Throttle jest per proces. Przy więcej niż jednej instancji sumaryczny limit może
wzrosnąć; do czasu wdrożenia token bucket w Redis należy ograniczyć instancje
wykonujące ruch BGG. Job i import logują statystyki, ale nie treść tokenów.
