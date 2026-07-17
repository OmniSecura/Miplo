# 0005 — Firebase Storage jako bucket publicznych mediów

Data: 2026-07-17
Status: przyjęte

## Kontekst
Avatary graczy i okładki customowych gier potrzebują hostingu plików: upload,
optymalizacja i publiczny URL.
Rozważane: Firebase Storage (Cloud Storage pod spodem), AWS S3 / R2 (Cloudflare),
serwowanie z dysku serwera (Cloud Run).

## Decyzja
Podjęta decyzja: używamy Firebase Storage (bucketa GCS zarządzanego przez
Firebase). Backend uploaduje przez Admin SDK. Avatary są publiczne od razu;
treści społecznościowe gier pozostają prywatne do chwili moderacji, a następnie
są dostępne pod stałym URL-em bez tokenów odczytu.

## Dlaczego
- Firebase Auth już w projekcie — Admin SDK zaciągnięty; Storage to jedna linia
  konfiguracji, nie kolejna usługa z osobnym zestawem kluczy.
- GCS pod spodem: ta sama infrastruktura co S3, tylko jeden rachunek GCP
  zamiast dwóch chmur.
- Cloud Run jest stateless — dysk efemeryczny, po skalowaniu instancji pliki
  znikają. Montowanie GCS FUSE możliwe, ale wolne i komplikuje deploy.
- Koszt zależy od aktualnego cennika Google Cloud/Firebase; przed produkcją
  konfigurujemy budżet i alerty zamiast opierać architekturę na stałym limicie free tier.
- Publiczny odczyt bez tokenów = proste `<img src="...">`, CDN Google
  robi resztę. Cache busting przez `?v=` (milisekundy).
- Reguły bezpieczeństwa Firebase zablokowane na `allow read, write: if false` —
  upload wyłącznie przez Admin SDK (pomija reguły), klient nie ma
  bezpośredniego dostępu do zapisu.

## Implementacja
- Ścieżki docelowe obejmują avatar, okładkę, galerię i `box_model.glb`.
- Kandydaci okładek, zdjęć i modeli są prywatni; podgląd moderatora używa
  podpisanego URL-a, a akceptacja nadaje publiczny odczyt.
- Optymalizacja przed uploadem zależy od zasobu: avatar → WEBP 400×400,
  okładka → WEBP do 800 px, galeria → WEBP do 1600 px, tekstury GLB → JPEG
  do 1024 px. Oryginały i EXIF nie trafiają do trwałego Storage.
- Walidacja 3-warstwowa + limit pikseli (24 Mpx) przed dekodowaniem
  (obrona przed bombą pikselową).
- `DELETE /me` czyści avatar z bucketa przed usunięciem rekordu z bazy.

## Konsekwencje
- Zależność od GCP Storage — akceptowalna, bo reszta infry (Cloud Run,
  Cloud SQL, Secret Manager) też jest w GCP.
- Plan Blaze (pay-as-you-go) wymagany do włączenia Storage — kartę trzeba
  podpiąć, ale darmowe limity zostają.
- Migracja na S3/R2 w przyszłości = zmiana `core/storage.py` oraz serwisów plików;
  routery i kontrakty domenowe pozostają bez zmian.

## Kiedy zrewidować
Gdy egress z GCS zacznie kosztować (>1 TB/mies) — wtedy Cloudflare R2
(zero egress fee) lub CDN przed bucketem.
