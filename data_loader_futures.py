"""
Data loader for crypto futures using CCXT (Binance, OKX, Bybit, etc).

Features:
    - OHLCV data for perpetual futures contracts
    - Funding rates (perpetual futures specific) - critical for strategy
    - Caching for faster re-runs
    - Support for multiple exchanges
    - Merging of funding rates with OHLCV data

Usage:
    # Fetch BTC futures from Binance
    df = fetch_crypto_futures_data(
        symbol="BTC/USDT:USDT",
        timeframe="1h",
        period="1mo",
        exchange="binance",
        include_funding=True
    )

    # Get just BTC without futures features (SPOT only)
    df = fetch_crypto_data(symbol="BTC-USD")
"""

import warnings
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional
import time

import pandas as pd
import numpy as np

# Try to import CCXT (for futures trading)
try:
    import ccxt
    CCXT_AVAILABLE = True
except ImportError:
    CCXT_AVAILABLE = False

# Try to import yfinance (for SPOT trading)
try:
    import yfinance as yf
    YFINANCE_AVAILABLE = True
except ImportError:
    YFINANCE_AVAILABLE = False

warnings.filterwarnings("ignore", category=FutureWarning)

DEFAULT_CACHE_DIR = Path(__file__).resolve().parent / "datasets"


# ============================================================================
# FUTURES DATA LOADING (CCXT) - Premium feature for real trading
# ============================================================================

def fetch_futures_ohlcv(
    symbol: str = "BTC/USDT:USDT",
    timeframe: str = "1h",
    since: Optional[str] = None,
    limit: int = 1000,
    force_refresh: bool = False,
    exchange_name: str = "binance",
    cache_dir: Optional[Path] = None,
) -> pd.DataFrame:
    """
    Fetch OHLCV data for perpetual futures from CCXT exchange.

    Args:
        symbol: Trading pair (e.g., 'BTC/USDT:USDT' for perpetual)
        timeframe: Candle timeframe ('1h', '4h', '1d', etc.)
        since: Start date (YYYY-MM-DD or datetime)
        limit: Max candles to fetch
        force_refresh: If True, bypass cache
        exchange_name: Exchange to use ('binance', 'okx', 'bybit', etc.)
        cache_dir: Cache directory

    Returns:
        DataFrame with columns: datetime, open, high, low, close, volume
    """
    if not CCXT_AVAILABLE:
        raise ImportError("CCXT is required for futures trading. Install with: pip install ccxt")

    if cache_dir is None:
        cache_dir = DEFAULT_CACHE_DIR
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)

    # Create cache filename
    symbol_safe = symbol.replace("/", "-").replace(":", "_")
    if since:
        since_str = since if isinstance(since, str) else since.strftime("%Y%m%d")
        cache_file = cache_dir / f"{exchange_name}_{symbol_safe}_{timeframe}_{since_str}_{limit}.parquet"
    else:
        cache_file = cache_dir / f"{exchange_name}_{symbol_safe}_{timeframe}_latest_{limit}.parquet"

    # Try to load from cache
    if not force_refresh and cache_file.exists():
        print(f"Loading cached futures data from {cache_file}")
        df = pd.read_parquet(cache_file)
        df['datetime'] = pd.to_datetime(df['datetime'], utc=True)
        return df

    print(f"Fetching {symbol} futures data from {exchange_name.upper()}...")

    # Initialize exchange
    try:
        exchange_class = getattr(ccxt, exchange_name)
    except AttributeError:
        raise ValueError(f"Exchange '{exchange_name}' not found in CCXT. Available: {ccxt.exchanges}")

    exchange = exchange_class({
        'enableRateLimit': True,
        'options': {'defaultType': 'swap'}  # Use perpetual swaps
    })

    # Parse since parameter
    if since:
        if isinstance(since, str):
            since_dt = pd.to_datetime(since, utc=True)
        else:
            since_dt = since
        since_ms = int(since_dt.timestamp() * 1000)
    else:
        since_ms = None

    # Fetch OHLCV data
    all_candles = []
    current_since = since_ms

    print(f"  Timeframe: {timeframe}")
    print(f"  Start: {since if since else 'Latest candles'}")
    print(f"  Limit: {limit}")

    while True:
        try:
            # Fetch batch (adjust limit based on exchange limits)
            batch_limit = min(500, limit - len(all_candles))
            ohlcv = exchange.fetch_ohlcv(
                symbol=symbol,
                timeframe=timeframe,
                since=current_since,
                limit=batch_limit
            )

            if not ohlcv:
                break

            all_candles.extend(ohlcv)
            print(f"  Fetched {len(ohlcv)} candles (total: {len(all_candles)})")

            # Check if we got enough or reached the end
            if len(all_candles) >= limit or len(ohlcv) < 50:
                break

            # Update since to last candle timestamp + 1ms
            current_since = ohlcv[-1][0] + 1

            # Rate limiting
            time.sleep(exchange.rateLimit / 1000)

        except Exception as e:
            print(f"Error fetching data: {e}")
            if len(all_candles) > 100:
                print("Using partial data...")
                break
            else:
                raise

    if len(all_candles) == 0:
        raise ValueError(f"No data fetched for {symbol}")

    # Convert to DataFrame
    df = pd.DataFrame(
        all_candles,
        columns=['timestamp', 'open', 'high', 'low', 'close', 'volume']
    )

    # Convert timestamp to datetime
    df['datetime'] = pd.to_datetime(df['timestamp'], unit='ms', utc=True)
    df = df.drop('timestamp', axis=1)

    # Reorder columns
    df = df[['datetime', 'open', 'high', 'low', 'close', 'volume']]

    # Sort by datetime
    df = df.sort_values('datetime').reset_index(drop=True)

    # Remove duplicates
    df = df.drop_duplicates(subset='datetime', keep='last')

    print(f"Downloaded {len(df)} candles from {df['datetime'].iloc[0]} to {df['datetime'].iloc[-1]}")

    # Save to cache
    df.to_parquet(cache_file)
    print(f"Saved to cache: {cache_file}")

    return df


