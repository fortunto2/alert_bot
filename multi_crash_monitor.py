#!/usr/bin/env python3
"""
Multi-Crypto Crash Monitor - Monitor crash probability for perpetual futures.

Uses REAL futures data (OKX) with funding rates - the most critical metric for crash detection.
This is the production system for automated alerts on actual trading pairs.

Usage:
    python multi_crash_monitor.py

Features:
- Monitors top cryptocurrencies on perpetual futures (OKX)
- Includes funding rate analysis (critical for sentiment)
- Smart caching - only refreshes data if cache is older than 1 hour
- Sends consolidated Telegram alert with all warnings
- Parallel processing for faster execution

Data Source: OKX Perpetual Futures (live trading pairs)
Exchange: OKX (most reliable for non-US traders)
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
from data_loader_futures import fetch_crypto_futures_data

# Import strategy module to use crash detection
import importlib.util
spec = importlib.util.spec_from_file_location("strategy", Path(__file__).parent / "initial.py")
strategy_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(strategy_module)

# Top cryptocurrencies to monitor - OKX perpetual futures format
# Format: "BTC/USDT:USDT" for perpetual contracts
# TOP 5 by market cap + TRUMP
TOP_CRYPTOS = [
    "BTC/USDT:USDT",    # Bitcoin
    "ETH/USDT:USDT",    # Ethereum
    "SOL/USDT:USDT",    # Solana
    "XRP/USDT:USDT",    # Ripple
    "AVAX/USDT:USDT",   # Avalanche
    "TRUMP/USDT:USDT",  # Trump
]

# Exchange to use for futures data
EXCHANGE = "okx"

# Cache expiry time in seconds (1 hour)
CACHE_EXPIRY = 3600


def get_cache_age(symbol: str, exchange: str = "okx", period: str = "1mo", interval: str = "1h") -> float:
    """
    Get age of cached futures data in seconds.

    Returns:
        Age in seconds, or float('inf') if cache doesn't exist
    """
    cache_dir = Path(__file__).parent / "datasets"

    # Build cache filename following data_loader_futures pattern
    # Format: {exchange}_{symbol_safe}_{timeframe}_{date}_{limit}.parquet
    symbol_safe = symbol.replace("/", "-").replace(":", "_")

    # Find any matching cache file (we don't know the exact limit/date without loading)
    # Look for the most recent cache file for this symbol
    cache_files = list(cache_dir.glob(f"{exchange}_{symbol_safe}_1h_*.parquet"))

    if not cache_files:
        return float('inf')

    # Use the most recently modified file
    cache_file = max(cache_files, key=lambda p: p.stat().st_mtime)

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


def check_crash_probability_for_symbol(symbol: str, lookback_hours: int = 500, thresholds: dict = None, exchange: str = "okx"):
    """
    Check crash probability for a single futures symbol.

    Args:
        symbol: Trading pair symbol (e.g., "BTC/USDT:USDT" for perpetual futures)
        lookback_hours: How many hours of data to analyze
        thresholds: dict with 'pre_crash', 'early_warning', 'crisis' thresholds
        exchange: Exchange to fetch from (okx, bybit, deribit, etc.)

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
        cache_age = get_cache_age(symbol, exchange=exchange)
        force_refresh = cache_age > CACHE_EXPIRY

        if force_refresh:
            print(f"  {symbol}: Cache expired ({cache_age/60:.1f} min old), downloading fresh futures data...")
        else:
            print(f"  {symbol}: Using cached futures data ({cache_age/60:.1f} min old)")

        # Fetch FUTURES data with funding rates (critical for sentiment)
        df = fetch_crypto_futures_data(
            symbol=symbol,
            timeframe="1h",
            period="1mo",
            exchange=exchange,
            include_funding=True,
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
        market_strength = float(system.market_strength.iloc[latest_idx])
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
            'market_strength': market_strength,
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
        # Get crypto name from futures symbol
        crypto_name = metrics['symbol'].split('/')[0]
        crash_prob = metrics['crash_probability']

        # Determine alert level emoji
        if crash_prob >= thresholds['crisis']:
            alert_emoji = "🔴"
            alert_text = "КРИТИЧЕСКИЙ"
        elif crash_prob >= thresholds['early_warning']:
            alert_emoji = "🟠"
            alert_text = "ВЫСОКИЙ РИСК"
        elif crash_prob >= thresholds['pre_crash']:
            alert_emoji = "🟡"
            alert_text = "СРЕДНИЙ РИСК"
        else:
            alert_emoji = "🟢"
            alert_text = "НИЗКИЙ РИСК"

        # Market regime
        if metrics['market_strength'] > 0.6:
            if metrics['trend_strength'] > 0.5:
                market_regime = "📈 БЫЧ"
            else:
                market_regime = "➡️ КОНС"
        elif metrics['market_strength'] < 0.3:
            if metrics['trend_strength'] < 0.3:
                market_regime = "📉 МЕДВЕДЬ"
            else:
                market_regime = "⚠️ КРАХ"
        else:
            market_regime = "⚡ ВОЛАТ"

        # Price change color
        if metrics['change_24h'] > 0:
            price_color = f"🔵 {metrics['change_24h']:+.2f}%"
        else:
            price_color = f"🔴 {metrics['change_24h']:+.2f}%"

        # Add crypto alert - clean and simple
        message += f"{alert_emoji} *{crypto_name}* — {alert_text}\n"
        message += f"Цена: {format_price(metrics['price'])} {price_color}\n"
        message += f"Краш: *{crash_prob:.1%}* | RSI {metrics['rsi']:.0f} | {market_regime}\n"
        message += f"Fund: {metrics['funding_stress']:+.3f} | Mom: {metrics['momentum_strength']:.2f}\n\n"

    # Add recommendations based on highest alert level
    highest_alert = alerts[0]
    crash_prob = highest_alert['crash_probability']
    message += "⚡ *СТРАТЕГИЯ ДЕЙСТВИЯ:*\n\n"

    if crash_prob >= thresholds['crisis']:
        message += "🔴 *КРИТИЧЕСКИЙ КРАШ (≥{:.0%})*\n".format(thresholds['crisis'])
        message += "• ФЬЮЧЕРСЫ: 🟥 SHORT все позиции\n"
        message += "• Размер: Максимальный (полный левередж)\n"
        message += "• Стоп-лосс: Ширина волатильности × 1.5\n"
        message += "• Прибыль: ТП на -5% до -15%\n"
    elif crash_prob >= thresholds['early_warning']:
        message += "🟠 *ВЫСОКИЙ РИСК ({:.0%}-{:.0%})*\n".format(thresholds['early_warning'], thresholds['crisis'])
        message += "• ФЬЮЧЕРСЫ: 🟥 SHORT позиция 50% от максимума\n"
        message += "• СПОТ: Сократить LONG / Не покупать\n"
        message += "• Стоп-лосс: -8-10%\n"
    elif crash_prob >= thresholds['pre_crash']:
        message += "🟡 *СРЕДНИЙ РИСК ({:.0%}-{:.0%})*\n".format(thresholds['pre_crash'], thresholds['early_warning'])
        message += "• ФЬЮЧЕРСЫ: Готовиться к SHORT\n"
        message += "• СПОТ: Осторожно - не открывать новые LONG\n"
        message += "• Наблюдать за funding rate\n"

    message += f"\n_Обновлено: {highest_alert['timestamp'].strftime('%Y-%m-%d %H:%M UTC')}_\n"
    message += "_Futures Trading System (OKX Perpetual Futures)_\n"
    message += "_Powered by Gen11-47 Strategy_"

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
    print(f"ℹ️  Data source: PERPETUAL FUTURES ({EXCHANGE.upper()})")
    print("ℹ️  Includes funding rate analysis (critical for crash detection)")
    print("ℹ️  Crash probability = risk of PRICE DROP:")
    print(f"   🔴 ≥{thresholds['crisis']:.0%} = SHORT FUTURES / REDUCE LONGS | 🟠 {thresholds['early_warning']:.0%}-{thresholds['crisis']:.0%} = CAUTION | 🟡 {thresholds['pre_crash']:.0%}-{thresholds['early_warning']:.0%} = MONITOR | 🟢 <{thresholds['pre_crash']:.0%} = NORMAL")
    print()

    try:
        # Check all symbols in parallel
        all_metrics = []

        with ThreadPoolExecutor(max_workers=5) as executor:
            # Submit all tasks with thresholds and exchange
            future_to_symbol = {
                executor.submit(check_crash_probability_for_symbol, symbol, thresholds=thresholds, exchange=EXCHANGE): symbol
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
            # Extract crypto name from futures symbol (e.g., "BTC/USDT:USDT" -> "BTC")
            crypto_name = metrics['symbol'].split('/')[0]
            prob = metrics['crash_probability']
            change = metrics['change_24h']

            # Alert level emoji only
            if prob >= thresholds['crisis']:
                alert_emoji = "🔴"  # Red - Critical
            elif prob >= thresholds['early_warning']:
                alert_emoji = "🟠"  # Orange - High
            elif prob >= thresholds['pre_crash']:
                alert_emoji = "🟡"  # Yellow - Medium
            else:
                alert_emoji = "🟢"  # Green - Low

            # Price change: RED down, BLUE up, simple
            if change > 0:
                price_emoji = "🔵"  # Blue up
            else:
                price_emoji = "🔴"  # Red down

            # Format price with appropriate precision
            price_str = format_price(metrics['price']).replace('$', '')

            print(f"{alert_emoji} {crypto_name:8} {prob:6.1%}  ${price_str:>12}  {price_emoji} {change:+6.2f}%")

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
