"""
Data loader for crypto crash monitoring.

Fetches historical cryptocurrency data from Yahoo Finance and caches it locally
for faster subsequent loads. Provides automatic feature engineering for technical analysis.
"""

from __future__ import annotations

import warnings
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

# Suppress yfinance warnings
warnings.filterwarnings("ignore", category=FutureWarning)

try:
    import yfinance as yf
except ImportError:
    raise ImportError(
        "yfinance is required for the crypto_trading example. "
        "Install with: pip install yfinance"
    )


DEFAULT_CACHE_DIR = Path(__file__).resolve().parent / "datasets"


def fetch_crypto_data(
    symbol: str = "BTC-USD",
    period: str = "2y",
    interval: str = "1h",
    cache_dir: Optional[Path] = None,
    force_refresh: bool = False,
) -> pd.DataFrame:
    """
    Fetch cryptocurrency data from Yahoo Finance with caching.

    Args:
        symbol: Trading pair symbol (e.g., "BTC-USD", "ETH-USD")
        period: Time period to fetch (e.g., "1mo", "3mo", "1y", "2y", "max")
        interval: Data interval (e.g., "1m", "5m", "15m", "1h", "1d")
        cache_dir: Directory to cache data (default: datasets/)
        force_refresh: If True, force re-download even if cached

    Returns:
        DataFrame with OHLCV data and additional features
    """
    if cache_dir is None:
        cache_dir = DEFAULT_CACHE_DIR

    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)

    # Create cache filename
    cache_file = cache_dir / f"{symbol}_{period}_{interval}.parquet"

    # Try to load from cache
    if not force_refresh and cache_file.exists():
        print(f"Loading cached data from {cache_file}")
        df = pd.read_parquet(cache_file)
        return df

    # Download data from Yahoo Finance
    print(f"Downloading {symbol} data from Yahoo Finance...")
    print(f"  Period: {period}, Interval: {interval}")

    ticker = yf.Ticker(symbol)
    df = ticker.history(period=period, interval=interval)

    if df.empty:
        raise ValueError(
            f"No data returned for {symbol}. "
            f"Check symbol name and try again."
        )

    # Clean up column names
    df.columns = [col.lower() for col in df.columns]

    # Reset index to make datetime a column
    df = df.reset_index()

    # Find the datetime column (could be 'date', 'datetime', or index name)
    datetime_col = None
    for col in df.columns:
        if col.lower() in ["date", "datetime"] or pd.api.types.is_datetime64_any_dtype(df[col]):
            datetime_col = col
            break

    if datetime_col is None:
        raise ValueError("Could not find datetime column in data")

    # Rename to 'datetime'
    if datetime_col != "datetime":
        df = df.rename(columns={datetime_col: "datetime"})

    # Ensure datetime is timezone-aware UTC
    if not pd.api.types.is_datetime64_any_dtype(df["datetime"]):
        df["datetime"] = pd.to_datetime(df["datetime"], utc=True)
    elif df["datetime"].dt.tz is None:
        df["datetime"] = pd.to_datetime(df["datetime"], utc=True)
    else:
        df["datetime"] = df["datetime"].dt.tz_convert("UTC")

    # Sort by datetime
    df = df.sort_values("datetime").reset_index(drop=True)

    # Remove any duplicate timestamps
    df = df.drop_duplicates(subset=["datetime"], keep="last")

    # Add basic features
    df = add_basic_features(df)

    # Save to cache
    print(f"Saving to cache: {cache_file}")
    df.to_parquet(cache_file, index=False)

    print(f"Downloaded {len(df)} records from {df['datetime'].min()} to {df['datetime'].max()}")

    return df


def add_basic_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Add basic derived features to the dataframe.

    Args:
        df: DataFrame with OHLCV columns

    Returns:
        DataFrame with additional feature columns
    """
    df = df.copy()

    # Returns
    df["returns"] = df["close"].pct_change()
    df["log_returns"] = np.log(df["close"] / df["close"].shift(1))

    # High-Low range
    df["hl_range"] = (df["high"] - df["low"]) / df["close"]

    # Open-Close range
    df["oc_range"] = (df["close"] - df["open"]) / df["open"]

    # Volume change
    df["volume_change"] = df["volume"].pct_change()

    # Price momentum (rate of change)
    df["price_momentum_5"] = df["close"].pct_change(5)
    df["price_momentum_20"] = df["close"].pct_change(20)

    return df


# Example usage
if __name__ == "__main__":
    # Fetch BTC-USD hourly data for testing
    df = fetch_crypto_data(
        symbol="BTC-USD",
        period="1mo",
        interval="1h",
        force_refresh=False,
    )

    print(f"\nLoaded {len(df)} records")
    print(f"Date range: {df['datetime'].min()} to {df['datetime'].max()}")
    print(f"Latest price: ${df['close'].iloc[-1]:,.2f}")
    print("\nSample data:")
    print(df[["datetime", "open", "high", "low", "close", "volume"]].tail(5))
