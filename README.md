# Common Ground

Common Ground to prosta aplikacja do znajdowania miejsca spotkania dla kilku osób w Warszawie. Pomysł jest taki, żeby nie wybierać miejsca tylko na podstawie odległości, ale uwzględnić rzeczywisty czas dojazdu każdej osoby.

## Pomysł

Chciałem zrobić coś prostego, ale trochę innego niż kolejny planer podróży. Zależało mi na tym, żeby aplikacja miała jedną konkretną funkcję, robiła ją dobrze i nie wymagała rozbudowanej architektury.

Tak powstał Common Ground - aplikacja, która szuka kompromisu między szybkością a sprawiedliwością podróży. Możemy wybrać miejsce, do którego wszyscy dotrą średnio najszybciej, albo takie, w którym nikt nie będzie musiał jechać przesadnie długo.

Dodałem też wizualizację 3D, która przedstawia wyniki jako „dolinę dostępności”. To trochę eksperymentalny sposób pokazania tego samego problemu.

## Co robi aplikacja?

- Pozwala tworzyć, edytować i usuwać spotkania oraz dodawać do nich uczestników.
- Można zarządzać uczestnikami ręcznie albo zwykłymi poleceniami tekstowymi, np. „Dodaj Olę i Pawła, Ola jedzie rowerem”.
- Każdemu uczestnikowi ustawiamy punkt startowy, środek transportu (pieszo, rower lub samochód) i opcjonalnie maksymalny czas podróży.
- Aplikacja korzysta z Geoapify, żeby znaleźć prawdziwe kawiarnie i obliczyć czasy dojazdu. Bez klucza API może korzystać z danych OpenStreetMap i publicznego OSRM.
- Python porównuje miejsca i wybiera trzy najlepsze propozycje.
- Suwakiem możemy zmienić priorytet między średnim czasem podróży a czasem osoby, która ma najdalej. Ranking przelicza się bez ponownego pobierania tras.
- Wyniki widać na interaktywnej mapie 3D, również w eksperymentalnym trybie VALLEY.
- Spotkania i ich dane zapisują się w SQLite.

## Technologie i architektura

**Backend:** Python, FastAPI, Pydantic, PydanticAI, SQLAlchemy, SQLite, pytest.

**Frontend:** React, TypeScript, Vite, MapLibre GL, Paper Shaders, Playwright.

**Usługi:** Geoapify, OpenStreetMap, OSRM, OpenRouter.

Wybrałem Pythona, FastAPI, Pydantic, SQLAlchemy i SQLite, ponieważ to stack, który dobrze znam, którego uczyłem się i z którego korzystam chociażby w pracy. Dzięki temu mogłem szybko napisać prosty, czytelny backend, bez zbędnego komplikowania projektu.

Zastosowałem też strukturę, którą przyjąłem wcześniej podczas nauki FastAPI: osobno router, serwisy z logiką, repozytorium do komunikacji z bazą, modele i schematy walidacji.

Cały backend aplikacji korzysta z jednego routera z siedmioma endpointami, nie licząc testowego `/api/health`. To wystarcza do obsługi CRUD, interpretowania poleceń i obliczania rekomendacji. Kod jest bardzo minimalistyczny.

AI służy tutaj głównie do rozumienia poleceń użytkownika. Zwraca uporządkowane akcje, które Python sprawdza i wykonuje. Sam ranking i obliczenia nie zależą od odpowiedzi modelu językowego.

Dlaczego taki stack na frontendzie? Ponieważ mam doświadczenie z Reactem, zapewnia szybką i prostą implementację efektownego UI z pomocą AI, jest prosty i łatwno na nim zbudować nowoczesne UI - tu użyłem paper shaders i WebGL, które bardzo lubię ponieważ są ciekawe i w moim odczuciu będą kierunkiem rozwoju UI desing.

I najważniejszy powód wybrania takiego stacku: ustandaryzowanie zaplecza technologicznego do sprawdzonych i powszechnie wykorzystywanych wzorców projektowych i bibliotek.

## Struktura - najważniejsze elementy

