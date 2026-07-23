# 0017 — Lekkie tekstury pseudo-3D publikowane razem z GLB

Data: 2026-07-23
Status: przyjęte

## Kontekst

Katalog i półka pokazują wiele pudełek jednocześnie. Renderowanie osobnego GLB
przez WebGL dla każdego kafelka jest kosztowne, a pobranie całego modelu tylko po
to, aby wyciągnąć tekstury, marnuje transfer. Generator ma już sześć poprawnie
obróconych obrazów ścian w pamięci.

## Decyzja

W tym samym jobie co kandydat GLB backend tworzy trzy dodatkowe pliki WEBP:

- `face_front.webp` z pliku `front`,
- `face_side.webp` z pliku `left`,
- `face_top.webp` z pliku `top`.

Każdy obraz ma maksymalnie 512 px na dłuższej krawędzi, jakość 80, usunięte
metadane i tę samą korektę EXIF, proporcji oraz rotację formularza co GLB.
Kandydaci pozostają w prywatnym stagingu.

Front modelu zawsze pochodzi z istniejącej okładki gry. Backend pobiera cover
z kontrolowanego źródła i ponownie go waliduje; user przesyła `file_front`
wyłącznie wtedy, gdy gra nie ma covera. Upload nie może nadpisać istniejącej
okładki tylko na potrzeby modelu.

Akceptacja publikuje nowy, wersjonowany pakiet czterech plików. Dopiero gdy
wszystkie kopie w Storage istnieją, jeden commit ustawia `model_3d_url` oraz trzy
`box_face_*_url`. Constraint bazy wymusza komplet albo trzy wartości `NULL`.
Poprzedni pakiet jest sprzątany dopiero po udanym commicie.

## Odrzucone alternatywy

- wiele kontekstów WebGL i renderowanie GLB na każdej karcie;
- pobieranie GLB i ekstrakcja tekstur po stronie klienta;
- serwerowy snapshot przez headless OpenGL;
- nadpisywanie czterech stałych publicznych ścieżek przed commitem, ponieważ
  częściowa awaria mogłaby pokazać użytkownikom mieszankę starej i nowej wersji.

## Konsekwencje

- listy pobierają trzy małe obrazy zamiast pełnego modelu;
- gry bez nowego pakietu zwracają `NULL` i korzystają z `cover_url` oraz koloru;
- zaakceptowane wcześniej modele nie dostają automatycznego backfillu;
- wersjonowane ścieżki pozwalają bezpiecznie podmieniać pakiet i długo go cache'ować;
- cleanup Storage jest best-effort po transakcji, więc awaria sprzątania nie cofa
  poprawnej decyzji moderacyjnej.
