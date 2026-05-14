# Dokumentacja teoretyczna — forex_ai_bot v1.4
# Filozofia: "W cierpliwości siła"

---

## 0. Aktualne założenia v1.3 (produkcja) — zmiany 2026-05-04

> Ta sekcja opisuje **biznesowe założenia zmian** wdrożonych do działającego bota v1.3.0.5.
> Sekcje 1–14 dotyczą wizji docelowej v1.4 (w projektowaniu).

### 0.1 HTF Scoring — dlaczego punkty zamiast binarnego bloku?

**Problem przed zmianą**: Bot blokował transakcje gdy W1 i D1 były niezgodne — ale nie rozróżniał "lekko niezgodne" od "silnie niezgodne". Np. W1=UP (silny), D1=FLAT (neutralny) → blokada, mimo że W1 dawał mocny sygnał. To powodowało zbyt dużo blokad.

**Nowe podejście — system punktów pewności kierunku:**

| Timeframe | Zgodny z ML | Przeciwny do ML |
|-----------|-------------|-----------------|
| W1 (tygodniowy) | +2 pkt | −2 pkt |
| D1 (dzienny) | +1 pkt | −1 pkt |
| H4 (4-godzinny) | +1 pkt | −1 pkt |

**Zasada biznesowa:**
- Score 0–1 → **BLOKADA** — zbyt słaba zgodność HTF, ryzyko wejścia pod prąd
- Score 2 → **SŁABE WEJŚCIE** — wchodzimy tylko z minimalnym lotem i wyższym progiem ufności (+5%). Bot "wchodzi ostrożnie" gdy sygnał jest umiarkowany.
- Score 3–4 → **PEŁNE WEJŚCIE** — wszystkie timeframy zgodne, normalny lot i próg

**Efekt**: Mniej blokad przy silnych sygnałach W1. Ostrożne wejścia przy sygnałach mieszanych. Całkowita blokada tylko gdy brak zgodności.

### 0.2 Adaptive conf/lot per symbol — nauka z własnej historii

**Problem przed zmianą**: Bot traktował wszystkie pary walutowe jednakowo. XAGUSD (srebro) i EURUSD miały ten sam próg ufności, mimo że historycznie srebro dawało dużo gorzsze wyniki.

**Nowe podejście — automatyczna adaptacja na podstawie win-rate:**

Bot co godzinę sprawdza historię transakcji z bazy danych. Dla symboli z ≥ 10 zamkniętych transakcji:

| Win-rate | Reakcja bota |
|----------|-------------|
| ≥ 35% | Bez zmian — normalny próg i lot |
| < 35% | Próg ufności +10%, lot ×0.5 — wchodzi rzadziej i mniejszym wolumenem |

**Zasada biznesowa**: Bot uczy się na własnych błędach. Symbol który historycznie przegrywa → dostaje "karę" w postaci wyższej poprzeczki wejścia. Gdy jego wyniki się poprawią (win-rate wzrośnie), kara znika automatycznie przy kolejnym odświeżeniu.

**Wartości domyślne** (konfigurowalne w `bot_config` DB):
- `adaptive_min_trades = 10` — minimalna liczba transakcji do oceny
- `adaptive_winrate_thresh = 0.35` — próg 35% win-rate
- `adaptive_conf_boost = 0.10` — podniesienie progu ufności dla słabych symboli
- `adaptive_lot_factor = 0.50` — redukcja lota dla słabych symboli

### 0.3 Śledzenie wersji bota w transakcjach

Każda nowa transakcja zapisuje pole `bot_version` (np. `"1.3.0.5"`) w tabeli `trades`. Pozwala to analizować czy zmiany w poszczególnych wersjach bota poprawiają win-rate.

Komentarz wysyłany do MT5 zmieniony z `"AI Forex Bot 1.3"` na `"AI FBoot 1.3.0.5"` — widoczny w historii transakcji u brokera.

### 0.4 Jakość operacyjna — ograniczenie szumu w logach

Przed wdrożeniem bot generował setki identycznych komunikatów dziennie:
- Weekend: `"Poza godzinami handlu"` co 5 minut = **~576 linii/weekend**
- Dzienny limit strat: WARNING co 5 minut przez resztę dnia

Po wdrożeniu:
- Komunikat off-hours: **max 1 raz na godzinę** (throttle `_off_hours_last_log`)
- W weekend sleep wydłużony do **30 minut** (rynek zamknięty)
- Komunikaty o limitach strat: **raz na dobę** (flagi `_daily_limit_warned`, `_usd_limit_warned`)
- Restart 23:59 działa teraz również w **weekend** (wcześniej był omijany)

### 0.5 Spójność danych transakcyjnych (manualne vs botowe) — zmiana 2026-05-14

**Problem wykryty na produkcji**: część transakcji ręcznych była widoczna w `trade_outcomes`, ale brakowało ich (lub były niepoprawnie mapowane) w `trades`.

**Przyczyna techniczna**:
- MT5 używa dwóch różnych identyfikatorów: `order` (warstwa zlecenia) i `position_id` (warstwa pozycji).
- Historycznie bot opierał mapowanie głównie o jedno pole (`order_id`), co powodowało rozjazdy dla części ręcznych flow.

**Nowe podejście (Variant B)**:
- W `trades` są dwa jawne klucze: `mt5_order_id` i `mt5_position_id`.
- Kluczem życia pozycji jest `mt5_position_id`.
- `mt5_order_id` pozostaje do pełnej audytowalności i debugowania ścieżki egzekucji.
- Jeśli bot dostanie zamknięcie pozycji bez wcześniejszego rekordu otwarcia (np. manualny trade), dopisuje rekord `SYNCED` do `trades` aby zachować pełną historię.

**Efekt biznesowy**:
- raporty strat i win-rate nie pomijają już części transakcji ręcznych,
- analiza jakości strategii i risk management jest bardziej wiarygodna,
- łatwiejszy audyt zgodności `trades` ↔ `trade_outcomes`.

