# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Crypto Crash Monitor - Real-time cryptocurrency crash probability detector with Telegram alerts using Gen11 strategy. This system monitors 11 cryptocurrencies (BTC, ETH, SOL, XRP, ADA, DOGE, AVAX, DOT, LINK, LTC, TRUMP) using **SPOT market data** from Yahoo Finance and sends consolidated Telegram notifications based on risk levels.

## Essential Commands

### Development Setup
```bash
# Install dependencies (uses uv package manager)
uv sync

# Set up environment variables
cp .env.example .env  # Then edit with your Telegram credentials
nano .env

# Test multi-crypto monitor (recommended)
uv run python multi_crash_monitor.py

# Test single BTC monitor (legacy)
uv run python crash_monitor.py

# Run data loader example
uv run python data_loader.py
```

### Cron Setup
```bash
# Automated setup (recommended)
chmod +x setup_cron.sh
./setup_cron.sh

# Manual crontab entry for multi-crypto monitor (recommended)
0 * * * * cd /home/rustam/alert_bot && /home/rustam/.local/bin/uv run python multi_crash_monitor.py >> /tmp/multi_crypto_monitor.log 2>&1

# Manual crontab entry for single BTC monitor (legacy)
0 * * * * cd /home/rustam/alert_bot && /home/rustam/.local/bin/uv run python crash_monitor.py >> /tmp/crash_monitor.log 2>&1
```

### Monitoring
```bash
# View multi-crypto monitor logs
tail -f /tmp/multi_crypto_monitor.log

# View single BTC monitor logs
tail -f /tmp/crash_monitor.log

# Check cron status
crontab -l
grep CRON /var/log/syslog
```

## Architecture

### Core Components

**multi_crash_monitor.py** - Multi-cryptocurrency monitoring script (RECOMMENDED)
- Monitors 11 cryptocurrencies: BTC, ETH, SOL, XRP, ADA, DOGE, AVAX, DOT, LINK, LTC, TRUMP
- Smart caching: only refreshes data if cache is older than 1 hour (3600 seconds)
- Parallel processing using ThreadPoolExecutor (max 5 workers)
- Consolidated Telegram alerts showing all cryptos above threshold
- Three alert levels: СРЕДНИЙ (≥20%), ВЫСОКИЙ (≥40%), КРИТИЧЕСКИЙ (≥60%)
- Uses same strategy and data loader as single monitor

**crash_monitor.py** - Single BTC monitoring script (LEGACY)
- Fetches BTC data via `data_loader.py`
- Uses `initial.py` strategy for crash detection
- Sends Telegram alerts using stdlib only (urllib, no external deps)
- Three alert levels: СРЕДНИЙ (≥20%), ВЫСОКИЙ (≥40%), КРИТИЧЕСКИЙ (≥60%)
- Configured via environment variables
- Always forces data refresh (force_refresh=True)

**data_loader_futures.py** - Futures data fetching via CCXT
- Downloads **perpetual futures** data from OKX exchange using CCXT
- Caches data locally in `datasets/` as parquet files
- Fetches OHLCV + funding rates (critical for futures trading)
- Provides `fetch_crypto_futures_data()`, `fetch_futures_ohlcv()`, `fetch_funding_rates()`
- **Note:** Uses OKX because Binance is blocked in restricted regions

**initial.py** - Gen11 trading strategy (VectorBT-based)
- `AdaptiveTradingSystem` class implements modular strategy
- Three signal generators: trend following, mean reversion, crash protection
- Market regime detection (trending/ranging/crisis)
- Crash probability calculation using weighted composite of 5 indicators:
  - Volatility spike (40% weight)
  - Price acceleration (20% weight)
  - Volume divergence (20% weight)
  - RSI extremes (15% weight)
  - Recent price drop (5% weight)
- Dynamic position sizing based on regime and crash probability
- Used by crash_monitor.py via dynamic import

### Data Flow

1. **crash_monitor.py:check_crash_probability()** calls `fetch_crypto_data()` to get latest BTC data
2. Creates `AdaptiveTradingSystem` instance from `initial.py`
3. Extracts latest crash_probability, warning flags, and technical indicators
4. If crash_probability ≥ threshold, formats alert message and sends via Telegram
5. Returns metrics dict with timestamp, price, RSI, ATR ratio, etc.

### Telegram Integration

- Uses pure stdlib (urllib.request, no libraries)
- `send_telegram_message()` posts directly to Telegram Bot API
- Markdown formatting for rich alerts
- Requires TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in .env

### Environment Configuration

Required:
- `TELEGRAM_BOT_TOKEN` - Bot token from @BotFather
- `TELEGRAM_CHAT_ID` - Numeric chat ID (get from /getUpdates)

Optional:
- `CRASH_ALERT_THRESHOLD` - Minimum probability to trigger alert (default: 0.2)
- `SEND_DAILY_SUMMARY` - Send daily update regardless of alert (default: false)
- `DAILY_SUMMARY_HOUR` - UTC hour for daily summary (default: 12)

## Key Technical Details

### VectorBT Strategy Structure

The `initial.py` module contains an EVOLVE-BLOCK section designed for LLM-based strategy evolution. Key indicators used:
- RSI (14 period)
- MACD (12/26/9)
- Bollinger Bands (20 period, 2 std)
- ATR (short: 5, long: 20)
- Moving averages (SMA 20/50, EMA 50)
- Multi-timeframe EMA (4h resampled)

All indicators are pre-computed in `_compute_base_indicators()` for performance.

### Alert System Logic

The crash detection system uses a smoothed composite probability:
1. Calculate 5 binary signals
2. Apply weighted sum (weights sum to 1.0)
3. Smooth with 3-period rolling mean
4. Generate three warning levels (0.2, 0.4, 0.6 thresholds)

The monitor sends alerts when current crash_probability crosses the threshold, with recommendations based on severity.

### Caching Strategy

Data is cached as parquet files in `datasets/` with naming: `{symbol}_{period}_{interval}.parquet`

**Multi-Crypto Monitor (Smart Caching):**
- Checks file modification time via `get_cache_age()`
- Only refreshes if cache is older than 1 hour (CACHE_EXPIRY = 3600 seconds)
- Dramatically reduces API calls and speeds up execution
- All 11 cryptos cached after first run

**Single BTC Monitor (Legacy):**
- Always uses `force_refresh=True` to get latest data
- Downloads fresh data every run
- Useful for testing or when absolute latest data is required

**Development:**
- Use `force_refresh=False` in `fetch_crypto_futures_data()` to use cache
- Avoids rate limits during development
- OKX used instead of Binance (geo-restrictions)

## Dependencies

All dependencies managed via uv/pyproject.toml:
- pandas (>=2.3.3)
- ccxt (>=4.5.14) - Exchange API for futures trading
- vectorbt (>=0.28.1) - Fast backtesting
- pyarrow (>=22.0.0) - Parquet support
- fastparquet (>=2024.11.0) - Parquet support
- python-dotenv (>=1.2.1) - Environment loading

Python 3.13+ required.
