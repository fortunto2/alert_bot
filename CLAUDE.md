# CLAUDE.md

Guidelines for Claude Code when working with this crypto crash monitoring system.

---

## Project Overview

**Crypto Crash Monitor** - Real-time alert system using trained strategy from ShinkaEvolve. Monitors multiple cryptos using **OKX perpetual futures** (CCXT) and sends Telegram alerts based on crash probability.

**Tech Stack:**
- Data: OKX perpetual futures via CCXT (NOT SPOT, NOT Yahoo Finance)
- Strategy: Trained model from initial.py (can be any generation/version)
- Alerts: multi_crash_monitor.py → Telegram
- Testing: backtest.py → VectorBT Portfolio
- Cache: Smart 1h expiry for performance

**⚠️ IMPORTANT:** For strategy details, performance metrics, and feature importance → see [README.md](README.md)

---

## System Architecture

```
Data Layer              Strategy Engine          Application Layer
─────────────          ────────────────         ──────────────────
data_loader_futures    initial.py               multi_crash_monitor.py
(OKX + CCXT)          (Trained strategy)        (Telegram alerts)
     │                       │                           │
     │                       │                   backtest.py
     │                       │                   (VectorBT testing)
     └───────────────────────┴──────────────────────────┘
         Shared data pipeline via fetch_crypto_futures_data()
```

### Core Files

| File | Role | Usage |
|------|------|-------|
| **data_loader_futures.py** | Fetch OKX futures + funding rates | All components |
| **initial.py** | Strategy engine (indicators + signals) | Source of truth |
| **multi_crash_monitor.py** | Alert system (production) | Cron job |
| **backtest.py** | Testing tool | Validation |

---

## Essential Commands

### Development
```bash
# Setup
uv sync
cp .env.example .env && nano .env

# Test monitoring
uv run python multi_crash_monitor.py

# Test backtesting
uv run python backtest.py BTC --days 7
uv run python backtest.py BTC ETH SOL --days 30 --fresh

# Run tests
uv run python test_backtest.py
uv run python test_multi_monitor.py
```

### Deployment
```bash
# Setup hourly cron
./setup_cron.sh

# Check logs
tail -f /tmp/multi_crypto_monitor.log
```

---

## Data Flow (High-Level)

### 1. Data Collection (data_loader_futures.py)

**Function:** `fetch_crypto_futures_data(symbol, timeframe, period, exchange="okx")`

**Process:**
1. Check cache age (< 1h → use cache, ≥ 1h → fetch fresh)
2. Fetch via CCXT: OHLCV + funding rates from OKX
3. Merge on timestamp, save as Parquet
4. Return DataFrame with `[datetime, open, high, low, close, volume, funding_rate]`

**Why OKX Perpetual Futures:**
- Funding rates = market sentiment (critical for crash detection)
- 24/7 liquid markets
- OKX used (Binance blocked in some regions)

### 2. Strategy Computation (initial.py)

**Two components - can be ANY trained strategy:**

#### A. Strategy Class (e.g., FuturesTradingStrategy)
- Computes indicators (RSI, MACD, BB, ATR, OBV, ADX, funding metrics, etc.)
- Calculates crash_probability (composite of multiple factors)
- Detects market regime (BULL/BEAR/CRASH/VOLATILE)

#### B. run_experiment(df) Function
- Creates strategy instance
- Generates entry/exit signals (logic depends on trained model)
- Calculates dynamic position_size and stop_loss_pct
- Runs VectorBT Portfolio backtest
- **Returns DataFrame with ALL features + signals**

**⚠️ This is SOURCE OF TRUTH - backtest.py MUST use these signals!**

### 3. Application Layer

#### Monitor (multi_crash_monitor.py)
```python
# For each crypto:
1. Fetch data (smart cache)
2. Create Strategy(df)
3. Extract crash_probability + metrics
4. If ≥ threshold → send Telegram alert

# No VectorBT Portfolio - just metrics extraction
```

