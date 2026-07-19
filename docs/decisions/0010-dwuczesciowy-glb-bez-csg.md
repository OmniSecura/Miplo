# 0010 — Dwuczęściowy GLB bez CSG i bez trimesh

Data: 2026-07-17
Status: przyjęte

## Kontekst

Pudełko planszówki ma denko i nałożone wieko. Demo wykorzystywało boolean
difference w `trimesh`, ale CSG wymaga dodatkowego silnika, bywa niestabilne dla
liczb zmiennoprzecinkowych i jest zbędne dla zamkniętego pudełka oglądanego z zewnątrz.

## Decyzja

Backend składa GLB 2.0 bezpośrednio ze standardowej geometrii:

- osobny node `BoxBase` — spód i dolne paski czterech boków,
- osobny node `BoxLid` — wieko i górne części boków,
- osie mają kontrakt `X=width`, `Y=height`, `Z=depth`; wieko nasuwa się po osi Z,
- `front` jest dużym wiekiem, `back` dużym spodem, a pozostałe cztery tekstury
  trafiają na odpowiadające im wąskie krawędzie,
- boczne UV dzielą jedną teksturę między denko i wieko, więc napis nie urywa się
  ani nie odwraca; przeciwległe ściany mają skompensowane kierunki UV,
- EXIF jest respektowany, oczywisty obrót 90° poprawiany z proporcji, a frontend
  może jawnie przekazać obrót `0/90/180/270` dla każdej ściany,
- sześć materiałów odpowiada `front/back/left/right/top/bottom`,
- obrazy są osadzane jako JPEG, ponieważ JPEG/PNG należą do rdzenia glTF 2.0;
  WebP wymaga rozszerzenia `EXT_texture_webp`, którego nie obsługuje każdy viewer,
- wymiary z centymetrów są konwertowane na metry wymagane przez glTF.
- fizyczny luz wieka jest niewielki, a otwarty pierścień pod rantem wypełnia
  osobny, matowy czarny materiał imitujący karton.

Nie używamy `trimesh`, `numpy`, `pygltflib` ani plików tymczasowych.

## Konsekwencje

- generator jest deterministyczny i nie zależy od silnika CSG,
- plik zawiera dwa logiczne elementy gotowe pod przyszłą animację otwierania,
- wnętrze nie ma modelowanej grubości ścianek — obecny model służy półce 3D,
- ~~ciężki job działa jako `BackgroundTasks`~~ — zmienione przez ADR 0015:
  obecnie działa podczas aktywnego requestu w ograniczonym slocie; przed skalowaniem
  należy przenieść go do Cloud Tasks/Cloud Run Jobs, aby przetrwał restart instancji.
