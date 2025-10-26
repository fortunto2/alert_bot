# 🚨 Crypto Crash Monitor

Real-time cryptocurrency crash probability detector with Telegram alerts using Gen11 strategy.

## Features

- ✅ Monitor 11 cryptocurrencies simultaneously (BTC, ETH, SOL, XRP, ADA, DOGE, AVAX, DOT, LINK, LTC, TRUMP)
- ✅ Smart caching - only refreshes data older than 1 hour
- ✅ Parallel processing for fast execution
- ✅ Telegram notifications with alert levels
- ✅ Consolidated alerts for multiple cryptos
- ✅ Easy cron integration
- ✅ Configurable thresholds

## Quick Start

### 1. Create Telegram Bot

1. Talk to [@BotFather](https://t.me/BotFather) on Telegram
2. Send `/newbot` and follow instructions
3. Copy your bot token (looks like: `123456789:ABCdefGHIjklMNOpqrsTUVwxyz`)

### 2. Get Your Chat ID

1. Send any message to your bot
2. Visit: `https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates`
3. Find `"chat":{"id":123456789}` in the response
4. Copy the chat ID number

### 3. Configure Environment

```bash
cd /home/rustam/ShinkaEvolve-Private-Repo/examples/crypto_trading

# Copy example config
cp .env.example .env

# Edit with your credentials
nano .env
```

Set your values:
```bash
TELEGRAM_BOT_TOKEN=123456789:ABCdefGHIjklMNOpqrsTUVwxyz
TELEGRAM_CHAT_ID=123456789
CRASH_ALERT_THRESHOLD=0.2
```

### 4. Test Manually

**Multi-Crypto Monitor (Recommended):**
```bash
uv run python multi_crash_monitor.py
```

You should see:
```
🔍 Checking crash probability for 11 cryptocurrencies...
Monitored: BTC, ETH, SOL, XRP, ADA, DOGE, AVAX, DOT, LINK, LTC, TRUMP
Alert threshold: 20.00%

============================================================
SUMMARY:
============================================================
🟢 LOW           BTC       5.00%  $113,638.26 ( +1.81%)
🟢 LOW           ETH       5.00%  $  4,071.89 ( +2.90%)
...
✅ No alerts needed (all below 20.00% threshold)
```

**Single BTC Monitor (Legacy):**
```bash
uv run python crash_monitor.py
```

### 5. Add to Crontab (Run Every Hour)

**For Multi-Crypto Monitor (Recommended):**
```bash
# Edit crontab
crontab -e

# Add this line (adjust path to your repo):
0 * * * * cd /home/rustam/alert_bot && /home/rustam/.local/bin/uv run python multi_crash_monitor.py >> /tmp/multi_crypto_monitor.log 2>&1
```

**For Single BTC Monitor (Legacy):**
```bash
# Edit crontab
crontab -e

# Add this line:
0 * * * * cd /home/rustam/alert_bot && /home/rustam/.local/bin/uv run python crash_monitor.py >> /tmp/crash_monitor.log 2>&1
```

**Or use the helper script:**
```bash
chmod +x setup_cron.sh
./setup_cron.sh
```

## Alert Levels

The monitor uses Gen11's crash detection with 3 levels:

| Level | Probability | Emoji | What it means | Actions |
|-------|-------------|-------|---------------|---------|
| **КРИТИЧЕСКИЙ** | ≥ 60% | 🔴 | Very high crash risk | ❌ Close longs / ✅ Open shorts / 🚫 DON'T BUY |
| **ВЫСОКИЙ** | 40-60% | 🟠 | High crash risk | ⚠️ Reduce positions / Set stops / Consider shorts |
| **СРЕДНИЙ** | 20-40% | 🟡 | Medium risk | 👀 Watch closely / Don't open big longs |
| Низкий | < 20% | 🟢 | Normal risk | ✅ Normal trading |

### Understanding "Crash Probability"

**Data source:** SPOT prices from Yahoo Finance (not futures)

**Crash probability = probability of PRICE DROP (падение цены)**

#### For SPOT Trading (текущие данные):
- 🔴 **≥60%** → SELL coins you have / DON'T BUY (продать имеющиеся / не покупать)
- 🟠 **40-60%** → REDUCE positions / DON'T BUY (сократить / не покупать)
- 🟡 **20-40%** → CAUTION with buying (осторожно покупать)
- 🟢 **<20%** → NORMAL trading (нормальная торговля)

#### For FUTURES Trading (если используете фьючерсы):
- 🔴 **≥60%** → OPEN SHORT / CLOSE LONG (открыть шорт / закрыть лонг)
- 🟠 **40-60%** → CONSIDER SHORT / SET STOPS (рассмотреть шорт / поставить стопы)
- 🟡 **20-40%** → DON'T OPEN LONG (не открывать лонг)
- 🟢 **<20%** → CAN OPEN LONG (можно открыть лонг)

**Example:** TRUMP at 53% (🟠 HIGH risk)
- SPOT: Don't buy, sell if you have it
- FUTURES: Consider opening SHORT position

## Configuration

### Environment Variables

```bash
# Required
TELEGRAM_BOT_TOKEN=your_token
TELEGRAM_CHAT_ID=your_chat_id

# Optional
CRASH_ALERT_THRESHOLD=0.2    # Send alert when probability ≥ 20%
SEND_DAILY_SUMMARY=true       # Send daily update even if no alert
DAILY_SUMMARY_HOUR=12         # Hour (UTC) to send daily summary
```

### Custom Thresholds

To only get critical alerts:
```bash
CRASH_ALERT_THRESHOLD=0.6  # Only crisis alerts (≥60%)
```

To get all warnings:
```bash
CRASH_ALERT_THRESHOLD=0.2  # All alerts (≥20%)
```

## Example Alert Messages

### Crisis Alert (Probability ≥ 60%)

```
🚨 BTC CRASH ALERT 🚨

Уровень риска: КРИТИЧЕСКИЙ
Вероятность краша: 67.50%

📉 Цена BTC: $105,234.00
Изменение 24h: -8.45%

📊 Технические индикаторы:
• RSI: 28.3
• ATR Ratio: 2.45

🕒 Время: 2025-10-26 14:00 UTC

⚡ Рекомендации:
• 🔴 КРИТИЧЕСКИЙ РИСК - рассмотрите выход из позиций
• 🔴 Вероятность сильного падения очень высока

Powered by ShinkaEvolve Gen11 Strategy
```

### Pre-Crash Warning (Probability ≥ 20%)

```
⚡ BTC CRASH ALERT ⚡

Уровень риска: СРЕДНИЙ
Вероятность краша: 24.30%

📈 Цена BTC: $118,500.00
Изменение 24h: +1.23%

📊 Технические индикаторы:
• RSI: 72.1
• ATR Ratio: 1.35

🕒 Время: 2025-10-26 14:00 UTC

⚡ Рекомендации:
• 🟢 СРЕДНИЙ РИСК - наблюдайте за рынком
• 🟢 Повышенная волатильность возможна

Powered by ShinkaEvolve Gen11 Strategy
```

## Monitoring Logs

Check logs:
```bash
tail -f /tmp/crash_monitor.log
```

## Troubleshooting

### No messages received

1. Check bot token is correct
2. Verify chat ID is a number (not username)
3. Make sure you sent at least one message to the bot first
4. Test with manual run: `python crash_monitor.py`

### Cron not running

1. Check cron service is running: `systemctl status cron`
2. Verify paths in crontab are absolute
3. Check logs: `grep CRON /var/log/syslog`

### Import errors

Make sure you're using the virtual environment:
```bash
/home/rustam/ShinkaEvolve-Private-Repo/.venv/bin/python crash_monitor.py
```

## How It Works

1. **Fetches latest BTC data** (1 month, 1h candles)
2. **Runs Gen11 strategy** crash detection on last 500 hours
3. **Calculates crash probability** using:
   - Volatility spike detection (40% weight)
   - Price acceleration (20% weight)
   - Volume divergence (20% weight)
   - RSI extremes (15% weight)
   - Recent price drop (5% weight)
4. **Sends alert** if probability ≥ threshold
5. **Formats message** with recommendations based on level

## Performance

Gen11 strategy proven results:
- **October 2025 crash**: +5.84% while market dropped -8.10%
- **February 2025 crash**: -5.55% while market dropped -12.87%
- **Sharpe ratio**: 6.62 during crash periods

## License

Part of ShinkaEvolve project.
