# 🔧 FIX dla Transakcji 2997158 - Wdrożenie

## Problem
Transakcja GBPCHF #2997158 straciła **-1301 pips** zamiast spodziewanych **-350 pips** (3.7x więcej!)
- Stop Loss nie był respektowany
- Pozycja była zamykana na losowej cenie rynkowej zamiast SL
- Win rate GBPCHF: 25% (tylko 1 wygrana na 4 transakcje)

## Przyczyna
1. **TIME_EXIT_HOURS** zamykał pozycje po określonym czasie na **bieżącej cenie market**, ignorując SL
2. **GBPCHF** ma złe parametry dla obecnego systemu
3. **LOT size** (0.8) był zbyt duży dla tej zmiennej pary

## ✅ Wdrożone Fixes

### 1. ⛔ Wyłączenie GBPCHF
- Dodany do blacklist w konfiguracji bazy danych
- Bot nie będzie otwierać nowych pozycji na tej parze

### 2. 🎯 Zmiana logiki TIME_EXIT
- Zamiast zamykać na market price (`_close_position`)
- Teraz zamyka limit order blisko SL (`_close_position_at_sl`)
- Unika drastycznych strat z powodu gap pricing

### 3. 📉 Zmniejszenie LOT size
- Zmiana: 0.8 → 0.3 (zmniejszenie o 62.5%)
- Ogranicza ekspozycję na ryzyko dla zmiennych par

### 4. 📊 Zwiększenie confidence thresholds dla JPY par
- GBPJPY, EURJPY, USDJPY: conf_threshold = 0.85
- Blokuje słabe sygnały na parach z niskim win rate

### 5. 🛡️ Wzmocniony NPM (Negative Position Manager)
- NPM_ALERT_R zmieniony na -0.5 (wcześniejsza interwencja)
- MAX_DAILY_LOSSES zmieniony na 2 (zamiast więcej)
- Bardziej agresywne zamykanie strat

## 📋 Instrukcje Wdrożenia

### Krok 1: Zastosuj SQL do bazy danych
```sql
-- Uruchom na serwerze appdbpri, baza ForexBotDB
-- Plik: c:\Program Files\Python310\forex_env\forex_data\fix_large_losses.sql
```

### Krok 2: Restart bota
```powershell
# W terminalu PowerShell
cd "c:\Program Files\Python310\forex_env"
python forex_ai_bot_v1.3.py
```

Bot automatycznie załaduje nową konfigurację z bazy danych.

### Krok 3: Monitorowanie
- Obserwuj logi pod kątem:
  - `TIME_EXIT` - czy zamyka na SL
  - `GBPCHF` - czy jest pomijany
  - `Close at SL` - czy nowa funkcja pracuje

## 📈 Oczekiwane Rezultaty

| Metrika | Przed | Po |
|---------|-------|-----|
| Max loss na TIME_EXIT | -1301 pips | ~-350 pips |
| GBPCHF w handlu | TAK | NIE (blacklist) |
| Lot size | 0.8 | 0.3 |
| JPY pairs confidence | 0.75 | 0.85 |
| Daily loss limit | ??? | 2 |

## 🔍 Testy

Aby zweryfikować zmiany:
```bash
# 1. Sprawdź czy GBPCHF jest w blacklist
SELECT value FROM bot_config WHERE key_name = 'blacklist_symbols';

# 2. Sprawdź lot size
SELECT value FROM bot_config WHERE key_name = 'lot';

# 3. Sprawdź nowe thresholds
SELECT key_name, value FROM bot_config 
WHERE key_name LIKE '%conf_threshold%' OR key_name LIKE '%atr%';
```

## ⚠️ Ograniczenia

1. **Fallback do market close** - jeśli limit order zawiedzie, fall back do market price
2. **5 pips offset** - nowa funkcja zamyka 5 pips od SL (dopasuj w kodzie jeśli potrzeba)
3. **Wymaga restart bota** - zmiany konfiguracji wymagają restarta programu

## 🔮 Przyszłe Ulepszenia

1. Per-symbol lot multiplier (zmniejszyć JPY pary jeszcze bardziej)
2. Adaptive confidence thresholds na bazie win rate
3. Graceful degradation dla problematycznych par (recovery window)
4. Swap cost analyzer - unikać par z dużym swapem

## 📝 Kod - Główne Zmiany

### a) Nowa funkcja `_close_position_at_sl()`
```python
def _close_position_at_sl(pos):
    """Zamknij pozycję limit order blisko SL zamiast na market price."""
    # - Oblicza limit price 5 pips poniżej SL
    # - Wysyła limit order zamiast market order
    # - Fallback do market close jeśli limit order zawiedzie
```

### b) Modyfikacja TIME_EXIT
- Linia 858: `_close_position(pos)` → `_close_position_at_sl(pos)`
- Linia 920: `_close_position(pos)` → `_close_position_at_sl(pos)`

### c) BLACKLIST_SYMBOLS
- Linia 26: nowy parametr konfiguracji
- Linia 103-112: logika filtrowania w reload_cfg

## 💬 Pytania/Feedback

Jeśli widzisz problemy:
1. Sprawdź logi: `c:\Program Files\Python310\forex_env\forex_logs\`
2. Sprawdź trade_outcomes w bazie: `SELECT * FROM trade_outcomes WHERE symbol='GBPCHF'`
3. Zweryfikuj że _close_position_at_sl jest wywoływana: szukaj "Close at SL" w logach
