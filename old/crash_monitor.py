#!/usr/bin/env python3
"""
Crash Monitor - Real-time BTC crash probability detector with Telegram alerts.

Usage:
    python crash_monitor.py

Environment variables required:
    TELEGRAM_BOT_TOKEN - Your Telegram bot token
    TELEGRAM_CHAT_ID - Your Telegram chat ID

Setup:
    1. Create bot: talk to @BotFather on Telegram, get token
    2. Get chat ID: send message to your bot, then visit:
       https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates
    3. Set environment variables in .env file or export them
    4. Add to crontab: 0 * * * * /path/to/python /path/to/crash_monitor.py
"""

import os
import sys
import json
from pathlib import Path
from datetime import datetime, timezone
import urllib.request
import urllib.parse

# Add current directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

import pandas as pd
from data_loader import fetch_crypto_data

# Import strategy module to use crash detection
import importlib.util
spec = importlib.util.spec_from_file_location("strategy", Path(__file__).parent / "initial.py")
strategy_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(strategy_module)


def send_telegram_message(bot_token: str, chat_id: str, message: str, parse_mode: str = "Markdown"):
    """Send message to Telegram using direct API call (no libraries)."""
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"

    data = {
        'chat_id': chat_id,
        'text': message,
        'parse_mode': parse_mode,
    }

    # Encode data
    data_encoded = urllib.parse.urlencode(data).encode('utf-8')

    # Make request
    req = urllib.request.Request(url, data=data_encoded, method='POST')

    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            result = json.loads(response.read().decode('utf-8'))
            if result.get('ok'):
                return True
            else:
                print(f"Telegram API error: {result}")
                return False
    except Exception as e:
        print(f"Failed to send Telegram message: {e}")
        return False


def check_crash_probability(lookback_hours: int = 500):
    """
    Check current crash probability using the strategy's detection logic.

    Args:
        lookback_hours: How many hours of data to analyze

    Returns:
        dict with crash metrics
    """
    # Fetch latest data
    df = fetch_crypto_data(
        symbol="BTC-USD",
        period="1mo",  # Last month
        interval="1h",
        force_refresh=True  # Always get fresh data
    )

    # Take last N hours
    df = df.tail(lookback_hours).copy()

    # Set DatetimeIndex for VectorBT
    df['datetime'] = pd.to_datetime(df['datetime'])
    if 'datetime' in df.columns and not isinstance(df.index, pd.DatetimeIndex):
        df = df.set_index('datetime', drop=False)

    # Create trading system to compute crash probability
    system = strategy_module.AdaptiveTradingSystem(df)

    # Get latest values
    latest_idx = -1
    current_price = float(df['close'].iloc[latest_idx])
    current_time = df['datetime'].iloc[latest_idx]

    crash_prob = float(system.crash_probability.iloc[latest_idx])
    pre_crash_warning = bool(system.pre_crash_warning.iloc[latest_idx])
    early_warning = bool(system.early_warning.iloc[latest_idx])
    crisis_alert = bool(system.crisis_alert.iloc[latest_idx])

    # Additional metrics
    rsi = float(system.rsi.iloc[latest_idx])
    atr_ratio = float(system.atr_short.iloc[latest_idx] / system.atr_long.iloc[latest_idx])

    # Calculate 24h change
    if len(df) >= 24:
        price_24h_ago = float(df['close'].iloc[latest_idx - 24])
        change_24h = ((current_price - price_24h_ago) / price_24h_ago) * 100
    else:
        change_24h = 0.0

    return {
        'timestamp': current_time,
        'price': current_price,
        'change_24h': change_24h,
        'crash_probability': crash_prob,
        'pre_crash_warning': pre_crash_warning,
        'early_warning': early_warning,
        'crisis_alert': crisis_alert,
        'rsi': rsi,
        'atr_ratio': atr_ratio,
    }