def fetch_funding_rates(
    symbol: str = "BTC/USDT:USDT",
    since: Optional[str] = None,
    limit: int = 1000,
    force_refresh: bool = False,
    exchange_name: str = "binance",
    cache_dir: Optional[Path] = None,
) -> pd.DataFrame:
    """
    Fetch funding rate history for perpetual futures.

    Funding rates indicate market sentiment:
    - Positive: Longs are paying shorts (bullish, risky)
    - Negative: Shorts are paying longs (bearish, panic selling)
    - Updated every 8 hours typically

    Args:
        symbol: Trading pair (perpetual futures only)
        since: Start date (YYYY-MM-DD)
        limit: Max records to fetch
        force_refresh: Bypass cache
        exchange_name: Exchange to use
        cache_dir: Cache directory

    Returns:
        DataFrame with columns: datetime, funding_rate
    """
    if not CCXT_AVAILABLE:
        raise ImportError("CCXT is required for futures. Install with: pip install ccxt")

    if cache_dir is None:
        cache_dir = DEFAULT_CACHE_DIR
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)

    # Create cache filename
    symbol_safe = symbol.replace("/", "-").replace(":", "_")
    if since:
        since_str = since if isinstance(since, str) else since.strftime("%Y%m%d")
        cache_file = cache_dir / f"{exchange_name}_{symbol_safe}_funding_{since_str}_{limit}.parquet"
    else:
        cache_file = cache_dir / f"{exchange_name}_{symbol_safe}_funding_latest_{limit}.parquet"

    # Try cache
    if not force_refresh and cache_file.exists():
        print(f"Loading cached funding rates from {cache_file}")
        df = pd.read_parquet(cache_file)
        df['datetime'] = pd.to_datetime(df['datetime'], utc=True)
        return df

    print(f"Fetching funding rates for {symbol} from {exchange_name.upper()}...")

    # Initialize exchange
    exchange_class = getattr(ccxt, exchange_name)
    exchange = exchange_class({
        'enableRateLimit': True,
        'options': {'defaultType': 'swap'}
    })

    # Parse since
    if since:
        since_dt = pd.to_datetime(since, utc=True)
        since_ms = int(since_dt.timestamp() * 1000)
    else:
        since_ms = None

    # Fetch funding rate history
    try:
        funding_history = exchange.fetch_funding_rate_history(
            symbol=symbol,
            since=since_ms,
            limit=limit
        )

        if not funding_history:
            print("⚠️  No funding rate data available")
            return pd.DataFrame(columns=['datetime', 'funding_rate'])

        # Convert to DataFrame
        df = pd.DataFrame([
            {
                'datetime': pd.to_datetime(item['timestamp'], unit='ms', utc=True),
                'funding_rate': item['fundingRate']
            }
            for item in funding_history
        ])

        df = df.sort_values('datetime').reset_index(drop=True)

        print(f"Fetched {len(df)} funding rate records")
        if len(df) > 0:
            print(f"  Date range: {df['datetime'].iloc[0]} to {df['datetime'].iloc[-1]}")
            print(f"  Avg rate: {df['funding_rate'].mean():.6f}")
            print(f"  Min: {df['funding_rate'].min():.6f}, Max: {df['funding_rate'].max():.6f}")

        # Save to cache
        df.to_parquet(cache_file)
        print(f"Saved to cache: {cache_file}")

        return df

    except Exception as e:
        print(f"⚠️  Error fetching funding rates: {e}")
        return pd.DataFrame(columns=['datetime', 'funding_rate'])


