# 0012 — Jeden moderowany barcode na wersję językową gry

Data: 2026-07-18  
Status: przyjęte

## Kontekst

Ta sama gra planszowa może mieć różne kody EAN/UPC zależnie od wersji językowej.
Jedna kolumna `games.barcode` nie pozwalała odwzorować polskiego i angielskiego
wydania, a bezpośredni zapis community mógł zatruć publiczny lookup skanera.

## Decyzja

- barcode przechowujemy w osobnej tabeli `game_barcodes`,
- na tym etapie nie integrujemy zewnętrznej bazy barcode; mapowania buduje
  społeczność i zatwierdza administrator,
- `GameLanguage` jest enumem i obecnie zawiera wyłącznie `pl` oraz `en`,
- dla jednej gry może istnieć jeden zatwierdzony kod na każdy z tych języków,
- sam barcode jest globalnie unikalny,
- user wyłącznie proponuje kod; publiczny staje się dopiero po moderacji,
- dla pary gra–język może oczekiwać najwyżej jedna propozycja,
- propozycja zamiennika nie wyłącza starego kodu; zamiana następuje atomowo przy
  akceptacji administratora,
- publiczny lookup zwraca tylko zatwierdzone kody zweryfikowanych gier,
- `contributions/lock` blokuje również propozycje barcode,
- historycznych wartości bez informacji o języku nie klasyfikujemy automatycznie;
  migracja wymaga ręcznego wyboru `pl` albo `en`.

## Konsekwencje

- frontend przy zgłoszeniu kodu musi znać język wydania,
- `GameDetail` zwraca tablicę `barcodes`, a nie pojedyncze pole,
- polskie wznowienia tej samej gry współdzielą jeden slot `pl`; rozróżnianie
  wydań/edycji może zostać dodane później jako osobna encja, jeśli produkt będzie
  tego wymagał,
- moderacja chroni skaner przed niezweryfikowanymi mapowaniami community.