---

## 1. Wizja i filozofia wersji 1.4

### 1.1 Zmiana paradygmatu
Wersja 1.3 dziala wedlug zasady: "skanuj czesto, wchodzi gdy model powie TAK".
Wersja 1.4 odwraca podejscie: **bot NIE handluje, chyba ze ma pewniaka**.

| Cecha | v1.3 | v1.4 |
|---|---|---|
| Liczba transakcji dziennie | 5–20+ | 0–3 |
| Wolumen bazowy | LOT_MIN (0.01–0.1) | 5.0 lot |
| Prog wejscia | predict_proba > threshold | wielowarstwowy filtr pewnosci >= 0.92 |
| Tryb pracy | reaktywny (sygnal -> zlecenie) | obserwacyjny 24/7, snajperski strzal |
| Uczenie sie | retraining modelu co cykl | ciagla agregacja obserwacji + okresowy retraining |

### 1.2 Zasada naczelna
> Lepiej 3 transakcje tygodniowo po 5 lotow z 85%+ trafnoscia niz 50 transakcji po 0.1 lota z 55% trafnoscia.

### 1.3 Dwa tryby pracy bota
1. **OBSERVER** — tryb domyslny, 24/7. Bot obserwuje rynek, gromadzi dane, agreguje spostrzezenia. Nie sklada zlecen.
2. **SNIPER** — tryb aktywowany automatycznie gdy wszystkie warstwy filtracji potwierdzaja pewniaka. Bot sklada zlecenie o wysokim wolumenie.

---

## 2. Architektura wysokopoziomowa v1.4

```
┌─────────────────────────────────────────────────────────────┐
│                    PETLA GLOWNA 24/7                        │
│                                                             │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐   │
│  │  DATA LAYER  │───>│  ANALYSIS    │───>│  DECISION    │   │
│  │  (MT5 feed)  │    │  ENGINE      │    │  GATE        │   │
│  └──────────────┘    └──────────────┘    └──────┬───────┘   │
│                                                 │           │
│                              ┌──────────────────┼────────┐  │
│                              │                  │        │  │
│                         ┌────▼─────┐     ┌──────▼─────┐  │  │
│                         │ OBSERVER │     │  SNIPER    │  │  │
│                         │ (loguj)  │     │  (handluj) │  │  │
│                         └────┬─────┘     └──────┬─────┘  │  │
│                              │                  │        │  │
│                    ┌─────────▼──────────────┐    │        │  │
│                    │  WISDOM AGGREGATOR     │    │        │  │
│                    │  (baza spostrzezen)    │    │        │  │
│                    └────────────────────────┘    │        │  │
│                                                 │        │  │
│                                          ┌──────▼─────┐  │  │
│                                          │ POSITION   │  │  │
│                                          │ MANAGER    │  │  │
│                                          └────────────┘  │  │
│                              ┌────────────────────────┐  │  │
│                              │  PERIODIC RETRAINER    │  │  │
│                              └────────────────────────┘  │  │
└─────────────────────────────────────────────────────────────┘
```

---

## 3. Warstwy analizy technicznej — filtracja pewniakow

Transakcja moze zostac otwarta TYLKO jesli wszystkie 5 warstw zwroca sygnal zgodny.

### 3.1 Warstwa 1: Analiza swiece (Candle Analysis)

Analiza ostatnich N swiec na wielu timeframe'ach (M15, H1, H4, D1).

#### Metryki swiecowe:
- **Rozmiar body vs shadow**: stosunek ciala swiece do cieni — duze cialo + male cienie = silny impet
- **Konsekutywne swiece kierunkowe**: >= 3 swiece zamkniecia w jednym kierunku
- **Volume profile**: swiece o wolumenie > 1.5x sredniej potwierdzaja ruch
- **Rejected wicks**: dluge cienie od strony oporu/wsparcia = odrzucenie poziomu
- **Body momentum**: porownanie rozmiaru 3 ostatnich cial — rosnacy = narastajacy impet

#### Timeframe confluence (konfluencja czasowa):
- Sygnal musi byc zgodny na >= 3 z 4 timeframe'ow
- Waga: D1 (40%), H4 (30%), H1 (20%), M15 (10%)

### 3.2 Warstwa 2: Analiza formacji (Formation Analysis)

#### Formacje odwrocenia (reversal) — wysokie prawdopodobienstwo:
- **Evening Star / Morning Star** — potwierdzony wolumenem
- **Engulfing** — cialo pochlaniajacej swiece >= 1.5x poprzedniej
- **Three White Soldiers / Three Black Crows** — z rosnacym cialem
- **Hammer / Hanging Man** — cien >= 2x ciala, na kluczowym poziomie
- **Doji + potwierdzenie** — doji sam w sobie to nie sygnal; doji + nastepna swieca kierunkowa = sygnal

#### Formacje kontynuacji (continuation) — potwierdzenie trendu:
- **Rising/Falling Three Methods**
- **Bullish/Bearish Flag** (wykrywanie geometryczne)
- **Cup and Handle** (rozpoznawanie wzorca na >= 20 swiecach)

#### Formacje chartowe (pattern recognition):
- **Double Top / Double Bottom** — z pomiarem odleglosci miedzy szczytami
- **Head and Shoulders** — z linia szyi i pomiarem glowy
- **Triangle** (ascending, descending, symmetrical) — breakout z wolumenem

#### Scoring formacji:
Kazda formacja otrzymuje score 0.0–1.0 na podstawie:
- jakosci (proporcje cial, cieni, wolumen)
- kontekstu (poziom wsparcia/oporu, trend nadrzedny)
- historycznej skutecznosci dla danej pary (z bazy spostrzezen)

### 3.3 Warstwa 3: Kontekst makro-techniczny