def merge_ohlcv_with_funding(
    ohlcv_df: pd.DataFrame,
    funding_df: pd.DataFrame
) -> pd.DataFrame:
    """
    Merge OHLCV data with funding rates.

    Funding rates are updated every ~8h, so we use backward fill to match hourly data.

    Args:
        ohlcv_df: OHLCV DataFrame with 'datetime' column
        funding_df: Funding rate DataFrame with 'datetime' and 'funding_rate'

    Returns:
        Merged DataFrame with funding_rate column added
    """
    if funding_df.empty:
        ohlcv_df['funding_rate'] = 0.0
        return ohlcv_df

    # Merge on datetime with backward fill (use last known funding rate)
    merged = pd.merge_asof(
        ohlcv_df.sort_values('datetime'),
        funding_df[['datetime', 'funding_rate']].sort_values('datetime'),
        on='datetime',
        direction='backward'
    )

    # Fill any remaining NaNs with 0
    merged['funding_rate'] = merged['funding_rate'].fillna(0)

    return merged


def fetch_crypto_futures_data(
    symbol: str = "BTC/USDT:USDT",
    timeframe: str = "1h",
    period: str = "1mo",
    force_refresh: bool = False,
    include_funding: bool = True,
    exchange: str = "binance",
    cache_dir: Optional[Path] = None,
) -> pd.DataFrame:
    """
    Main function to fetch complete futures data with funding rates.

    Args:
        symbol: Trading pair (perpetual futures) - e.g., "BTC/USDT:USDT"
        timeframe: Candle timeframe - e.g., "1h", "4h", "1d"
        period: Time period - e.g., "1mo", "3mo", "1y"
        force_refresh: Bypass cache
        include_funding: Include funding rate data
        exchange: Exchange to use - "binance", "okx", "bybit", etc.
        cache_dir: Cache directory

    Returns:
        DataFrame with OHLCV + funding_rate columns
    """
    # Parse period to get since date
    period_map = {
        '1w': 7,
        '1mo': 30,
        '3mo': 90,
        '6mo': 180,
        '1y': 365,
        '2y': 730,
        '3y': 1095,
    }

    days = period_map.get(period, 30)
    since = datetime.now() - timedelta(days=days)
    since_str = since.strftime("%Y-%m-%d")

    # Calculate number of candles needed
    timeframe_hours = {
        '1m': 1/60, '5m': 5/60, '15m': 15/60, '30m': 30/60,
        '1h': 1, '2h': 2, '4h': 4, '6h': 6, '12h': 12,
        '1d': 24, '1w': 168
    }
    hours_per_candle = timeframe_hours.get(timeframe, 1)
    limit = int((days * 24) / hours_per_candle) + 100  # +100 buffer

    # Fetch OHLCV
    ohlcv_df = fetch_futures_ohlcv(
        symbol=symbol,
        timeframe=timeframe,
        since=since_str,
        limit=limit,
        force_refresh=force_refresh,
        exchange_name=exchange,
        cache_dir=cache_dir
    )

    # Fetch and merge funding rates
    if include_funding:
        funding_df = fetch_funding_rates(
            symbol=symbol,
            since=since_str,
            limit=limit // 8 + 100,  # Funding every 8h
            force_refresh=force_refresh,
            exchange_name=exchange,
            cache_dir=cache_dir
        )

        ohlcv_df = merge_ohlcv_with_funding(ohlcv_df, funding_df)
    else:
        ohlcv_df['funding_rate'] = 0.0

    return ohlcv_df


