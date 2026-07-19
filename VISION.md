# Wizja — Miplo

Wszystko, czego chcę w apce. To dokument żywy: pomysły dochodzą i się zmieniają.
Gdy pomysł dojrzewa do zrobienia → trafia do GitHub Issues jako ticket.

Dokument opisuje PRZYSZŁOŚĆ (czego jeszcze nie ma). To, co już DZIAŁA,
opisuje dokumentacja w `docs/`.

---

## Rdzeń (MVP) — bez tego nie ma apki

- **Półka 3D z grami** — pudełka jako BoxGeometry + okładki z BGG (proceduralnie,
  bez modeli 3D per gra). Będzie potrzebny skaner którym można zeskanować pudełko i stworzy się model 3D i zapisze w bazie.
- **Profil gracza z miastem** — kotwica dla całej reszty; potrzebny do kojarzenia.
- **Matchmaking lokalny** — "kto w mojej okolicy ma grę X i chce zagrać".
  Jedyny prawdziwy powód, dla którego ktoś zostaje w apce.
- **Import kolekcji z BGG** — user podaje nick z BGG → ciągniemy jego kolekcję
  (łapie też userów BG Stats i Meeplay, bo oni synchronizują z BGG).

## v1 — po walidacji rdzenia

- Mapa miejscówek (sklepy, kawiarnie, kluby)
- Umawianie spotkań + tabela wyników + historia rozgrywek
- Rangi / rankingi w stylu gier komputerowych
- Skaner kodu kreskowego (dodawanie gry na półkę)
- Wishlisty

## v2 — gdy jest już społeczność

- **Wypożyczanie P2P z kaucją + system reputacji** — najtrudniejszy technicznie
  (płatności, escrow, spory), ale najbardziej unikalny. Nikt tego nie ma.
- "Tinder gier" — swipe jako hak zaangażowania i napęd matchmakingu
- Czat / komunikacja między userami
- Eventy i turnieje

## Kiedyś / może

- Afiliacja zakupowa (Rebel, Aleplanszy itd.) — monetyzacja, nie produkt
- Sponsoring / promowane miejscówki na mapie
- Achievementy
- Pytania o kruczki w zasadach (AI)
- Ścieżki dźwiękowe (community-driven + weryfikacja)
- Własne API modeli/danych dla innych

## Osobne biznesy (NIE apka — nie mieszać do roadmapy softu)

- Własna wypożyczalnia / wynajęty pokój do grania. Apka może być lejkiem,
  ale to biznes fizyczny z innym ryzykiem.

---

## Konkurencja (stan research, lipiec 2026)

Do zapamiętania czym się różnimy:
- **BG Stats** — król trackerów, ale aspołeczny, tabelkowy. Nie ścigać się na statystykach.
- **Meeplay** (~5k), **MeepleMatch**, **Meepzy**, **Meeplr/Dice-Cat** — społecznościówki,
  słabo zaludnione, wizualnie suche.
- **Boardly** (PL) — najbliższy rywal: kojarzenie graczy, myśli o wypożyczalniach.
- **Planszeo** (PL) — polski BGG (baza, ceny, kolekcja).
- **Critical Match** (PL) — tinder do gier/RPG, wczesny, słaby w PL.

**Nasza przewaga:** półka 3D (nikt), wypożyczanie P2P (nikt), integracja wszystkiego w jedno.
**Prawdziwa bitwa:** gęsta lokalna społeczność (jedno miasto najpierw), nie kod.

---

## Dump myśli o feature, które wpadły mi do głowy, ale nie wiem czy i kiedy będą zrobione:

- **Własne modele 3D gier** — skanowanie pudełek, tworzenie modeli 3D i zapis w bazie. Te modele 3D będą wyświetlane
    w półce 3D. To jest feature, który może być unikalny i przyciągnąć użytkowników, ale wymaga sporo pracy i technologii.
    Baza będzie przechowywać te modele, co pozwoli w przyszłości na wystawienie API dla innych platform np za opłatą.
    Mówiąc modele 3D mam na myśli modle pudełek, nie figurki. Figurki to osobny temat, który może być rozwijany w przyszłości.