- **Trend nadrzedny**: EMA(50) vs EMA(200) na D1 — handluj TYLKO z trendem
- **ADX**: >= 25 na H4 — potwierdzenie silnego trendu
- **RSI divergence**: rozbieznosc ceny i RSI jako wczesny sygnal odwrocenia
- **Bollinger Band squeeze**: zwezenie wsteg = zbliajacy sie silny ruch (nie kierunek, ale sila)
- **MACD histogram**: zmiana znaku histogramu na H4 = potwierdzenie momentum
- **Kluczowe poziomy S/R**: automatyczna detekcja wsparc i oporow z ostatnich 100 swiec D1

### 3.4 Warstwa 4: Predykcja ML (model)

Model ML dziala jak poprzednio, ale:
- **Wymagany prog pewnosci**: >= 0.85 (zamiast dotychczasowego predict_proba_threshold)
- **Ensemble**: zamiast jednego modelu, 3 modele glosuja (Random Forest, XGBoost, LightGBM)
  - Transakcja tylko gdy >= 2 z 3 modeli zgodne z confidence >= 0.85
- **Feature importance tracking**: modele raportuja ktore cechy byly decydujace — logowane do bazy spostrzezen

### 3.5 Warstwa 5: Bramka koncowa (Decision Gate)

Wszystkie warstwy daja wynik 0.0–1.0. Bramka oblicza **Composite Confidence Score (CCS)**:

$$CCS = w_1 \cdot S_{candle} + w_2 \cdot S_{formation} + w_3 \cdot S_{macro} + w_4 \cdot S_{ml}$$

Domyslne wagi:
- $w_1 = 0.20$ (swiece)
- $w_2 = 0.25$ (formacje)
- $w_3 = 0.25$ (kontekst makro)
- $w_4 = 0.30$ (ML ensemble)

**Prog wejscia**: $CCS \geq 0.92$

Dodatkowo wymagane:
- ATR > atr_min * 2 (wystarczajaca zmiennosc dla duzego lota)
- Spread < 20% planowanego TP (koszt wejscia nie zjada zysku)
- Brak waznych news w oknie +/- 30min (opcjonalnie: integracja z kalendarzem ekonomicznym)

---

## 4. System obserwacji i agregacji spostrzezen (Wisdom Aggregator)

### 4.1 Cel
Bot w trybie OBSERVER zbiera dane 24/7 i buduje baze wiedzy per para walutowa. Ta baza:
- uczy model jakie warunki poprzedzaly zyskowne transakcje,
- identyfikuje wzorce specyficzne dla kazdej pary,
- pozwala na adaptacyjne dostosowanie wag i progow.

### 4.2 Struktura bazy spostrzezen

Baza przechowywana w MS SQL Server (ForexBotDB) na localhost.
Warstwa dostepu: forex_v14/db_writer.py (MSSQLWriter, pyodbc, Windows Auth).
Mechanizm synchronizacji MT5 -> DB zapewnia spojnosc danych nawet przy utracie polaczenia.

#### Tabela: `observations` (rekord co cykl analizy)
| Kolumna | Typ | Opis |
|---|---|---|
| timestamp | datetime | Czas obserwacji |
| symbol | str | Para walutowa |
| timeframe | str | Timeframe analizy |
| candle_score | float | Wynik analizy swiec (0–1) |
| formation_type | str | Wykryta formacja (lub "none") |
| formation_score | float | Jakosc formacji (0–1) |
| macro_score | float | Wynik kontekstu makro (0–1) |
| ml_prediction | int | Predykcja modelu (0=BUY, 1=SELL) |
| ml_confidence | float | Pewnosc modelu |
| ccs | float | Composite Confidence Score |
| atr | float | ATR w momencie obserwacji |
| spread | float | Spread w momencie obserwacji |
| ema_trend | str | "UP" / "DOWN" / "FLAT" |
| rsi | float | RSI(14) |
| adx | float | ADX(14) |
| volume_ratio | float | Wolumen vs srednia |
| action_taken | str | "NONE" / "BUY" / "SELL" |
| outcome_1h | float | Zmiana ceny po 1h (pips) |
| outcome_4h | float | Zmiana ceny po 4h (pips) |
| outcome_24h | float | Zmiana ceny po 24h (pips) |
| outcome_max_favorable | float | Max korzystna zmiana w 24h |
| outcome_max_adverse | float | Max niekorzystna zmiana w 24h |

#### Tabela: `trade_outcomes` (rekord per transakcja)
| Kolumna | Typ | Opis |
|---|---|---|
| trade_id | int | ID transakcji |
| symbol | str | Para walutowa |
| direction | str | BUY / SELL |
| entry_ccs | float | CCS w momencie wejscia |
| entry_candle_score | float | Score swiec przy wejsciu |
| entry_formation | str | Formacja przy wejsciu |
| entry_macro_score | float | Score makro przy wejsciu |
| profit_pips | float | Wynik w pipsach |
| profit_money | float | Wynik w walucie konta |
| duration_hours | float | Czas trwania pozycji |
| max_drawdown | float | Max obsunecie w trakcie |
| sl_hit | bool | Czy SL zostal trafiony |
| tp_hit | bool | Czy TP zostal trafiony |

#### Tabela: `formation_effectiveness` (agregowana statystyka)
| Kolumna | Typ | Opis |
|---|---|---|
| symbol | str | Para walutowa |
| formation_type | str | Typ formacji |
| occurrences | int | Liczba wystapien |
| win_rate | float | % zyskownych po 24h |
| avg_move_pips | float | Sredni ruch po 24h |
| best_timeframe | str | Najskuteczniejszy TF |
| last_updated | datetime | Data aktualizacji |

### 4.3 Cykl zycia obserwacji
1. Co cykl analizy (np. co 15 min) bot zapisuje observation dla kazdego symbolu.
2. Po 1h, 4h i 24h od obserwacji — uzupelnia pola outcome_*.
3. Jesli observation doprowadzila do transakcji — laczy z trade_outcomes.
4. Co 24h agreguje formation_effectiveness.
5. Synchronizacja MT5 -> DB przy starcie i co cykl petli uzupelnia brakujace rekordy.

