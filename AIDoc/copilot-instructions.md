# Globalne Zasady Pracy — GitHub Copilot Agent

> Wersja: 1.0 | Data: 2026-04-11  
> Dotyczy: całości workspace `C:\Program Files\Python310` (projekt Forex AI Bot)

---

## 1. Zasady ogólne

1. **Błędy pierwsze** — Przed każdym nowym zadaniem najpierw napraw wszystkie aktywne błędy (ERROR/CRITICAL w logach, wyjątki SQL, błędy DB schema itp.). Nowe funkcje realizuj dopiero gdy środowisko jest czyste.
2. **Analiza przed działaniem** — Przed każdym wdrożeniem najpierw przeanalizuj problem i wypracuj trzy warianty rozwiązania oznaczone jako `A`, `B`, `C` z krótkim opisem zalet i wad każdego. Następnie zapytaj użytkownika, który wariant wdrażamy.
3. **Nie nadmiaruj** — Nie dodawaj funkcji, refaktoryzacji ani "ulepszeń" poza zakresem zadania.
3. **Używaj `py`** zamiast `python` w komendach terminalowych (Windows py launcher).
4. **Po każdej zmianie** zaktualizuj dokumentację techniczną w folderze `AIDoc/`.
5. **Bezpieczeństwo** — Każdy kod musi być wolny od podatności z OWASP Top 10.

---

## 2. Architektura Multi-Agent — Hierarchia Ról

Każde zadanie przechodzi przez trójwarstwową hierarchię. Orchestrator (główna sesja premium) jest odpowiedzialny za analizę, podział i koordynację — **nigdy sam nie wykonuje całości pracy implementacyjnej**, deleguje ją do odpowiednich agentów.

```
┌─────────────────────────────────────────────────────┐
│              ORCHESTRATOR (Warstwa 0)               │
│         Model: Claude Sonnet — premium              │
│  • Analizuje zadanie i ocenia złożoność             │
│  • Generuje warianty A / B / C                      │
│  • Decyduje o podziale na podzadania                │
│  • Koordynuje Agentów i Subagentów                  │
│  • Weryfikuje i integruje wyniki                    │
└────────────────┬────────────────────────────────────┘
                 │ deleguje
        ┌────────┴─────────┐
        ▼                  ▼
┌───────────────┐  ┌────────────────────────────────┐
│ SPECIALIST    │  │      WORKER SUBAGENT           │
│ AGENT         │  │   (Warstwa 2 — non-premium)    │
│ (Warstwa 1)   │  │   Model: GPT-4o / Explore      │
│ Sonnet subag. │  │                                │
│               │  │ • Eksploracja kodu             │
│ • Złożone     │  │ • Proste zmiany 1-plikowe      │
│   zmiany      │  │ • Generowanie dokumentacji     │
│   multi-plik  │  │ • Generowanie unit testów      │
│ • Architektura│  │ • Wyszukiwanie i analiza       │
│ • Security    │  │   plików / wzorców             │
│   audit       │  │ • Formatowanie i lint          │
│ • DB schema   │  └────────────────────────────────┘
│   i migracje  │
└───────────────┘
```

---

## 3. Routing zadań — Macierz Złożoności

Orchestrator klasyfikuje każde zadanie według poniższej macierzy i dobiera odpowiedni typ agenta:

| Złożoność | Kryteria | Typ Agenta | Model |
|---|---|---|---|
| **Prosta** | 1 plik, jasne wymaganie, < 50 linii zmian | Worker Subagent | GPT-4o / Explore |
| **Średnia** | 2–5 plików, logika biznesowa, testy | Specialist Agent | Claude Sonnet subagent |
| **Wysoka** | Architektura, multi-moduł, DB schema, security | Orchestrator + Specialist Agents | Sonnet (premium) |
| **Krytyczna** | Produkcja, deployment, nieodwracalne operacje | Orchestrator z zatwierdzeniem użytkownika | Sonnet (premium) |

---

## 4. Protokół Pracy Orchestratora

### Krok 1 — Analiza zadania
```
1. Odczytaj kontekst z /memories/repo/ i AIDoc/
2. Oceń złożoność (macierz powyżej)
3. Zidentyfikuj pliki których dotyczy zadanie
4. Zdefiniuj podzadania do delegacji
```

### Krok 2 — Warianty rozwiązania
```
Zawsze przedstaw:
  A: [opis wariantu] — zalety / wady
  B: [opis wariantu] — zalety / wady
  C: [opis wariantu] — zalety / wady

Zalecany wariant: [A/B/C] — uzasadnienie
→ Poczekaj na decyzję użytkownika
```

