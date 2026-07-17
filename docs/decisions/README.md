# Decyzje architektoniczne Miplo

ADR-y zapisują decyzje, ich kontekst i konsekwencje. Przyjętego ADR nie przepisujemy
po cichu; istotna zmiana powinna dostać kolejny numer albo jawne uzupełnienie.

| ADR | Decyzja | Status |
|---|---|---|
| [`0001`](0001-firebase-zamiast-wlasnego-auth.md) | Firebase Auth zamiast własnego systemu haseł i tokenów | przyjęte |
| [`0002`](0002-monolit-modularny.md) | modularny monolit zamiast mikroserwisów | przyjęte |
| [`0003`](0003-jedna-baza-postgres.md) | jedna relacyjna baza PostgreSQL | przyjęte |
| [`0004`](0004-cloud-run-i-repo.md) | Cloud Run, Secret Manager i strategia repo | przyjęte |
| [`0005`](0005-firebase-storage-avatary.md) | Firebase Storage dla publicznych i moderowanych mediów | przyjęte |
| [`0006`](0006-bgg-proxy-cache.md) | BGG wyłącznie przez backend z cache PostgreSQL | przyjęte |
| [`0007`](0007-import-katalogu-bgg.md) | operatorski import dumpa i leniwe wzbogacanie | przyjęte |
| [`0008`](0008-custom-games.md) | BGG i custom games we wspólnym katalogu | przyjęte |
| [`0009`](0009-moderacja-mediow-gier.md) | niezależna moderacja gry, mediów, modelu i barcode | przyjęte |
| [`0010`](0010-dwuczesciowy-glb-bez-csg.md) | dwuczęściowy GLB generowany bez CSG/trimesh | przyjęte |
| [`0011`](0011-dwutorowy-dostep-administratorski.md) | admin Firebase albo uniwersalny klucz operatorski | przyjęte |
| [`0012`](0012-barcode-per-wersja-jezykowa.md) | jeden zatwierdzony barcode na wersję językową | przyjęte |