### 4.4 Wykorzystanie bazy spostrzezen
- **Adaptacyjne wagi CCS**: co tydzien przeliczane na podstawie korelacji score -> outcome
- **Filtracja formacji**: formacje z win_rate < 55% dla danej pary sa ignorowane
- **Anomaly detection**: obserwacje odstajace od normy flagowane do recznej analizy
- **Feature engineering**: nowe cechy do modelu ML generowane z agregowanych spostrzezen

---

## 5. Zarzadzanie pozycja w trybie "cierpliwosci"

### 5.1 Sizing pozycji (equity-based)

Wielkosc pozycji obliczana dynamicznie na podstawie stanu konta i odleglosci SL:

```
risk_money   = equity × 1%               (ryzyko na transakcje)
sl_ticks     = odleglosc_SL / tick_size   (ile tickow do SL)
loss_per_lot = sl_ticks × tick_value      (strata per 1 lot przy SL)
base_lot     = risk_money / loss_per_lot  (bazowy wolumen)
```

**Skalowanie wg confidence modelu ML:**
- confidence 0.6 (prog) → 50% base_lot
- confidence 0.8 → 75% base_lot
- confidence 1.0 → 100% base_lot

**Zabezpieczenia:**
- Max 70% wolnego marginu na pozycje (poduszka bezpieczenstwa)
- Clamp do limitow brokera: volume_min ≤ lot ≤ volume_max
- Zaokraglenie do volume_step

**Przyklad** (konto 100k PLN, EURUSD, SL=65 pips, confidence=0.7):
- risk_money = 1000 PLN, loss_per_lot = 650, base_lot = 1.54
- confidence scale = 0.625 → **final = 0.96 lota**

**Przyklad** (konto 100k PLN, EURUSD, SL=30 pips, confidence=0.9):
- risk_money = 1000 PLN, loss_per_lot = 300, base_lot = 3.33
- confidence scale = 0.875 → **final = 2.91 lota**

### 5.2 SL/TP strategia
- **SL**: ATR(14) * 1.3 — od ceny wejscia (sl_atr_multiplier)
- **TP**: fibonacci extension 1.618 z zakresu ostatniego swingu
  - alternatywnie: nastepny kluczowy poziom S/R
- **R:R minimum**: 1:2.5 — jesli nie mozna uzyskac, transakcja odrzucona

### 5.2.1 4-stopniowy mechanizm ochrony zysku (R-multiple trailing SL)

Mechanizm opiera sie na **R-multiple** — mierze zysku wyrazonej w jednostkach poczatkowego ryzyka:

```
1R = |cena_wejscia - poczatkowy_SL|   (poczatkowe ryzyko w pipsach)
R  = (cena_aktualna - cena_wejscia) / 1R   (dla BUY)
R  = (cena_wejscia - cena_aktualna) / 1R   (dla SELL)
```

**Sledzenie ekstremalnej ceny**: bot pamięta najkorzystniejsza cene osiagnieta przez kazda pozycje:
- BUY: `max(wszystkie_ceny)` — najwyzszy punkt
- SELL: `min(wszystkie_ceny)` — najnizszy punkt
- Zapisywane w pliku `extreme_price_dict.pkl` (trwalosc miedzy restartami)

| Etap | Warunek | Nowy SL (BUY) | Nowy SL (SELL) | Efekt |
|------|---------|---------------|----------------|-------|
| **Stage 0** | R < 0.7 | oryginalny SL | oryginalny SL | Normalny risk |
| **Stage 1 — Break-Even** | R >= 0.7 | entry + spread buffer | entry - spread buffer | **Zero risk** |
| **Stage 2 — Lock Profit** | R >= 1.5 | entry + 0.5R | entry - 0.5R | **Gwarantowany zysk** |
| **Stage 3 — Trailing** | R >= 2.0 | extreme - 1.0 ATR | extreme + 1.0 ATR | **Podaza za cena** |
| **Stage 4 — Tight Trail** | R >= 3.0 | extreme - 0.5 ATR | extreme + 0.5 ATR | **Maksymalizacja zysku** |

**Zasady:**
- SL **nigdy sie nie cofa** — moze sie przesunac tylko w korzystnym kierunku
- Kazda pozycja jest chroniona **inkubatorem** (20h) — przez ten czas SL nie jest modyfikowany
- Pozycje **stale ujemne** (R < 0) analizowane sa heurystycznie (trend + RSI + formacje + ML) — zamykane gdy analiza wskazuje brak szans na odbicie

**Przyklad praktyczny** (EURUSD BUY, entry=1.0800, SL=1.0750, 1R=50 pips):

| Cena | R | Stage | Nowy SL | Zabezpieczony zysk |
|------|---|-------|---------|-------------------|
| 1.0820 | 0.4 | 0 | 1.0750 | -50 pips (risk) |
| 1.0850 | 1.0 | 1 | ~1.0801 | ~0 pips (break-even) |
| 1.0875 | 1.5 | 2 | 1.0825 | +25 pips |
| 1.0900 | 2.0 | 3 | ~1.0820 | +20 pips (trailing) |
| 1.0950 | 3.0 | 4 | ~1.0910 | +110 pips (tight) |

**Konfiguracja** (globalcfg.py):
- `trail_breakeven_r` = 0.7 — prog Stage 1 (Variant C: obnizony z 1.0)
- `trail_lock_r` = 1.5, `trail_lock_fraction` = 0.5 — prog i frakcja Stage 2
- `trail_atr_r` = 2.0, `trail_atr_factor` = 1.0 — prog i ATR factor Stage 3
- `trail_tight_r` = 3.0, `trail_tight_factor` = 0.5 — prog i ATR factor Stage 4

