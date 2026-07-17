# 0011 — Firebase admin lub uniwersalny klucz operatorski

Data: 2026-07-17  
Status: przyjęte

## Kontekst

Moderacja musi działać zarówno z przyszłego panelu przypisanego do konkretnego
administratora, jak i ręcznie ze Swaggera lub z kontrolowanego skryptu. Samo
`User.is_admin` wymaga wcześniejszego logowania Firebase, natomiast publiczny
frontend nie może znać uniwersalnego sekretu.

## Decyzja

- endpointy `/api/admin/moderation/*` akceptują aktywnego usera Firebase z
  `is_admin=true` albo nagłówek `X-Admin-Key`,
- wartość nagłówka musi odpowiadać `ADMIN_API_KEY` z `.env`/Secret Managera,
- sekret ma minimum 32 znaki i jest porównywany przez `secrets.compare_digest`,
- podany błędny klucz jest natychmiast odrzucany; nie uruchamiamy wtedy fallbacku
  do Firebase,
- klucz nie jest zwracany przez API, logowany ani umieszczany w frontendzie,
- zwykłe endpointy aplikacji nadal przyjmują wyłącznie Firebase ID token.

## Konsekwencje

- operator może moderować przez Swagger bez modyfikowania rekordu usera,
- wyciek jednego sekretu daje dostęp do całej moderacji, dlatego klucz musi być
  przechowywany jak hasło produkcyjne, rotowany i ograniczony do backendu,
- indywidualne konta `is_admin` pozostają zalecanym mechanizmem dla docelowego
  panelu, ponieważ umożliwią później pełny audyt działań per administrator.
