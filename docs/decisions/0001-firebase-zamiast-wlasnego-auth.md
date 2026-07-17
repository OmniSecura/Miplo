# 0001 — Firebase Auth zamiast własnego systemu logowania

Data: 2026-07-16
Status: przyjęte

## Kontekst
Potrzebne logowanie/rejestracja. Rozważane: napisanie własnego auth (jak w CyberCore)
vs gotowe rozwiązanie.

## Decyzja
Firebase Auth do logowania i rejestracji. Własna tabela `users` trzyma tylko
`firebase_uid` jako most + dane apki (miasto, publiczny `tag`, profil). Hasła i tożsamość zostają
po stronie Firebase.

## Dlaczego
- Auth to pole minowe bezpieczeństwa; gotowe = eliminuje całą klasę błędów
  (hashowanie, reset hasła, session fixation).
- Apple wymaga "Sign in with Apple" gdy są inne logowania społecznościowe — Firebase to ogarnia.
- BGG nie ma oficjalnego API do logowania userów; nie budujemy logowania przez BGG.
- Czas idzie w to, co wyróżnia apkę (półka 3D, matchmaking), nie w rozwiązany problem.

## Konsekwencje
- Zależność od Firebase — akceptowalna, izolowana w `core/auth.py`.
- Autoryzacja (kto co może) nadal w całości po naszej stronie.
- Bezpieczeństwo własnej bazy (Cloud SQL) i RODO nadal na nas (model współdzielonej odpowiedzialności).