**Wczesniejszy mechanizm (usuniety)**: regula 30% max_profit (zamykaj gdy profit spadnie do 30% max profitu). Zastapiony deterministycznym 4-etapowym trailingiem opartym na R-multiple i sledzeniu ekstremalnej ceny zamiast monetarnego max_profit.

### 5.2.2 Variant C — kompleksowy pakiet ochrony (po analizie 9/9 strat)

Po analizie raportu handlowego (9 transakcji, 9 strat, zadna nie osiagnela R>=1.0) wdrozono pakiet "Variant C":

#### Filtry wejscia (blokuja otwieranie nowych pozycji)
| Filtr | Parametr | Wartosc | Opis |
|-------|----------|---------|------|
| **Prog ML** | `predict_proba_threshold` | 0.75 | Podniesiony z 0.6 — wymagana wieksza pewnosc modelu |
| **Minimalny R:R** | `min_rr_ratio` | 2.0 | TP/SL musi byc >= 2.0, inaczej blokada |
| **Filtr HTF** | W1+D1 mandatory | — | W1 i D1 musza byc zgodne z ML (usuniety tryb "wejscie z ostrzezeniem") |
| **Filtr spreadu** | `spread_filter_pct` | 0.20 | Spread > 20% dystansu SL → blokada |
| **Okno plynnosci** | `volatility_block_start/end` | 0-4 UTC | Brak nowych zlecen 00:00-04:00 UTC (niska plynnosc) |
| **Cooldown symbolu** | `symbol_cooldown_hours` | 24h | Po stracie na symbolu — 24h przerwy na ten symbol |
| **Limit dzienny** | `max_daily_losses` | 3 | Po 3 stratach — stop nowych zlecen na caly dzien |

#### Ochrona pozycji (wzmocniona)
| Mechanizm | Parametr | Wartosc | Opis |
|-----------|----------|---------|------|
| **Wczesniejszy break-even** | `trail_breakeven_r` | 0.7 | SL na break-even juz przy R=0.7 (wczesniej 1.0) |
| **Czesciowe zamkniecie** | `partial_close_r/pct` | R>=1.5, 50% | Zamknij 50% pozycji przy R>=1.5, reszta jedzie dalej |
| **Time exit** | `time_exit_hours` | 16h | Ujemna pozycja (R<0) trwajaca 16h+ → zamkniecie |

#### Uzasadnienie zmian
- 7 z 9 strat otwarto miedzy 01:11-02:21 UTC → okno plynnosci bezposrednio rozwiazuje problem
- Zadna transakcja nie osiagnela R>=1.0 → problem jest na wejsciu, nie na ochronie
- Podniesienie progu ML 0.6→0.75 eliminuje najslabsze sygnaly
- Obowiazkowy HTF filter uniemozliwia handel pod prad W1/D1
- Czesciowe zamkniecie przy R>=1.5 realizuje zysk czescio jednoczesnie pozwalajac reszcie biec

### 5.2.3 NPM — Negative Position Manager (zarzadzanie pozycjami ujemnymi)

System inteligentnego zarzadzania pozycjami generujacymi strate. Zastapil proste `should_close_negative_position()`.

#### NPM Score (0-100)
Kompozytowy wynik obliczany co cykl (5 min) dla kazdej ujemnej pozycji:

| Skladnik | Waga | Mierzy |
|----------|------|--------|
| Momentum H1 | 20% | EMA(9) vs EMA(21) — czy impet wraca na korzysc? |
| RSI extremum | 15% | RSI w strefie oversold/overbought — szansa na odwrocenie |
| ATR contraction | 15% | ATR(5)/ATR(14) — czy ruch przeciwny zwalnia? |
| Bliskosc S/R | 20% | Odleglosc od fibo 38.2% / 61.8% — wsparcie/opor |
| Czas w stracie | 15% | Kara rosnaca z czasem (0h=15pkt, 48h+=0pkt) |
| Koszt swapu | 15% | Swap wzgledem straty — czy oplacalny carry? |

#### Eskalacja 3-poziomowa
| Poziom | Warunek | Akcja |
|--------|---------|-------|
| 🟢 WATCH | R > -0.5 AND NPM > 50 | Tylko logowanie i monitorowanie |
| 🟡 ALERT | R <= -0.5 LUB NPM < 50 | Sciagniecie SL do -1.5R od entry |
| 🔴 CRITICAL | R <= -1.0 LUB NPM < 30 | Skalowane zamkniecie (50% → 100%) |
| ⛔ HARD CAP | R <= -2.5 | Bezwzgledne zamkniecie 100% |

#### Skalowany exit (CRITICAL)
- R <= -1.0 AND NPM < 30 → zamknij 50% wolumenu
- R <= -1.5 AND NPM < 20 → zamknij reszte (100%)
- Przy CRITICAL jesli ML potwierdza (should_close=True) → natychmiastowe zamkniecie

#### Weekend Recovery Window
**Kluczowa obserwacja**: po weekendowych przestojach rynek potrafi odwrócic trendy (gap poniedzialkowy).
Szczegolnie dotyczy metali (XAUUSD, XAGUSD) i crossow JPY.

- Piatek od 20:00 UTC do niedzieli 23:59: akcje ALERT/CRITICAL **wstrzymane**
- Hard cap (R <= -2.5) nadal aktywny w weekend window
- Logika: daj szanse na poniedzialkowy gap zamiast zamykac ze strata w piatek wieczorem

#### Tabela SQL `negative_position_log`
Pelna historia decyzji NPM zapisywana co cykl — umozliwia:
- Analiza retrospektywna: ktore decyzje byly trafne?
- Uczenie recovery probability z danych historycznych
- Dashboard: filtr CRITICAL z ostatnich 24h

#### Recovery Probability
Obliczana z tabeli `trade_outcomes` dla tego samego symbolu:
- Ile transakcji z podobna glebokoscia straty (R) ostatecznie zakonczylo sie zyskiem?
- Wynik logowany do NPM table — dane do dalszej analizy

