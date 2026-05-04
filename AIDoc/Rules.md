# Zasady Pracy — Forex AI Bot

> Pełna instrukcja globalna: `.github/copilot-instructions.md`

## Skrót kluczowych zasad

1. **Błędy pierwsze** — przed nowym zadaniem napraw wszystkie aktywne błędy (ERROR w logach, wyjątki SQL, błędy DB). Nowe funkcje dopiero gdy środowisko jest czyste.
2. **Analiza przed działaniem** — zawsze 3 warianty (A, B, C), czekaj na wybór użytkownika.
2. **Architektura agentów** — patrz `.github/copilot-instructions.md` sekcja 2–5:
   - **Orchestrator** (Claude Sonnet premium) — analiza, koordynacja, integracja
   - **Specialist Agent** (Claude Sonnet subagent) — złożone zmiany multi-plikowe
   - **Worker Subagent** (GPT-4o / Explore) — eksploracja, dokumentacja, proste zadania
3. **Routing** — złożoność zadania decyduje o typie agenta (macierz w sekcji 3).
4. **Po każdej zmianie** — aktualizuj `AIDoc/` (dokumentacja tech + teoria).
5. **Terminal** — używaj `py` zamiast `python` (Windows py launcher).
6. **Operacje nieodwracalne** (SQL schema, git push, usuwanie) — zawsze pytaj użytkownika.
