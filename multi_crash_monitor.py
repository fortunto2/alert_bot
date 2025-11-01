#!/usr/bin/env python3
"""
Multi-Crypto Crash Monitor - Monitor crash probability for multiple cryptocurrencies.

Usage:
    python multi_crash_monitor.py

Features:
- Monitors top cryptocurrencies simultaneously (BTC, ETH, SOL, XRP, ADA, DOGE, AVAX, DOT, LINK, LTC, TRUMP)
- Smart caching - only refreshes data if cache is older than 1 hour
- Sends consolidated Telegram alert with all warnings
- Parallel processing for faster execution
"""

import os
import sys
import json
from pathlib import Path
from datetime import datetime, timezone, timedelta
import urllib.request
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed

# Add current directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

import pandas as pd
from data_loader import fetch_crypto_data

# Import strategy module to use crash detection
import importlib.util
spec = importlib.util.spec_from_file_location("strategy", Path(__file__).parent / "initial.py")
strategy_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(strategy_module)

# Top cryptocurrencies to monitor (excluding stablecoins)
TOP_CRYPTOS = [
    "BTC-USD",    # Bitcoin
    "ETH-USD",    # Ethereum
    "SOL-USD",    # Solana
    "XRP-USD",    # Ripple
    "ADA-USD",    # Cardano
    "DOGE-USD",   # Dogecoin
    "AVAX-USD",   # Avalanche
    "DOT-USD",    # Polkadot
    "LINK-USD",   # Chainlink
    "LTC-USD",    # Litecoin
    "TRUMP-USD",  # Trump Meme Coin
]

# Cache expiry time in seconds (1 hour)
CACHE_EXPIRY = 3600


def get_cache_age(symbol: str, period: str = "1mo", interval: str = "1h") -> float:
    """
    Get age of cached data in seconds.

    Returns:
        Age in seconds, or float('inf') if cache doesn't exist
    """
    cache_dir = Path(__file__).parent / "datasets"
    cache_file = cache_dir / f"{symbol}_{period}_{interval}.parquet"

    if not cache_file.exists():
        return float('inf')

    # Get file modification time
    mtime = cache_file.stat().st_mtime
    age = datetime.now().timestamp() - mtime

    return age


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