### Krok 3 — Podział i delegacja
```
Dla wybranego wariantu:
  - Identyfikuj niezależne podzadania → Worker Subagents (równolegle)
  - Identyfikuj zależne podzadania   → Specialist Agents (sekwencyjnie)
  - Zachowaj dla siebie             → integracja i weryfikacja
```

### Krok 4 — Weryfikacja i integracja
```
1. Zweryfikuj wyniki każdego agenta
2. Sprawdź spójność między plikami
3. Uruchom testy jeśli dostępne
4. Zaktualizuj dokumentację w AIDoc/
5. Zaktualizuj /memories/repo/ o nowe fakty
```

---

## 5. Zasady delegacji do Subagentów

### Worker Subagent (Explore agent — non-premium)
Używaj dla zadań **tylko do odczytu** lub **prostych wdrożeń**:
- Eksploracja struktury kodu (`Explore` agent z poziomem: quick/medium/thorough)
- Czytanie wielu plików równolegle
- Generowanie dokumentacji na podstawie kodu
- Generowanie unit testów dla istniejących funkcji
- Wyszukiwanie wzorców, importów, użyć symboli

**Prompt dla Explore subagenta powinien zawierać:**
- Co szukamy / co analizujemy
- Poziom szczegółowości: quick / medium / thorough
- Dokładnie co ma zwrócić w odpowiedzi

### Specialist Agent (Claude Sonnet subagent — premium)
Używaj dla zadań wymagających **rozumowania i złożonych zmian**:
- Refaktoryzacja wieloplikowa
- Implementacja nowych modułów/klas
- Analiza bezpieczeństwa
- Zmiany w schemacie DB
- Optymalizacja algorytmów

---

## 6. Praca z tym Projektem (Forex AI Bot)

### Środowisko
- **Python**: `C:\Program Files\Python310` — używaj `py`
- **Venv**: `C:\Program Files\Python310\forex_env`
- **Bot**: `forex_env\forex_ai_bot_v1.3.py`
- **DB**: MS SQL Server — baza `ForexBotDB`, Windows Auth

### Dokumentacja — aktualizuj po każdej zmianie
- `AIDoc\forex_ai_bot_v1_3_dokumentacja_techniczna.md` — zmiany techniczne
- `AIDoc\forex_ai_bot_v1_4_dokumentacja_teoretyczna.md` — zmiany algorytmiczne/strategiczne

### Pliki krytyczne (zawsze weryfikuj przed zmianą)
- `forex_env\forex_v14\db_writer.py` — warstwa DB + sync + DBLogHandler
- `forex_env\forex_v14\wisdom_aggregator.py` — obserwator rynku
- `forex_env\forex_ai_bot_v1.3.py` — główny bot

### Operacje wymagające zatwierdzenia użytkownika
- Zmiany w schemacie tabel SQL
- Modyfikacje `start.bat` i innych skryptów startowych
- Wszelkie `git push`, deployment na produkcję
- Usuwanie plików lub danych z bazy

---

## 7. Standardy Kodu

- **Python 3.10** — bez f-string walrus operator i funkcji 3.11+
- **Logowanie**: używaj `DBLogHandler` z `db_writer.py` — nie `print()`
- **Wyjątki**: zawsze loguj z kontekstem, nie przechwytuj cicho
- **Testy**: folder `forex_env\tests\` — pytest
- **Brak hardkodowanych credentials** — tylko Windows Auth lub zmienne środowiskowe

---

## 8. Zarządzanie Pamięcią (Memory)

| Plik | Zakres | Zawartość |
|---|---|---|
| `/memories/preferences.md` | User (globalny) | Preferencje użytkownika |
| `/memories/repo/forex-bot-infra.md` | Repo | Infrastruktura, DB, pliki klucz. |
| `/memories/session/` | Sesja | Plan zadania, stan w toku |

**Po zakończeniu każdego złożonego zadania:**
1. Zaktualizuj `/memories/repo/` o nowe fakty architektoniczne
2. Wyczyść session memory z tymczasowych notatek

---

## 9. Format Raportowania do Użytkownika

Po zakończeniu zadania zawsze podaj:
```
✅ Zrealizowane: [co zostało zrobione]
📁 Zmienione pliki: [lista z linkami]
🧪 Testy: [wynik / nie dotyczy]
📚 Dokumentacja: [zaktualizowana / nie dotyczy]
⚠️  Wymaga uwagi: [opcjonalne ostrzeżenia]
```

---

*Plik zarządzany przez GitHub Copilot. Aktualizuj przy zmianach zasad pracy.*
