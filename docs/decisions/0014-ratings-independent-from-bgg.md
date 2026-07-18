# ADR 0014: oceny Miplo niezależne od BGG i półki

Status: przyjęte

## Kontekst

Ocena BGG opisuje globalną społeczność, a Miplo potrzebuje własnego wyniku i
recenzji. Posiadanie gry nie jest warunkiem wystawienia opinii, zaś usunięcie
egzemplarza z półki nie powinno kasować historii usera.

## Decyzja

- Oceny są osobną domeną i tabelą `game_ratings` z relacją przez stabilny,
  wewnętrzny `game_id`; HTTP identyfikuje grę wyłącznie przez `slug`.
- Nie duplikujemy sluga w ocenach. Zmiana publicznego sluga nie wymaga przepisywania
  relacji; migracje bazy zachowują wartości PK i ustawiają sekwencje po imporcie.
- Dane BGG aktualizuje wyłącznie jawna biała lista. Pola Miplo nigdy nie są jej
  częścią.
- Oficjalny wynik Miplo jest publiczny od trzech widocznych ocen.
- Ukrycie moderacyjne wyłącza całą ocenę z list i agregatów.
- Oceny BGG można importować z kolekcją, ale nie wolno nimi nadpisywać
  istniejącej opinii Miplo.
- Reakcje helpful/not-helpful nie wchodzą do bieżącego zakresu.

## Konsekwencje

Game detail i półka mogą pokazywać Miplo score bez kosztownego AVG przy każdym
odczycie. Każda operacja usuwająca oceny musi przeliczyć denormalizowane agregaty;
dotyczy to również twardego usunięcia konta.