`backend/app` - struktura aplikacji FastAPI:
- `models/` - modele danych
- `repositories/` - zapytania do bazy danych
- `schemas/` - DTO
- `routers/` - punkty dostępu API
- `services/` - logika
- `tests/` - testy pytest
- `config.py` - wczytaie ustawień
- `database.py` - połączenie z bazą danych
- `.env` - lokalne zmienne środowiskowe
- `.envexample` - przykład zapisu zmiennych

`frontend/src` - frontend aplikacji React:
- `App.tsx` - główny komponent aplikacji i zarządzanie jej stanem
- `api/` - typy danych oraz komunikacja z backendem
- `components/` - komponenty interfejsu, np. lista uczestników i rekomendacji
- `map/` - interaktywna mapa, markery i warstwa wizualizacji wyników
- `ui/` - elementy wizualne, w tym shadery i wspólne komponenty UI
- `styles/` - style aplikacji
- `main.tsx` - punkt wejścia frontendu
- `e2e/` - testy end-to-end uruchamiane za pomocą Playwright

## Uruchomienie

**Backend:**

```bash
cd backend 
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --reload --port 8000
```

**Frontend:**

```bash
cd frontend 
npm install 
npm run dev
```

Aplikacja: http://localhost:5173

Dokumentacja API: http://localhost:8000/docs

Aplikacja działa również bez kluczy API. Bez nich dostępny jest ograniczony parser poleceń i alternatywne źródło tras.

## Jak korzystałem z AI?

Ponieważ w zadaniu zaznaczono, żeby przygotować niewielkie MVP i nie spędzać nad nim wielu dni, starałem się maksymalnie skrócić czas realizacji. Cały projekt zajął mi 2 popołudnia.

Wykorzystałem narzędzia AI przede wszystkim do stworzenia większości frontendu, rozszerzania funkcjonalności oraz przygotowania testów. Pomagały mi też w szybszym wychwytywaniu błędów i sprawdzaniu różnych rozwiązań. AI rozbudowało też backend naprawiając integrację AI.

Sam skupiłem się na pomyśle, doborze technologii, architekturze, logice działania i weryfikacji rezultatów i działaniu backendu, który jest ustrukturyzowany w bardzo typowy dla mnie sposób. Zależało mi, żeby kod pozostał bardzo prosty i zrozumiały, jest to też element polecenia.

## Ograniczenia

To MVP, więc na razie aplikacja działa tylko dla Warszawy, uwzględnia trzy środki transportu i wyszukuje kawiarnie. Nie bierze pod uwagę korków, komunikacji miejskiej ani godzin otwarcia lokali.

Ranking powstaje na podstawie maksymalnie 32 wybranych kandydatów, a nie wszystkich kawiarni w mieście. Jest więc praktycznym przybliżeniem, a nie gwarancją globalnie najlepszego rozwiązania.

## Co umie MVP

1. Zarządzasz grupą zdaniami: „Dodaj Olę i Pawła”, „Będziemy we czwórkę”, „Ola jedzie rowerem”, „Zmień Oli transport na auto i limit na 25 minut”, „Usuń Adama i dodaj Kasię”, „Zmień imię Oli na Aleksandra”, „Nie usuwaj Oli” (nic się nie dzieje), „Ola startuje z Mokotowa”.
2. Agent AI zamienia tekst na listę typowanych akcji, a Python wykonuje je atomowo - wszystko albo nic. Przy niejednoznaczności (np. „Będziemy we dwoje”, gdy są 3 osoby z danymi) aplikacja pyta i niczego nie usuwa.
3. Miejsce podane słowami trafia do geokodera jako propozycja startu (przerywany znacznik), którą zatwierdzasz jednym kliknięciem. Start możesz też kliknąć albo przeciągnąć na mapie.
4. „Znajdź miejsce” - bezpłatna preselekcja wybiera 32 kandydatów z puli ~300 kawiarni, Geoapify liczy dla nich realne czasy dojazdu (osobno pieszo / rower / auto), a Python liczy ranking.
5. Dostajesz 3 rekomendacje oddalone od siebie (prawdziwe alternatywy), czas każdej osoby i tryb CITY / VALLEY.
6. Suwak szybkość/sprawiedliwość (α) przelicza ranking natychmiast, bez ponownego routingu.

`score(p) = (1 − α) · średni_czas(p) + α · najdłuższy_czas(p)`