- **Strona danej gry** — po kliknięciu w grę na półce, użytkownik będzie mógł zobaczyć szczegóły model 3D gry, oceny, recenzje,
   dostępność w okolicy i możliwość dodania do wishlisty. Instrukcje, tutoriale, gameplay videos, news, events,
   turnieje, itp. (jeśli chodzi o tutoriale i gameplay videos można się dogadać z jakimś youtuberem, który robi recenzje gier planszowych i poprosić go o współpracę).
   To będzie miejsce, gdzie użytkownicy będą mogli dowiedzieć się więcej o grze i jej społeczności.
   Super będzie opcja soundtrack po prostu będzie puszczana muzyka pasująca do gry, np. soundtrack z gry planszowej lub muzyka tematyczna.


- **Organizacja spotkań** — użytkownicy będą mogli tworzyć wydarzenia i zapraszać innych graczy do wspólnej gry.
  Będzie można ustawić datę, godzinę, miejsce (będzie mapa podaje sie adres itp) i liczbę uczestników. Można ustawić lobby
  dla danego wydarzenia, gdzie użytkownicy będą mogli się komunikować przed spotkaniem. Wydarzenia będą mogły być publiczne lub prywatne.
  Aplikacja będzie mogła wysyłać powiadomienia do użytkowników o nadchodzących wydarzeniach, które ich interesują.
  Dla danego wydarzenia będzie miejsce na wpisywanie wyników, komentarzy i zdjęć z gry.
  Będzie można też oceniać wydarzenia i zostawiać recenzje. Jeśli będzie to event publiczny to będzie można również wystawić
  opinie organizatorowi, dzięki temu użytkownicy będą wiedziec czy dany organizator jest godny zaufania i czy warto brać udział w jego wydarzeniach.


- **System rankingów i osiągnięć** — użytkownicy będą mogli zdobywać punkty doświadczenia i odznaki za udział w wydarzeniach, wygrane gry, recenzje gier, itp.
  Będzie można tworzyć rankingi lokalne i globalne, a także porównywać swoje wyniki z innymi graczami.
  System osiągnięć będzie motywował użytkowników do aktywności i angażowania się w społeczność.
  System będzie działał na zasadzie gamifikacji, chodzi mi o rankingki jak w grach komputerowych. Bardzo fajnie jeśli rankingi
  będą przypominały grę planszową, że każdy kolejny szczebel w danej randze będzie wygladał jakby przemieszczało się na kolejne
  pola. Kiedyś jeśli miałbym współpracować z jakąś firmą sprzedającą gry, może jakieś rabaty dla najlepszych graczy w danym miesiącu,
  np. 10% zniżki na zakupy w sklepie partnerskim dla top 10 graczy w rankingu.


- **Organizowanie turniejów** — użytkownicy będą mogli tworzyć turnieje i zapraszać innych graczy do udziału.
  Będzie można ustawić zasady turnieju, liczbę uczestników, nagrody i harmonogram.
  Turnieje będą mogły być publiczne lub prywatne. Aplikacja będzie mogła wysyłać powiadomienia do użytkowników o nadchodzących turniejach, które ich interesują.
  Dla danego turnieju będzie miejsce na wpisywanie wyników, komentarzy i zdjęć z gry.
  Będzie można też oceniać turnieje i zostawiać recenzje. Jeśli będzie to turniej publiczny to będzie można również wystawić
  opinie organizatorowi, dzięki temu użytkownicy będą wiedziec czy dany organizator jest godny zaufania i czy warto brać udział w jego turniejach.


- **Mapa miejscówek** — użytkownicy będą mogli przeglądać mapę z zaznaczonymi miejscówkami, w których można grać w gry planszowe.
  Będzie można filtrować miejscówki według typu (sklep, kawiarnia, klub), lokalizacji i opinii innych użytkowników.
  Każda miejscówka będzie miała swoją stronę z informacjami o godzinach otwarcia, dostępnych grach, opiniami użytkowników i możliwością dodania do ulubionych.
  Mapka będzie w apce ale będzie możliwośc przejścia do znanych nam Google Maps i Apple Maps, żeby można było łatwo nawigować do danej miejscówki.
  W przypadku jakiegoś sponsoringu można się pokusić o wyróżnianie miejscówek na mapie, np. poprzez oznaczenie ich specjalnym kolorem lub ikoną.