### 5.3 Maksymalna ekspozycja
- Max 2 otwarte pozycje jednoczesnie (niezaleznie od symbolu)
- Max 1 pozycja per symbol
- Dzienny limit strat: -3% equity -> stop handlu do nastepnego dnia
- Tygodniowy limit strat: -5% equity -> stop handlu do poniedzialku

### 5.4 Inkubator pozycji
- Minimalne trzymanie: 4h (nie zamykaj zbyt wczesnie)
- Po 4h: ocena trendu — jesli trend zgodny z pozycja, trzymaj
- Zamkniecie agresywne: tylko gdy CCS odwroci sie < 0.3 (silny kontrsygnal)

---

## 6. Cykl pracy bota — przeplyw 24/7

```
START (Windows Server 2025, autostart jako usluga)
  │
  ▼
INICJALIZACJA
  ├── Polaczenie z MT5
  ├── Zaladowanie modeli (cache w RAM)
  ├── Otwarcie bazy spostrzezen
  └── Odczyt stanu (extreme_price_dict, open positions)
  │
  ▼
PETLA GLOWNA (while True)
  │
  ├── [co 1 min] HEARTBEAT
  │     └── Sprawdz polaczenie MT5, equity, otwarte pozycje
  │
  ├── [co 15 min] OBSERVER CYCLE
  │     ├── Dla kazdego symbolu:
  │     │     ├── Pobierz dane M15, H1, H4, D1
  │     │     ├── Oblicz candle_score
  │     │     ├── Wykryj formacje -> formation_score
  │     │     ├── Oblicz macro_score
  │     │     ├── ML ensemble prediction
  │     │     ├── Oblicz CCS
  │     │     ├── Zapisz observation do bazy
  │     │     │
  │     │     └── CCS >= 0.92?
  │     │           ├── TAK -> SNIPER MODE
  │     │           │     ├── Sprawdz margin, spread, limity
  │     │           │     ├── Oblicz lot, SL, TP
  │     │           │     ├── Zloz zlecenie
  │     │           │     └── Loguj trade
  │     │           └── NIE -> kontynuuj obserwacje
  │     │
  │     └── Aktualizuj outcome_* dla starszych obserwacji
  │
  ├── [co 1 min] POSITION MANAGER (4-stopniowy trailing SL + Variant C)
  │     ├── Sprawdz otwarte pozycje
  │     ├── Oblicz R-multiple per pozycja
  │     ├── Aktualizuj extreme_price_dict (najkorzystniejsza cena)
  │     ├── NPM: Negative Position Manager (dla R<0 i profit<0)
  │     │     ├── Oblicz NPM score (momentum, RSI, ATR, S/R, czas, swap)
  │     │     ├── Wyznacz eskalacje (WATCH / ALERT / CRITICAL)
  │     │     ├── Sprawdz weekend recovery window
  │     │     ├── HARD CAP (R<=-2.5) → zamknij 100%
  │     │     ├── CRITICAL → skalowany exit (50% / 100%) lub ML close
  │     │     ├── ALERT → sciagnij SL do -1.5R
  │     │     ├── WATCH → tylko logowanie
  │     │     └── Zapisz do negative_position_log (SQL)
  │     ├── Czesciowe zamkniecie: R>=1.5 → zamknij 50% wolumenu (raz per ticket)
  │     ├── Stage 0 (R<0.7): nie ruszaj SL
  │     ├── Stage 1 (R>=0.7): SL → break-even
  │     ├── Stage 2 (R>=1.5): SL → entry + 0.5R
  │     ├── Stage 3 (R>=2): SL = extreme - 1.0 ATR
  │     ├── Stage 4 (R>=3): SL = extreme - 0.5 ATR
  │     └── Sprawdz limity strat
  │
  ├── [co 24h o 02:00] WISDOM CYCLE
  │     ├── Agreguj formation_effectiveness
  │     ├── Przelicz adaptacyjne wagi CCS
  │     ├── Wygeneruj raport dzienny (plik/email)
  │     └── Opcjonalnie: retraining modeli
  │
  └── [23:55] DAILY SHUTDOWN (opcjonalny)
        ├── Zamknij pozycje (jesli skonfigurowane)
        └── Zapisz stan do plikow trwalych
```

---

## 7. Logowanie i diagnostyka

### 7.1 Poziomy logow
- **TRADE**: kazde zlecenie — pelne szczegoly CCS, score'y, formacje
- **OBSERVATION**: co cykl obserwacji — skrot analizy per symbol
- **WISDOM**: co dobowy cykl agregacji — statystyki formacji, win rate
- **SYSTEM**: heartbeat, polaczenie MT5, bledy, zuzucie pamieci

### 7.2 Pliki logow i baza danych
- `forex_logs/forex_bot_{data}.log` — log aplikacji (plik)
- Tabela `bot_logs` (MS SQL) — WARNING/ERROR/CRITICAL automatycznie przez DBLogHandler
- Tabela `observations` (MS SQL) — pelna baza spostrzezen
- Tabela `trade_outcomes` (MS SQL) — historia transakcji z metrykami
- Tabela `trades` (MS SQL) — log transakcji + synchronizacja MT5
- Tabela `bot_status` (MS SQL) — heartbeat bota
- Tabela `formation_effectiveness` (MS SQL) — agregowana skutecznosc formacji
- `reports/daily_{data}.md` — raport dzienny (opcjonalnie)

### 7.3 Alerty
- Transakcja otwarta/zamknieta -> log TRADE + opcjonalnie webhook/email
- Dzienny limit strat osiagniety -> log SYSTEM + alert
- Polaczenie z MT5 utracone -> log SYSTEM + proba reconnect

---

## 8. Roznica miedzy v1.3 a v1.4 — podsumowanie zmian

