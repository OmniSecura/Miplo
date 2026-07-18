# ADR 0013: półka usera i synchroniczny import kolekcji BGG na MVP

Status: przyjęte

Uzupełnienie 2026-07-18: etap przejściowy z punktu 7 zakończył ADR 0014.
`import_ratings=true` i sortowanie Miplo są obecnie zaimplementowane; zachowany
opis dokumentuje zachowanie sprzed wdrożenia domeny ratings.

## Kontekst

Miplo potrzebuje prywatnego opisu posiadanego egzemplarza gry, publicznej oferty
wypożyczenia i prostego przeniesienia kolekcji z BoardGameGeek. Dane katalogowe
gier są już wspólne i cache'owane w tabeli `games`. Domena `ratings` jeszcze nie
istnieje, a trwała kolejka zadań nie jest częścią obecnego wdrożenia.

## Decyzja

1. Wprowadzamy osobną tabelę `shelf_items` z unikalną parą user–gra. Nie kopiujemy
   do niej tytułów ani okładek.
2. Własność każdej operacji wynika wyłącznie z usera zwróconego przez auth.
3. Publiczny widok półki ukrywa prywatne notatki i warunki niewypożyczalnej gry.
4. Szczegóły gry mają opcjonalny kontekst `on_my_shelf`/`my_shelf_item`, aby strona
   gry nie wymagała dodatkowego requestu. Brak tokenu oznacza anonimowość, ale
   błędnego tokenu nie ignorujemy.
5. Import kolekcji działa synchronicznie na MVP, z limitem 180 sekund, paczkami po
   20 BGG ID, pięciosekundowym odstępem i limitem endpointu `2/hour`.
6. Timeout daje częściowy wynik, a import jest addytywny — nigdy nie usuwa półki.
7. `import_ratings=true` zwraca `501 ratings_not_available` do czasu wdrożenia
   domeny ratings. Nie ignorujemy flagi i nie raportujemy pozornego sukcesu.
8. Na półkę można dodać tylko zweryfikowaną grę, aby nie ujawniać wpisów z kolejki
   moderacji przez publiczny endpoint półki.
9. Kontrakt HTTP identyfikuje grę wyłącznie unikalnym slugiem. `games.id` pozostaje
   wewnętrznym kluczem obcym i nie jest wymagany przez frontend półki.

## Konsekwencje

- Frontend może obsłużyć katalogowy i właścicielski wariant jednej strony gry
  jednym requestem.
- Import dużej kolekcji może trwać kilkadziesiąt sekund i wymaga widocznego stanu
  postępu. Proces przerwany wraz z instancją Cloud Run nie ma gwarancji wznowienia.
- Gdy pojawi się trwała kolejka, import można przenieść do joba z pollingiem bez
  zmiany modelu półki.
- Po wdrożeniu ratings opcje `miplo_rating` oraz `import_ratings=true` dostaną
  implementację w tej domenie, nie w tabeli `shelf_items`.