- **Szafy z grami innych graczy** — użytkownicy mają możliwośc podglądu (za pozwoleniem danej osoby) szaf z grami innych graczy.
  Można napisać do gracza i umówić się na spotkanie, żeby pograć w jego gry. Można też filtrować szafy według lokalizacji, typu gier i opinii innych użytkowników.


- **Wypożyczanie gier P2P** — użytkownicy będą mogli wypożyczać gry od innych graczy w swojej okolicy.
  Będzie można ustawić zasady wypożyczenia (czas, kaucja, warunki zwrotu) i komunikować się z właścicielem gry.
  Aplikacja będzie mogła wysyłać powiadomienia do użytkowników o dostępnych grach w ich okolicy (np. z wishlisty).
  Będzie można oceniać wypożyczających i zostawiać recenzje. Jeśli będzie to wypożyczenie publiczne to będzie można również wystawić
  opinie właścicielowi gry, dzięki temu użytkownicy będą wiedziec czy dany właściciel jest godny zaufania i czy warto brać udział w jego wypożyczeniach.
  Czyli wchodzimy sobie na kogoś szafe i tam można wypożyczyć (użytkownik sam ustawia czy można daną gre wypożyczyć, bazowo będzie że nie).


- **Wishlisty** — użytkownicy będą mogli tworzyć listy gier, które chcieliby mieć lub zagrać.
  Będzie można przeglądać wishlisty innych użytkowników (za pozwoleniem danej osoby) i dodawać gry do swojej wishlisty.
  Będzie można ustawić powiadomienia o dostępności gier z wishlisty w okolicy lub w sklepach partnerskich.


- **Polubienia / ulubione** — lajkowanie gier (osobne od wishlisty: lubię ≠ chcę mieć).
  Będzie można przeglądać ulubione gry innych użytkowników (za pozwoleniem danej osoby) i dodawać gry do swoich ulubionych.
  Będzie można filtrować ulubione gry według typu, gatunku i opinii innych użytkowników.


- **Marketplace P2P** — sprzedaż, odkupywanie i wymiana używanych gier między userami.
  Osobne od afiliacji (sklep) i od wypożyczania. Wymaga płatności i reputacji.


- **Dopasowanie graczy po guście** — matching ludzi do ludzi po preferencjach gatunków/
  mechanik (nie tylko "kto ma grę X"). Napędza "tinder gier".


- **Grupy / społeczności tematyczne** — fora/kanały wokół systemów i gier (Warhammer,
  LotR, ciężkie euro itd.), nie tylko czat 1:1.


- **Linki na stronie gry** — do BGG, sklepów, YouTube, materiałów.


- **Własne API** — dla innych serwisów, np. sklepów, które chcą pokazać półkę użytkownika
  lub jego wishlistę. Wersja płatna (abonament) dla partnerów biznesowych.


- **Pobranie swoich gier z BGG** — w formacie CSV lub JSON, do własnej analizy i backupu.
  Jest API które na to pozwala, więc nie trzeba robić scrappingu. Wersja płatna (abonament) dla partnerów biznesowych.


- **Ranking gier** — zaciągnięte przez APi z BGG, ale można też robić własne rankingi (np. w danym mieście, wśród znajomych).


- **Asysten AI (klasyk)** — odpowiada na pytania o zasady, podpowiada strategie, podaje przykładowe scenariusze.
  Wersja płatna (abonament), lub kilka darmowych zapytań.


---

## Strategia wzrostu / marketing (NIE feature, ale nie zapomnieć)
- Instagram i social media jako kanał budowania społeczności od dnia zero.
- Międzynarodowość: i18n od początku, App Store globalnie — nie tylko PL. Ale
  START od jednego miasta (gęstość społeczności > zasięg).
- Zaangażowanie współtwórców: ktoś do bazy okładek/modeli, ktoś do treści.
  Potencjalne partnerstwa: youtuberzy (tutoriale), sklepy, wydawcy.