### 8.1 Co zostaje z v1.3
- Integracja z MT5 (API, zlecenia, historia)
- Bazowa infrastruktura logowania
- Moduly forex_base (indicators, formation_detection, tran_logs, globalcfg)
- Mechanizm reconnect i obsluga bledow
- Trailing SL (4-stopniowy R-multiple) i ochrona zysku

### 8.2 Co sie zmienia
| Obszar | v1.3 | v1.4 |
|---|---|---|
| Decyzja o wejsciu | 1 model + threshold | 5-warstwowy filtr + CCS >= 0.92 |
| Analiza swiec | generate_features() | rozbudowana candle_score() multi-TF |
| Analiza formacji | detect_candle_formations() | rozszerzona + scoring + skutecznosc historyczna |
| Model ML | 1 model per symbol | ensemble 3 modeli per symbol |
| Lot sizing | dynamiczny od LOT_MIN | stale 5.0 lot (z walidacja margin) |
| Obserwacja rynku | brak | ciagla 24/7 z baza spostrzezen |
| Retraining | co cykl petli | co 24h z nowych spostrzezen |
| Liczba transakcji | wiele drobnych | 0–3 dziennie, pewniaki |
| Zarzadzanie ryzykiem | 4-stopniowy trailing SL (R-multiple) + HTF filter | ATR + R:R minimum 1:2.5 + limity strat |
| Raportowanie | CSV log | MS SQL (6 tabel) + log plikowy |

### 8.3 Nowe moduly do stworzenia
1. **candle_analyzer.py** — wielotimeframe'owa analiza swiec z scoringiem
2. **formation_scorer.py** — scoring i filtracja formacji wg historycznej skutecznosci
3. **macro_context.py** — analiza trendu nadrzednego, S/R, divergence
4. **decision_gate.py** — obliczanie CCS, bramka wejscia
5. **wisdom_aggregator.py** — zapis/odczyt obserwacji, agregacja, adaptacja wag
6. **ensemble_predictor.py** — wrapper na 3 modele ML z glosowaniem
7. **position_manager_v2.py** — zaawansowane zarzadzanie pozycja z limitami
8. **daily_reporter.py** — generowanie raportow dziennych

### 8.4 Zmiany w konfiguracji (nowe parametry globalcfg)
```
# v1.4 nowe parametry
sniper_lot              = 5.0              # Bazowy wolumen snajperski
ccs_threshold           = 0.92             # Prog Composite Confidence Score
ml_ensemble_threshold   = 0.85             # Prog pewnosci modelu (per model)
max_open_positions      = 2                # Max jednoczesnych pozycji
max_per_symbol          = 1                # Max pozycji per symbol
daily_loss_limit_pct    = 3.0              # Dzienny limit strat (% equity)
weekly_loss_limit_pct   = 5.0              # Tygodniowy limit strat (% equity)
min_rr_ratio            = 2.5              # Minimalny Risk:Reward
sl_atr_multiplier_v2    = 2.0              # Szerszy SL dla pewniakow
observer_interval_sec   = 900              # Co ile sekund cykl obserwacji (15 min)
heartbeat_interval_sec  = 60               # Co ile sekund heartbeat
wisdom_cycle_hour       = 2                # O ktorej godzinie wisdom cycle
retraining_interval_h   = 24               # Co ile godzin retraining
observations_db_path    = "data/obs.db"    # Sciezka do bazy spostrzezen
candle_analysis_tfs     = [M15,H1,H4,D1]  # Timeframe'y do analizy swiec
formation_min_winrate   = 0.55             # Min win rate formacji
spread_max_pct_of_tp    = 0.20             # Max spread jako % TP
```

---

## 9. Koncepcja "roztropnego uczenia sie"

### 9.1 Etapy nauki
1. **Obserwacja bierna** (tydzien 1–2): Bot tylko zbiera dane, nie handluje. Buduje baze spostrzezen.
2. **Kalibracja** (tydzien 3): Na podstawie zebranych danych kalibrowane sa wagi CCS i progi.
3. **Paper trading** (tydzien 4): Bot "zawiera" transakcje wirtualnie — loguje co by zrobil, ale nie wysyla zlecen.
4. **Live trading** (od tygodnia 5): Bot handluje na zywo z pelna filtracja.

### 9.2 Petla zwrotna (feedback loop)
```
Obserwacja -> Spostrzezenie -> Agregacja -> Korekta wag -> Lepsza selekcja -> ...
     ▲                                                            │
     └────────────────────────────────────────────────────────────┘
```

Kazda transakcja (zyskowna i stratna) wzbogaca baze spostrzezen:
- Jakie formacje poprzedzaly zysk?
- Jaki CCS mial pewniaki vs pudla?
- Ktore pary sa bardziej przewidywalne w jakich warunkach?
- Ktore timeframe'y daja najlepsze sygnaly dla danej pary?

### 9.3 Adaptacja per para walutowa
Po 100+ obserwacjach per symbol bot buduje profil pary:
- **Preferowane formacje**: np. EURUSD reaguje na Evening Star lepiej niz GBPJPY
- **Optymalne okno czasowe**: np. USDJPY najlepsza trafnosc 08:00–12:00 UTC
- **Waga TF**: np. GBPUSD — H4 wazniejszy niz D1 dla krotszych swiagow
- **Sezonowość**: np. ladniejsze trendy w Q1 vs choppy w Q3

---

## 10. Wymagania infrastrukturalne

### 10.1 Srodowisko
- Windows Server 2025
- Python 3.10 (C:\Program Files\Python310, venv: forex_env)
- MetaTrader 5 zainstalowany i zalogowany (konto live/demo)
- MS SQL Server na localhost (baza ForexBotDB, Windows Auth)
- Pamiec: >= 4 GB RAM (modele ensemble + baza spostrzezen w cache)
- Dysk: >= 10 GB wolnego (baza spostrzezen rosnie ~50 MB/miesiac)
- Siec: stabilne polaczenie internetowe (latency < 100ms do brokera)

