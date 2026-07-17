# 0009 — Osobna moderacja gry, okładki, galerii, modelu 3D i barcode

Data: 2026-07-17  
Status: przyjęte

## Kontekst

`Game.is_verified` opisuje wiarygodność rekordu gry. Nie może jednocześnie
opisywać zdjęcia wnętrza ani modelu przesłanego później do zweryfikowanej gry BGG.
Publiczny URL utworzony przed moderacją pozwalałby ominąć kolejkę bez znajomości API.

## Decyzja

- BGG tworzy zweryfikowany rekord gry; customowa gra zaczyna z `is_verified=false`.
- Galeria ma własne `GameImage.is_verified` i stan `pending/approved`.
- Model ma osobny stan oraz prywatną ścieżkę kandydata.
- Barcode ma osobny rekord `pending/approved`; publiczny lookup uwzględnia tylko
  zatwierdzony kod zweryfikowanej gry.
- Okładka customowej gry również trafia najpierw do prywatnego stagingu.
- Administrator ogląda kandydatów przez podpisane URL-e ważne 15 minut.
- Dopiero akceptacja kopiuje/nadaje publiczność docelowemu obiektowi.
- `User.is_admin` jest polem wewnętrznym, niewidocznym i nieedytowalnym przez API.
- Administrator może zablokować i odblokować wszystkie dalsze kontrybucje dla gry,
  w tym edycję customowej gry, obrazy, model i propozycje barcode.
- Po zweryfikowaniu gry każdy aktywny user może proponować zdjęcia galerii i nowy
  zestaw tekstur/model 3D; każda propozycja nadal wymaga osobnej moderacji.
- Publiczny model pozostaje niezmieniony podczas oceny zamiennika, a autor
  propozycji może wycofać tylko kandydata, nigdy zatwierdzony zasób.

## Konsekwencje

- zatwierdzenie rekordu BGG nie zatwierdza automatycznie treści społeczności,
- prywatny staging faktycznie egzekwuje moderację, nie tylko oznacza rekord flagą,
- odrzucenie usuwa blob, a publiczny katalog pokazuje tylko zatwierdzone rekordy,
- pierwszy administrator musi zostać nadany kontrolowanym SQL-em,
- panel webowy może później korzystać z tych samych endpointów co obecny Swagger.