#### Backtest (backtest.py)
```python
# For each crypto:
1. Fetch data
2. result_df = run_experiment(df)  # Get REAL trained signals
3. Extract: entry_signal, exit_signal, stop_loss_pct, position_size
4. Run vbt.Portfolio.from_signals() with extracted signals
5. Report metrics vs buy-and-hold
```

---

## Technical Details

### 1. data_loader_futures.py

**Main API:**
```python
fetch_crypto_futures_data(
    symbol="BTC/USDT:USDT",    # Perpetual futures format
    timeframe="1h",
    period="1mo",
    include_funding=True,
    exchange="okx",            # Always use OKX
    force_refresh=False
)
```

**Caching:**
- File: `datasets/okx_{symbol}_{timeframe}_{start_date}_{limit}.parquet`
- Smart cache in multi_crash_monitor: checks file mtime, refreshes if > 1h old
- Development: use `force_refresh=False` to avoid rate limits

**Funding Rates:**
- Updated every 8h (OKX)
- Positive: longs pay shorts (bullish sentiment)
- Negative: shorts pay longs (bearish panic)

### 2. initial.py

**⚠️ Strategy-specific - see README.md for current model details**

**Generic structure:**
```python
class SomeStrategy:
    def __init__(self, df):
        self._compute_indicators()
        self._compute_crash_probability()
        self._detect_market_regime()

    # Methods for indicators, signals, etc.

def run_experiment(df):
    """
    SOURCE OF TRUTH for trained signals.
    Always use this for backtest.py!

    Returns: DataFrame with entry_signal, exit_signal,
             stop_loss_pct, position_size + all features
    """
    strategy = SomeStrategy(df)
    # Generate signals
    # Run VectorBT backtest
    return result_df
```

### 3. multi_crash_monitor.py

**Key function:**
```python
check_crash_probability_for_symbol(symbol, lookback_hours, thresholds, exchange):
    """
    Returns dict with 16 metrics:
    - symbol, timestamp, price, change_24h
    - crash_probability, pre_crash_warning, early_warning, crisis_alert
    - rsi, atr_ratio, volatility, trend_strength, momentum_strength
    - market_strength, funding_stress, vol_ratio_4h
    """
```

**Why no Portfolio here:**
- Monitoring system, not trading system
- Only extracts crash_probability for alerts
- Portfolio simulation only in backtest.py

### 4. backtest.py

**Critical:** MUST use signals from `run_experiment(df)`, NOT create new ones!

```python
def run_backtest(symbol, df):
    # Get REAL trained signals
    result_df = run_experiment(df)

    # Extract (don't recreate!)
    entries = result_df['entry_signal']
    exits = result_df['exit_signal']
    stop_percents = result_df['stop_loss_pct']
    position_sizes = result_df['position_size']

    # Simulate with extracted signals
    pf = vbt.Portfolio.from_signals(...)
```

**CLI:**
```bash
python backtest.py BTC                    # 90 days default
python backtest.py BTC ETH SOL --days 7   # Multi-crypto
python backtest.py BTC --fresh            # Bypass cache
```

---

## Configuration (.env)

**Required:**
```bash
TELEGRAM_BOT_TOKEN=your_token
TELEGRAM_CHAT_ID=your_chat_id
```

**Alert thresholds (adjust per strategy):**
```bash
CRASH_ALERT_PRE_CRASH=0.2       # Yellow warning
CRASH_ALERT_EARLY_WARNING=0.4   # Orange alert
CRASH_ALERT_CRISIS=0.6          # Red crisis
CRASH_ALERT_THRESHOLD=0.4       # Send when ≥ this
```