# ============================================================================
# SPOT DATA LOADING (Yahoo Finance) - Fallback for development
# ============================================================================

def fetch_crypto_data(
    symbol: str = "BTC-USD",
    period: str = "1mo",
    interval: str = "1h",
    cache_dir: Optional[Path] = None,
    force_refresh: bool = False,
) -> pd.DataFrame:
    """
    Fetch cryptocurrency SPOT data from Yahoo Finance with caching.

    NOTE: This is for SPOT market only, not suitable for futures trading.
    For production, use fetch_crypto_futures_data() instead.

    Args:
        symbol: Trading pair symbol (e.g., "BTC-USD", "ETH-USD")
        period: Time period to fetch (e.g., "1mo", "3mo", "1y", "2y")
        interval: Data interval (e.g., "1h", "4h", "1d")
        cache_dir: Directory to cache data
        force_refresh: If True, force re-download

    Returns:
        DataFrame with OHLCV data
    """
    if not YFINANCE_AVAILABLE:
        raise ImportError("yfinance is required. Install with: pip install yfinance")

    if cache_dir is None:
        cache_dir = DEFAULT_CACHE_DIR

    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)

    # Create cache filename
    cache_file = cache_dir / f"{symbol}_{period}_{interval}.parquet"

    # Try to load from cache
    if not force_refresh and cache_file.exists():
        print(f"Loading cached SPOT data from {cache_file}")
        df = pd.read_parquet(cache_file)
        return df

    # Download data from Yahoo Finance
    print(f"Downloading {symbol} SPOT data from Yahoo Finance...")
    print(f"  Period: {period}, Interval: {interval}")

    ticker = yf.Ticker(symbol)
    df = ticker.history(period=period, interval=interval)

    if df.empty:
        raise ValueError(f"No data returned for {symbol}. Check symbol name.")

    # Clean up column names
    df.columns = [col.lower() for col in df.columns]

    # Reset index to make datetime a column
    df = df.reset_index()

    # Rename datetime column
    if 'date' in df.columns:
        df = df.rename(columns={'date': 'datetime'})
    elif 'datetime' not in df.columns:
        raise ValueError("Could not find datetime column")

    # Ensure datetime is timezone-aware UTC
    if df['datetime'].dt.tz is None:
        df['datetime'] = df['datetime'].dt.tz_localize('UTC')
    else:
        df['datetime'] = df['datetime'].dt.tz_convert('UTC')

    # Select required columns
    df = df[['datetime', 'open', 'high', 'low', 'close', 'volume']]

    # Add dummy funding_rate for compatibility
    df['funding_rate'] = 0.0

    print(f"Downloaded {len(df)} candles from {df['datetime'].iloc[0]} to {df['datetime'].iloc[-1]}")

    # Save to cache
    df.to_parquet(cache_file)
    print(f"Saved to cache: {cache_file}")

    return df
