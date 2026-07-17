# 0005 — Firebase Storage do avatarów (nie S3, nie dysk)

Data: 2026-07-17
Status: przyjęte

## Kontekst
Avatary graczy potrzebują hostingu plików: upload, optymalizacja, publiczny URL.
Rozważane: Firebase Storage (Cloud Storage pod spodem), AWS S3 / R2 (Cloudflare),
serwowanie z dysku serwera (Cloud Run).

## Decyzja
Firebase Storage (bucket GCS zarządzany przez Firebase). Backend uploaduje przez
Admin SDK, pliki publicznie dostępne pod stałym URL-em, bez tokenów.

## Dlaczego
- Firebase Auth już w projekcie — Admin SDK zaciągnięty; Storage to jedna linia
  konfiguracji, nie kolejna usługa z osobnym zestawem kluczy.
- GCS pod spodem: ta sama infrastruktura co S3, tylko jeden rachunek GCP
  zamiast dwóch chmur.
- Cloud Run jest stateless — dysk efemeryczny, po skalowaniu instancji pliki
  znikają. Montowanie GCS FUSE możliwe, ale wolne i komplikuje deploy.
- Darmowe limity (5 GB storage, 1 GB/dzień download) wystarczą na długo —
  avatar 400x400 webp waży ~10-30 KB; 5 GB = ~170 000 avatarów.
- Publiczny odczyt bez tokenów = proste `<img src="...">`, CDN Google
  robi resztę. Cache busting przez `?v=` (milisekundy).
- Reguły bezpieczeństwa Firebase zablokowane na `allow read, write: if false` —
  upload wyłącznie przez Admin SDK (pomija reguły), klient nie ma
  bezpośredniego dostępu do zapisu.

## Implementacja
- Ścieżka: `avatars/{firebase_uid}/avatar.webp` — stała na użytkownika,
  nadpisywana przy każdym uploadzie (zero śmieci w buckecie).
- Optymalizacja przed uploadem: Pillow re-encode do webp 400x400, EXIF
  usuwany, przezroczystość → białe tło.
- Walidacja 3-warstwowa + limit pikseli (24 Mpx) przed dekodowaniem
  (obrona przed bombą pikselową).
- `DELETE /me` czyści avatar z bucketa przed usunięciem rekordu z bazy.

## Konsekwencje
- Zależność od GCP Storage — akceptowalna, bo reszta infry (Cloud Run,
  Cloud SQL, Secret Manager) też jest w GCP.
- Plan Blaze (pay-as-you-go) wymagany do włączenia Storage — kartę trzeba
  podpiąć, ale darmowe limity zostają.
- Migracja na S3/R2 w przyszłości = zmiana jednego serwisu (`avatar_service.py`
  + `core/storage.py`), reszta kodu nie wie, skąd URL.

## Kiedy zrewidować
Gdy egress z GCS zacznie kosztować (>1 TB/mies) — wtedy Cloudflare R2
(zero egress fee) lub CDN przed bucketem.