def format_alert_message(metrics: dict) -> str:
    """Format crash alert message for Telegram."""

    # Determine alert level
    if metrics['crisis_alert']:
        alert_emoji = "🚨"
        alert_level = "КРИТИЧЕСКИЙ"
    elif metrics['early_warning']:
        alert_emoji = "⚠️"
        alert_level = "ВЫСОКИЙ"
    elif metrics['pre_crash_warning']:
        alert_emoji = "⚡"
        alert_level = "СРЕДНИЙ"
    else:
        alert_emoji = "ℹ️"
        alert_level = "НИЗКИЙ"

    # Price change emoji
    if metrics['change_24h'] > 0:
        change_emoji = "📈"
    else:
        change_emoji = "📉"

    # Format message
    message = f"""{alert_emoji} *BTC CRASH ALERT* {alert_emoji}

*Уровень риска:* {alert_level}
*Вероятность краша:* {metrics['crash_probability']:.2%}

{change_emoji} *Цена BTC:* ${metrics['price']:,.2f}
*Изменение 24h:* {metrics['change_24h']:+.2f}%

📊 *Технические индикаторы:*
• RSI: {metrics['rsi']:.1f}
• ATR Ratio: {metrics['atr_ratio']:.2f}

🕒 Время: {metrics['timestamp'].strftime('%Y-%m-%d %H:%M UTC')}

⚡ *Рекомендации:*
"""

    if metrics['crisis_alert']:
        message += "• 🔴 КРИТИЧЕСКИЙ РИСК - рассмотрите выход из позиций\n"
        message += "• 🔴 Вероятность сильного падения очень высока\n"
    elif metrics['early_warning']:
        message += "• 🟡 ВЫСОКИЙ РИСК - будьте готовы к волатильности\n"
        message += "• 🟡 Установите стоп-лоссы\n"
    elif metrics['pre_crash_warning']:
        message += "• 🟢 СРЕДНИЙ РИСК - наблюдайте за рынком\n"
        message += "• 🟢 Повышенная волатильность возможна\n"
    else:
        message += "• ✅ Риск в норме\n"

    message += f"\n_Powered by ShinkaEvolve Gen11 Strategy_"

    return message


def main():
    """Main monitoring function."""

    # Load config from environment or .env file
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass  # dotenv not required

    bot_token = os.environ.get('TELEGRAM_BOT_TOKEN')
    chat_id = os.environ.get('TELEGRAM_CHAT_ID')

    # Alert thresholds
    min_probability = float(os.environ.get('CRASH_ALERT_THRESHOLD', '0.4'))  # Default: pre_crash_warning (0.2)

    if not bot_token or not chat_id:
        print("ERROR: TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID must be set")
        print("\nSetup instructions:")
        print("1. Create bot with @BotFather on Telegram")
        print("2. Get your chat ID from https://api.telegram.org/bot<TOKEN>/getUpdates")
        print("3. Set environment variables:")
        print("   export TELEGRAM_BOT_TOKEN='your_token'")
        print("   export TELEGRAM_CHAT_ID='your_chat_id'")
        return 1

    print(f"🔍 Checking BTC crash probability...")
    print(f"Alert threshold: {min_probability:.2%}")

    try:
        # Check crash probability
        metrics = check_crash_probability()

        print(f"\n📊 Current metrics:")
        print(f"  Price: ${metrics['price']:,.2f} ({metrics['change_24h']:+.2f}% 24h)")
        print(f"  Crash probability: {metrics['crash_probability']:.2%}")
        print(f"  Pre-crash warning: {metrics['pre_crash_warning']}")
        print(f"  Early warning: {metrics['early_warning']}")
        print(f"  Crisis alert: {metrics['crisis_alert']}")

        # Send alert if probability exceeds threshold
        if metrics['crash_probability'] >= min_probability:
            print(f"\n⚠️ ALERT: Crash probability {metrics['crash_probability']:.2%} >= {min_probability:.2%}")
            print("📤 Sending Telegram notification...")

            message = format_alert_message(metrics)

            if send_telegram_message(bot_token, chat_id, message):
                print("✅ Alert sent successfully!")
                return 0
            else:
                print("❌ Failed to send alert")
                return 1
        else:
            print(f"\n✅ No alert needed (probability {metrics['crash_probability']:.2%} < {min_probability:.2%})")

            # Optional: send daily summary even if no alert
            send_daily = os.environ.get('SEND_DAILY_SUMMARY', 'false').lower() == 'true'
            if send_daily:
                # Check if current hour is the summary hour (default: 12 UTC)
                summary_hour = int(os.environ.get('DAILY_SUMMARY_HOUR', '12'))
                current_hour = datetime.now(timezone.utc).hour

                if current_hour == summary_hour:
                    print("📤 Sending daily summary...")
                    message = format_alert_message(metrics)
                    send_telegram_message(bot_token, chat_id, message)

            return 0

    except Exception as e:
        error_msg = f"❌ ERROR: {str(e)}"
        print(error_msg)

        # Send error notification
        try:
            send_telegram_message(bot_token, chat_id, f"⚠️ Crash Monitor Error\n\n`{str(e)}`")
        except:
            pass

        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