### 10.2 Uruchomienie produkcyjne
- Task Scheduler na koncie PRI\btrender (trigger: logowanie)
- Skrypt startowy: C:\Program Files\Python310\forex_env\start.bat
- start.bat: taskkill python.exe /F, potem uruchamia forex_ai_bot_v1.3.py
- Bot konczy dzialanie o 23:59
- Task Scheduler restartuje bota przy ponownym loginie (nastepny dzien)
- Konto PRI\btrender ma role db_owner na ForexBotDB

### 10.5 Git workflow — zasada

| Sytuacja | Akcja git |
|---|---|
| Zmiana wdrożona na produkcję (`deploy.ps1`) | commit dev + merge dev → **main** + push oba |
| Zmiana tylko lokalna / w trakcie prac | commit tylko **dev** |

Inaczej mówiąc: **`main` = stan produkcji**. Jeśli został deploy — `main` musi to odzwierciedlać.

### 10.4 Obowiązek aktualizacji dokumentacji

Po **każdej** zmianie w kodzie zaktualizuj:
- `AIDoc/forex_ai_bot_v1_3_dokumentacja_techniczna.md` — zmiany techniczne (kod, API, schemat DB, funkcje)
- `AIDoc/forex_ai_bot_v1_4_dokumentacja_teoretyczna.md` — zmiany biznesowe (założenia, strategie, zasady działania)

Obie dokumentacje są ładowane do kontekstu AI (Copilot) przy każdej sesji — nieaktualna dokumentacja prowadzi do błędnych decyzji agenta.
- Heartbeat co 60s logowany — brak heartbeatu = alarm
- Metryki: CPU, RAM, latency do MT5, liczba obserwacji/dzien
- Opcjonalnie: dashboard webowy (Flask/Streamlit) do podgladu stanu bota i spostrzezen

---

## 11. Harmonogram wdrozenia

| Etap | Opis | Czas szacowany |
|---|---|---|
| E1 | Refaktoring v1.3 — naprawienie bledow z dokumentacji technicznej | - |
| E2 | candle_analyzer.py + formation_scorer.py | - |
| E3 | macro_context.py + decision_gate.py | - |
| E4 | wisdom_aggregator.py (SQLite + agregacja) | - |
| E5 | ensemble_predictor.py (3 modele) | - |
| E6 | position_manager_v2.py + nowa konfiguracja | - |
| E7 | Integracja modulow w forex_ai_bot_v1.4.py | - |
| E8 | Obserwacja bierna (2 tygodnie zbierania danych) | - |
| E9 | Kalibracja i paper trading | - |
| E10 | Live trading z monitoringiem | - |

---

## 12. Metryki sukcesu v1.4

| Metryka | Cel |
|---|---|
| Win rate | >= 75% |
| Sredni R:R zrealizowany | >= 1:2.0 |
| Transakcje tygodniowo | 1–5 |
| Max drawdown miesieczny | < 5% equity |
| Profit factor | >= 2.5 |
| Sharpe ratio (miesieczny) | >= 1.5 |
| Czas obserwacji bez bledu | >= 168h (1 tydzien ciagly) |

---

## 13. Ryzyka i ograniczenia

| Ryzyko | Mitygacja |
|---|---|
| Zbyt restrykcyjny filtr = 0 transakcji | Adaptacyjne progi — obnizanie CCS o 0.01 co tydzien bez transakcji |
| Duzy lot + zly sygnal = duza strata | R:R min 1:2.5 + dzienny limit strat 3% + SL zawsze ustawiony |
| Awaria serwera = niezarzadzana pozycja | SL/TP ustawione w MT5 (brokerside) + heartbeat + auto-restart |
| Overfitting modelu do danych historycznych | Ensemble + walidacja out-of-sample + paper trading |
| Niska plynnosc = slippage na 5 lotach | Limity spread + filling IOC/FOK + wybor plynnych par |
| Baza spostrzezen rosnie bez konca | Archiwizacja > 6 miesiecy, retention policy |

---

## 14. Podsumowanie

Wersja 1.4 transformuje bota z reaktywnego egzekutora sygnalu w **cierpliwego obserwatora rynku**. Filozofia "w cierpliwosci sila" oznacza, ze:

1. Bot **obserwuje** 24/7, gromadzac wiedze o zachowaniu kazdej pary walutowej.
2. **Nie handluje** dopoki 5 warstw analizy nie potwierdzl pewniaka.
3. Gdy handluje — wchodzi **agresywnie** (5 lot) z szerokim SL i korzystnym R:R.
4. **Uczy sie** z kazdej obserwacji, trafionej i nietrafionej, adaptujac wagi i progi.
5. Z czasem staje sie coraz **roztropniejszy** — wie ktore formacje dzialaja na ktore pary, w jakich warunkach i kiedy.

Cel: mniej transakcji, wiecej zysku, rosnaca trafnosc.

---

## 15. Historia wdrożeń produkcyjnych

| Wersja | Data deploy | Opis zmian (biznesowy) |
|--------|------------|------------------------|
| 1.3.0.4 | 2026-05-01 | Deploy początkowy v1.3 na produkcję |
| 1.3.0.5 | 2026-05-04 | **HTF Scoring** (W1+D1+H4): zamiast binarnego bloku — system punktów pewności kierunku na wyższych TF. Score 0–1 blokuje, score 2 — wejście z minimalnym lotem + podniesiony próg ufności, score 3–4 — pełne wejście. **Adaptive conf/lot per symbol**: symbole z historycznym win-rate < 35% dostają automatycznie wyższy próg ufności (+0.10) i mniejszy lot (×0.5). **Jakość logów**: naprawiony spam komunikatów poza godzinami handlu (weekendy). **Śledzenie wersji**: pole `bot_version` w każdej transakcji w tabeli `trades`. |
