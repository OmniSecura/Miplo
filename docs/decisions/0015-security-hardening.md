# ADR 0015 — utwardzenie auth, limiterów i pracy zewnętrznej

Status: przyjęte — 2026-07-18

## Kontekst

Audyt wykazał, że poprawnie podpisany, ale odwołany token Firebase mógł działać
do wygaśnięcia, dekoratory SlowAPI nie liczyły requestów odrzuconych przez
dependencies, parser XML BGG nie był odporny na encje, a `BackgroundTasks` nie
dawał gwarancji ukończenia pracy po odpowiedzi na Cloud Run.

## Decyzja

- każdy Firebase ID token jest weryfikowany z `check_revoked=True`;
- DELETE konta: disable + revoke → usunięcie SQL → finalne delete Firebase;
- działa globalny limit per IP przed routingiem oraz limity per endpoint/user;
- `ENV=prod` wymaga współdzielonego Redis/Rediss i jawnych originów/hostów;
- BGG XML jest streamowany do 5 MB i parsowany przez `defusedxml`;
- publiczny odczyt gry nie uruchamia odświeżenia BGG po odpowiedzi;
- GLB jest generowany w ograniczonym slocie podczas aktywnego requestu;
- operacje `/api/admin/*` trafiają do bezsekretowego audit logu;
- CORS, prywatny cache, HSTS na prod i podstawowe nagłówki ochronne są wspólne.

## Konsekwencje

Revocation check wykonuje kontrolę stanu użytkownika w Firebase i może zwrócić
`503 auth_provider_unavailable`. Generowanie GLB wydłuża request, ale Cloud Run
przydziela mu CPU do końca; przed większą skalą należy przenieść tę pracę do
trwałej kolejki (Cloud Tasks/Jobs) z prywatnym stagingiem wejścia. Uniwersalny
`X-Admin-Key` pozostaje świadomą decyzją MVP — audit log identyfikuje go jako
`shared-api-key`, nie konkretną osobę.
