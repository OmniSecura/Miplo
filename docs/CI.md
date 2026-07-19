# CI/CD — konfiguracja GitHub

Pipeline znajduje się w `.github/workflows/ci.yml` i uruchamia pięć równoległych
jobów: `Lint & format`, `Type check`, `Tests`, `Security scan` oraz
`Docker build & scan`. Działa dla pull requestów do `main`, pushy do `main` i
ręcznego `workflow_dispatch`.

## Pierwsze uruchomienie

1. Wypchnij branch `chore/ci` i otwórz pull request do `main`.
2. Wejdź w GitHub → **Actions → CI** i sprawdź wszystkie pięć jobów.
3. Workflow nie wymaga sekretów projektu: testy Firebase i BGG są izolowane,
   a smoke test generuje jednorazowy klucz Firebase usuwany razem z runnerem.
4. Jeżeli repozytorium jest prywatne, włącz **Settings → Code security →
   Dependency graph**, aby workflow `Dependency review` mógł działać.

Nie dodawaj do GitHub Actions prawdziwego `FIREBASE_ADMIN_CREDENTIALS`,
`BGG_API_TOKEN`, `ADMIN_API_KEY` ani produkcyjnego `DATABASE_URL`.

## Ochrona `main`

Po pierwszym zakończonym workflow GitHub zna nazwy statusów. Skonfiguruj
**Settings → Rules → Rulesets → New branch ruleset** (w starszym UI:
**Branches → Add branch protection rule**):

1. Nazwa rulesetu: `protect-main`.
2. Target branches: `main`.
3. Włącz **Require a pull request before merging**.
4. Nie wymagaj approval — projekt jest prowadzony solo.
5. Włącz **Require status checks to pass** oraz **Require branches to be up to date**.
6. Dodaj wymagane statusy:
   - `Lint & format`;
   - `Type check`;
   - `Tests`;
   - `Security scan`;
   - `Docker build & scan`;
   - `Dependency review`.
7. Włącz **Block force pushes**, **Block deletions** i brak omijania reguł.
8. Zapisz ruleset jako aktywny.

Statusów nie da się wybrać przed ich pierwszym pojawieniem się, dlatego ochronę
ustawia się po pierwszym runie workflow.

## Co sprawdzają joby

- `Lint & format`: Ruff bez automatycznej modyfikacji kodu w CI.
- `Type check`: łagodny na start Mypy z pluginem Pydantic.
- `Tests`: PostgreSQL 16 i Redis 7 jako service containers, pytest i raport coverage.
- `Security scan`: `pip-audit`, Bandit oraz Gitleaks na pełnej historii Git.
- `Docker build & scan`: Hadolint, BuildKit cache, Trivy HIGH/CRITICAL, brak sekretów,
  limit obrazu 250 MB oraz prawdziwy request do `/health` uruchomionego kontenera.

Raport HTML coverage jest dostępny przez siedem dni jako artifact `coverage-report`.

## Dependabot

`.github/dependabot.yml` otwiera cotygodniowe aktualizacje Pythona oraz miesięczne
aktualizacje Dockera i GitHub Actions. Aktualizacje minor/patch Pythona są grupowane,
aby nie tworzyć kilkunastu osobnych pull requestów.

## Ograniczenia

- GitHub Actions i branch rules są konfiguracją zewnętrzną — ich działania nie da
  się w pełni potwierdzić lokalnie.
- Czas poniżej ośmiu minut trzeba potwierdzić po pierwszym runie na GitHub.
- Trivy korzysta z aktualnej bazy CVE, więc wynik może zmieniać się bez zmiany kodu.
