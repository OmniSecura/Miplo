# Audyt bezpieczeństwa — 2026-07-18

## Wynik

Wszystkie podatności znalezione w tym przebiegu zostały usunięte lub zastąpione
jawną, ograniczoną decyzją operacyjną. Nie znaleziono otwartych problemów o
ważności high/critical w kodzie objętym audytem.

## Zakres i wykonane poprawki

- Firebase: revocation/disabled check, stabilne 401/503 i bezpieczne usuwanie konta;
- abuse/DoS: globalny limit przed auth, per-endpoint limity, Redis wymagany na prod;
- HTTP: jawny CORS i Host allowlist, HSTS na prod, `nosniff`, `DENY`, `no-store`;
- BGG: `defusedxml`, stream limit 5 MB, przypięty oficjalny host, brak redirectów,
  globalny throttle per proces, deduplikacja in-flight i bounded refresh queue;
- CSV BGG: admin-only, 50 MB, ścisły nagłówek/content-type, whitelisty pól,
  atomowa transakcja i PostgreSQL advisory lock;
- upload: limity body/chunk/pikseli, dekodowanie i re-encoding, prywatny staging;
- GLB: jeden domyślny slot CPU, aktywny request, odzyskanie osieroconego joba;
- SQL: zapytania parametryzowane; LIKE ma escape wildcardów;
- RODO: avatar cache skrócony do 5 minut, avatar i rekord lokalny są usuwane;
- admin: constant-time key comparison i bezsekretowy audit log;
- skrypty DB: stare MySQL zastąpione PostgreSQL bez hasła w argv i bez SQL z inputu;
- ratings: agregaty batch przeliczane jednym zbiorczym UPDATE.

## Weryfikacja

- `unittest`: 76/76 testów OK;
- `compileall`: OK;
- `pip check`: brak uszkodzonych zależności;
- `pip-audit`: brak znanych CVE w `services/requirements.txt`;
- Bandit: 0 niewyjaśnionych wyników;
- `git diff --check`: brak błędów whitespace;
- skan znaków bidi/Trojan Source: brak literalnych znaków sterujących;
- skan sekretów w plikach śledzonych: brak znalezionych sekretów.

## Granice audytu i ryzyka operacyjne

Audyt nie jest dowodem matematycznym braku przyszłych podatności. Nie wykonywał
pentestu działającego wdrożenia, testu IAM/GCP ani prawdziwego PostgreSQL,
Firebase, Redis i BGG. Przed produkcją trzeba dodatkowo:

1. ustawić `rediss://`, dokładne `ALLOWED_HOSTS` i `ALLOWED_ORIGINS`;
2. ograniczyć IAM konta Firebase/GCP i rotować klucze operatorskie;
3. włączyć Cloud Armor/WAF oraz alerty dla 401/429/503 i audit logów;
4. ustawić timeout Cloud Run większy niż typowy czas GLB;
5. przy większym ruchu przenieść GLB do trwałej kolejki z retry/idempotency;
6. wykonywać `pip-audit`, Bandit i testy w CI przy każdym merge'u.
7. do czasu distributed throttle ograniczyć liczbę instancji wykonujących ruch BGG.