**Backtest thresholds (match trained strategy):**
```bash
BACKTEST_ENTRY_TREND=0.5        # Entry conditions
BACKTEST_ENTRY_CRASH=0.35
BACKTEST_EXIT_CRASH=0.40        # Exit conditions
BACKTEST_EXIT_TREND=0.30
BACKTEST_INIT_CASH=10000
BACKTEST_FEES=0.001
```

---

## Testing

### Unit Tests

**test_backtest.py** - Validates backtest architecture:
```bash
uv run python test_backtest.py
```
Checks:
1. run_experiment() returns required columns
2. Backtest uses REAL signals (not new ones)
3. Adaptive thresholds work

**test_multi_monitor.py** - Validates monitor:
```bash
uv run python test_multi_monitor.py
```
Checks:
1. Correct metrics extraction
2. All required fields present
3. Multiple symbols processed correctly

---

## Common Pitfalls

### ❌ DON'T: Create new signals in backtest
```python
# WRONG - creates new signals
entries = df['trend'] > 0.5
exits = df['crash'] > 0.4
```

### ✅ DO: Use trained signals
```python
# CORRECT - uses trained signals
result_df = run_experiment(df)
entries = result_df['entry_signal']
exits = result_df['exit_signal']
```

### ❌ DON'T: Run Portfolio in monitor
```python
# WRONG - monitor is not a trader
pf = vbt.Portfolio.from_signals(...)  # NO!
```

### ✅ DO: Extract metrics only
```python
# CORRECT - monitor extracts crash_probability
strategy = FuturesTradingStrategy(df)
crash_prob = strategy.crash_probability.iloc[-1]
```

### ❌ DON'T: Use SPOT or Yahoo Finance
```python
# WRONG - removed from codebase
df = fetch_crypto_data('BTC-USD')  # Function doesn't exist!
```

### ✅ DO: Use OKX perpetual futures
```python
# CORRECT
df = fetch_crypto_futures_data('BTC/USDT:USDT', exchange='okx')
```

### ❌ DON'T: Hardcode strategy details in CLAUDE.md
```python
# WRONG - strategy changes, CLAUDE.md becomes outdated
```

### ✅ DO: Reference README.md for strategy details
```markdown
For current strategy details → see README.md
```

---

## Development Workflow

### Adding New Features

1. **Modify data_loader_futures.py** - if data source changes
2. **Modify initial.py** - if strategy/indicators change
3. **Update README.md** - document new strategy details
4. **Run tests** - verify backtest still uses trained signals
5. **Update .env.example** - if new thresholds needed

### Changing Strategy

1. **Train new model** in ShinkaEvolve
2. **Update initial.py** with new strategy class
3. **Update README.md** with new performance metrics
4. **Adjust .env thresholds** if needed
5. **Run tests** - verify integration works

### CLAUDE.md stays generic - no need to update!

---

## Quick Reference

**Get Telegram credentials:**
```
1. @BotFather → /newbot
2. Get token
3. Send message to bot
4. Visit: https://api.telegram.org/bot<TOKEN>/getUpdates
5. Copy chat_id
```

**File structure:**
```
alert_bot/
├── data_loader_futures.py    # OKX data via CCXT
├── initial.py                # Trained strategy (SOURCE OF TRUTH)
├── multi_crash_monitor.py    # Telegram alerts (production)
├── backtest.py               # VectorBT testing
├── test_*.py                 # Unit tests
├── .env                      # Configuration
├── CLAUDE.md                 # This file (generic instructions)
├── README.md                 # Strategy details (model-specific)
└── datasets/                 # Cached Parquet files
```

**Dependencies:**
```toml
ccxt>=4.5.14          # OKX perpetual futures
pandas>=2.3.3         # Data manipulation
vectorbt>=0.28.1      # Backtesting
python-dotenv>=1.2.1  # Config
# NO yfinance - removed!
```

---

## For Strategy Details

**Current model, performance, feature importance, training results:**
→ See [README.md](README.md)

**This keeps CLAUDE.md generic and README.md always up-to-date with latest strategy.**
