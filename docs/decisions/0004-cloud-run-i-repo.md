# 0004 — Cloud Run (nie GKE) i strategia repo

Data: 2026-07-16
Status: przyjęte

## Kontekst
Hosting backendu i podział repozytoriów. Odruch (z pracy) ciągnie ku GKE/Kubernetes.

## Decyzja
- **Hosting:** Cloud Run (serverless, skaluje do zera). Nie GKE.
- **Sekrety:** GCP Secret Manager. Nie self-hosted Vault.
- **Repo:** monorepo dla backend + web/PWA. Mobile → osobne repo, gdy dojdzie.
- **DEV/PROD:** oba środowiska, ale DEV mocno okrojony (najmniejsze instancje,
  baza wyłączana poza pracą).

## Dlaczego
- GKE to stały koszt (setki zł/mies) za sam fakt, że klaster stoi — spalanie
  pieniędzy przy zero userów. Cloud Run: płacisz za realne żądania.
- Secret Manager: managed, grosze, zero utrzymania. Vault dokłada operację
  (unseal, pilnowanie strażnika) bez zwrotu na tym etapie.
- Backend + web mają jeden cykl wydawniczy → monorepo. Mobile ma inny cykl
  (review App Store/Google Play, inny toolchain) → osobne repo, gdy dojdzie.
- Klej między repo: OpenAPI z FastAPI → generowane typy po stronie frontu.

## Kiedy zrewidować
Dedyk/VPS (Hetzner, jak CyberCore) rozważyć przy stałym, przewidywalnym ruchu,
gdy rachunek Cloud Run zaczyna boleć (rząd $300-500/mies).