def check_crash_probability_for_symbol(symbol: str, lookback_hours: int = 500, thresholds: dict = None):
    """
    Check crash probability for a single symbol.

    Args:
        symbol: Trading pair symbol (e.g., "BTC-USD")
        lookback_hours: How many hours of data to analyze
        thresholds: dict with 'pre_crash', 'early_warning', 'crisis' thresholds

    Returns:
        dict with crash metrics, or None if error
    """
    try:
        # Default thresholds if not provided
        if thresholds is None:
            thresholds = {
                'pre_crash': 0.2,
                'early_warning': 0.4,
                'crisis': 0.6
            }

        # Check cache age
        cache_age = get_cache_age(symbol)
        force_refresh = cache_age > CACHE_EXPIRY

        if force_refresh:
            print(f"  {symbol}: Cache expired ({cache_age/60:.1f} min old), downloading fresh data...")
        else:
            print(f"  {symbol}: Using cache ({cache_age/60:.1f} min old)")

        # Fetch data (will use cache if available and fresh)
        df = fetch_crypto_data(
            symbol=symbol,
            period="1mo",
            interval="1h",
            force_refresh=force_refresh
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

        # Map crash probability to alert levels using configurable thresholds
        pre_crash_warning = bool(crash_prob >= thresholds['pre_crash'])
        early_warning = bool(crash_prob >= thresholds['early_warning'])
        crisis_alert = bool(crash_prob >= thresholds['crisis'])

        # Additional metrics
        rsi = float(system.rsi.iloc[latest_idx])
        # Use normalized ATR ratio (4h / 24h comparison)
        atr_ratio = float(system.atr_4h.iloc[latest_idx] / system.atr_24h.iloc[latest_idx])

        # New metrics from enhanced strategy
        volatility = float(system.norm_atr.iloc[latest_idx])
        trend_strength = float(system.trend_strength.iloc[latest_idx])
        momentum_strength = float(system.momentum_strength.iloc[latest_idx])
        funding_stress = float(system.funding_stress.iloc[latest_idx])
        vol_ratio_4h = float(system.vol_ratio_4h.iloc[latest_idx])

        # Calculate 24h change
        if len(df) >= 24:
            price_24h_ago = float(df['close'].iloc[latest_idx - 24])
            change_24h = ((current_price - price_24h_ago) / price_24h_ago) * 100
        else:
            change_24h = 0.0

        return {
            'symbol': symbol,
            'timestamp': current_time,
            'price': current_price,
            'change_24h': change_24h,
            'crash_probability': crash_prob,
            'pre_crash_warning': pre_crash_warning,
            'early_warning': early_warning,
            'crisis_alert': crisis_alert,
            'rsi': rsi,
            'atr_ratio': atr_ratio,
            'volatility': volatility,
            'trend_strength': trend_strength,
            'momentum_strength': momentum_strength,
            'funding_stress': funding_stress,
            'vol_ratio_4h': vol_ratio_4h,
        }

    except Exception as e:
        print(f"  {symbol}: Error - {str(e)}")
        return None


def format_price(price: float) -> str:
    """Format price with appropriate precision based on value."""
    if price >= 1.0:
        return f"${price:,.2f}"
    elif price >= 0.01:
        return f"${price:.4f}"
    elif price >= 0.0001:
        return f"${price:.6f}"
    else:
        return f"${price:.8f}"


def format_consolidated_alert(all_metrics: list, min_probability: float, thresholds: dict = None) -> str:
    """Format consolidated alert message for all cryptocurrencies."""

    # Default thresholds if not provided
    if thresholds is None:
        thresholds = {
            'pre_crash': 0.2,
            'early_warning': 0.4,
            'crisis': 0.6
        }

    # Filter to only alerts that meet threshold
    alerts = [m for m in all_metrics if m and m['crash_probability'] >= min_probability]

    if not alerts:
        return None

    # Sort by crash probability (highest first)
    alerts.sort(key=lambda x: x['crash_probability'], reverse=True)

    # Build message
    message = "🚨 *CRYPTO CRASH ALERTS* 🚨\n\n"

    for metrics in alerts:
        # Get crypto name (remove -USD suffix)
        crypto_name = metrics['symbol'].replace('-USD', '')

        # Determine alert level based on configurable thresholds
        if metrics['crash_probability'] >= thresholds['crisis']:
            alert_emoji = "🔴"
            alert_level = "КРИТИЧЕСКИЙ"
        elif metrics['crash_probability'] >= thresholds['early_warning']:
            alert_emoji = "🟠"
            alert_level = "ВЫСОКИЙ"
        elif metrics['crash_probability'] >= thresholds['pre_crash']:
            alert_emoji = "🟡"
            alert_level = "СРЕДНИЙ"
        else:
            alert_emoji = "🟢"
            alert_level = "НИЗКИЙ"

        # Price change emoji
        change_emoji = "📈" if metrics['change_24h'] > 0 else "📉"

        # Trend indicator
        trend_emoji = "📈" if metrics['trend_strength'] > 0.5 else "📉" if metrics['trend_strength'] < 0.3 else "➡️"

        # Volatility indicator
        if metrics['volatility'] > 0.03:
            vol_emoji = "⚡"
        elif metrics['volatility'] > 0.02:
            vol_emoji = "🔥"
        else:
            vol_emoji = "❄️"

        # Add crypto alert with compact metrics
        message += f"{alert_emoji} *{crypto_name}* - {alert_level}\n"
        message += f"Риск: *{metrics['crash_probability']:.1%}* | RSI: {metrics['rsi']:.0f}\n"
        message += f"{change_emoji} {format_price(metrics['price'])} ({metrics['change_24h']:+.1f}%) | "
        message += f"{trend_emoji} {metrics['trend_strength']:.2f} | {vol_emoji} {metrics['volatility']:.3f}\n"
        message += f"Моментум: {metrics['momentum_strength']:.2f} | Vol4h: {metrics['vol_ratio_4h']:.2f}\n\n"

    # Add recommendations based on highest alert level
    highest_alert = alerts[0]
    crash_prob = highest_alert['crash_probability']
    message += "⚡ *Рекомендации:*\n"

    if crash_prob >= thresholds['crisis']:
        message += f"• 🔴 *КРИТИЧЕСКИЙ РИСК ПАДЕНИЯ* (≥{thresholds['crisis']:.0%})\n"
        message += "• 🔴 СПОТ: Продать имеющиеся монеты / НЕ ПОКУПАТЬ\n"
        message += "• 🔴 ФЬЮЧЕРСЫ: Открыть SHORT / Закрыть LONG\n"
    elif crash_prob >= thresholds['early_warning']:
        message += f"• 🟠 *ВЫСОКИЙ РИСК ПАДЕНИЯ* ({thresholds['early_warning']:.0%}-{thresholds['crisis']:.0%})\n"
        message += "• 🟠 СПОТ: Сократить позиции / НЕ ПОКУПАТЬ\n"
        message += "• 🟠 ФЬЮЧЕРСЫ: Рассмотреть SHORT / Установить стопы\n"
    elif crash_prob >= thresholds['pre_crash']:
        message += f"• 🟡 *СРЕДНИЙ РИСК* ({thresholds['pre_crash']:.0%}-{thresholds['early_warning']:.0%})\n"
        message += "• 🟡 СПОТ: Осторожно с покупками\n"
        message += "• 🟡 ФЬЮЧЕРСЫ: Не открывать LONG без стопов\n"

    message += f"\n_Время: {highest_alert['timestamp'].strftime('%Y-%m-%d %H:%M UTC')}_"
    message += f"\n_Powered by Gen11 Strategy_"

    return message


def main():
    """Main monitoring function for multiple cryptocurrencies."""

    # Load config from environment or .env file
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass  # dotenv not required

    bot_token = os.environ.get('TELEGRAM_BOT_TOKEN')
    chat_id = os.environ.get('TELEGRAM_CHAT_ID')

    # Alert thresholds - load from environment or use defaults
    thresholds = {
        'pre_crash': float(os.environ.get('CRASH_ALERT_PRE_CRASH', '0.2')),
        'early_warning': float(os.environ.get('CRASH_ALERT_EARLY_WARNING', '0.4')),
        'crisis': float(os.environ.get('CRASH_ALERT_CRISIS', '0.6'))
    }

    # Minimum probability for sending any alert
    min_probability = float(os.environ.get('CRASH_ALERT_THRESHOLD', str(thresholds['pre_crash'])))

    if not bot_token or not chat_id:
        print("ERROR: TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID must be set")
        return 1

    print(f"🔍 Checking crash probability for {len(TOP_CRYPTOS)} cryptocurrencies...")
    print(f"Monitored: {', '.join([c.replace('-USD', '') for c in TOP_CRYPTOS])}")
    print(f"Alert threshold: {min_probability:.2%}")
    print(f"Alert levels: 🟡 ≥{thresholds['pre_crash']:.0%} | 🟠 ≥{thresholds['early_warning']:.0%} | 🔴 ≥{thresholds['crisis']:.0%}")
    print()
    print("ℹ️  Data source: SPOT prices (Yahoo Finance)")
    print("ℹ️  Crash probability = risk of PRICE DROP:")
    print(f"   🔴 ≥{thresholds['crisis']:.0%} = SELL SPOT/SHORT FUTURES | 🟠 {thresholds['early_warning']:.0%}-{thresholds['crisis']:.0%} = REDUCE | 🟡 {thresholds['pre_crash']:.0%}-{thresholds['early_warning']:.0%} = CAUTION | 🟢 <{thresholds['pre_crash']:.0%} = NORMAL")
    print()

    try:
        # Check all symbols in parallel
        all_metrics = []

        with ThreadPoolExecutor(max_workers=5) as executor:
            # Submit all tasks with thresholds
            future_to_symbol = {
                executor.submit(check_crash_probability_for_symbol, symbol, thresholds=thresholds): symbol
                for symbol in TOP_CRYPTOS
            }

            # Collect results as they complete
            for future in as_completed(future_to_symbol):
                symbol = future_to_symbol[future]
                try:
                    metrics = future.result()
                    if metrics:
                        all_metrics.append(metrics)
                except Exception as e:
                    print(f"  {symbol}: Exception - {str(e)}")

        print(f"\n📊 Successfully analyzed {len(all_metrics)}/{len(TOP_CRYPTOS)} cryptocurrencies")

        # Print summary
        print("\n" + "="*60)
        print("SUMMARY:")
        print("="*60)

        for metrics in sorted(all_metrics, key=lambda x: x['crash_probability'], reverse=True):
            crypto_name = metrics['symbol'].replace('-USD', '')
            prob = metrics['crash_probability']
            alert_status = "🔴 CRISIS" if prob >= thresholds['crisis'] else \
                          "🟠 HIGH" if prob >= thresholds['early_warning'] else \
                          "🟡 MEDIUM" if prob >= thresholds['pre_crash'] else \
                          "🟢 LOW"

            # Format price with appropriate precision
            price_str = format_price(metrics['price']).replace('$', '')  # Remove $ for alignment

            print(f"{alert_status:15} {crypto_name:8} {metrics['crash_probability']:6.2%}  "
                  f"${price_str:>12} ({metrics['change_24h']:+6.2f}%)")

        # Check if any alerts need to be sent
        alerts_to_send = [m for m in all_metrics if m['crash_probability'] >= min_probability]

        if alerts_to_send:
            print(f"\n⚠️ ALERT: {len(alerts_to_send)} cryptocurrencies above threshold!")
            print("📤 Sending Telegram notification...")

            message = format_consolidated_alert(all_metrics, min_probability, thresholds=thresholds)

            if message and send_telegram_message(bot_token, chat_id, message):
                print("✅ Alert sent successfully!")
                return 0
            else:
                print("❌ Failed to send alert")
                return 1
        else:
            print(f"\n✅ No alerts needed (all below {min_probability:.2%} threshold)")

            # Optional: send daily summary
            send_daily = os.environ.get('SEND_DAILY_SUMMARY', 'false').lower() == 'true'
            if send_daily:
                summary_hour = int(os.environ.get('DAILY_SUMMARY_HOUR', '12'))
                current_hour = datetime.now(timezone.utc).hour

                if current_hour == summary_hour:
                    print("📤 Sending daily summary...")
                    # Send summary of top 3 by crash probability
                    top3 = sorted(all_metrics, key=lambda x: x['crash_probability'], reverse=True)[:3]
                    message = format_consolidated_alert(top3, 0.0)  # Show all regardless of threshold
                    if message:
                        send_telegram_message(bot_token, chat_id, message)

            return 0

    except Exception as e:
        error_msg = f"❌ ERROR: {str(e)}"
        print(error_msg)

        # Send error notification
        try:
            send_telegram_message(bot_token, chat_id, f"⚠️ Multi-Crypto Monitor Error\n\n`{str(e)}`")
        except:
            pass

        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
