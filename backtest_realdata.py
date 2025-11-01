"""
Backtest gen11-47 strategy on real data from last week and last month.
Shows actual P&L if trading started 1 week ago or 1 month ago.
"""

from __future__ import annotations

import sys
from pathlib import Path
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import vectorbt as vbt

# Add alert_bot to path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from data_loader import fetch_crypto_data
from initial import FuturesTradingStrategy


def backtest_period(symbol: str, days: int = 30) -> dict:
    """
    Backtest strategy on last N days of real data.

    Returns:
        Dict with backtest metrics (Sharpe, return, drawdown, trades, etc)
    """
    print(f"\n{'='*60}")
    print(f"BACKTEST: {symbol} - Last {days} days")
    print(f"{'='*60}")

    try:
        # Determine period string
        if days <= 7:
            period_str = "1mo"  # Get 1 month to ensure we have enough data
        elif days <= 30:
            period_str = "1mo"
        elif days <= 90:
            period_str = "3mo"
        else:
            period_str = "6mo"

        # Fetch data
        df = fetch_crypto_data(symbol, period=period_str, interval="1h", force_refresh=False)

        # Set datetime as index if it's a column
        if 'datetime' in df.columns:
            df['datetime'] = pd.to_datetime(df['datetime'])
            df.set_index('datetime', inplace=True)
        else:
            df.index = pd.to_datetime(df.index)

        # Take only last N days
        cutoff_date = pd.Timestamp.now(tz='UTC') - timedelta(days=days)
        df_subset = df[df.index >= cutoff_date].copy()

        if len(df_subset) < 24:  # Need at least 24 hours
            print(f"❌ Not enough data: only {len(df_subset)} candles")
            return None

        print(f"✅ Loaded {len(df_subset)} candles from {df_subset.index[0]} to {df_subset.index[-1]}")
        print(f"   Price range: ${df_subset['close'].min():.2f} - ${df_subset['close'].max():.2f}")

        # Run strategy
        strategy = FuturesTradingStrategy(df_subset)

        # Get signals from strategy
        crash_prob = strategy.crash_probability

        # Use actual trading signals from strategy
        # Trend following signal: long when trend strong
        long_signal = strategy.trend_strength > 0.6
        short_signal = strategy.crash_probability > 0.6

        # Position: 1 = long, -1 = short, 0 = flat
        position = np.where(
            short_signal,
            -1,  # Short when crash probability > 60%
            np.where(long_signal & (crash_prob < 0.3), 1, 0)  # Long only in strong uptrend + low crash risk
        )
        position = pd.Series(position, index=df_subset.index)

        # Calculate returns
        price_returns = df_subset['close'].pct_change()
        strategy_returns = position.shift(1) * price_returns  # Delayed entry

        # Calculate metrics
        total_return = (1 + strategy_returns).prod() - 1
        cumulative_returns = (1 + strategy_returns).cumprod()
        sharpe_ratio = calculate_sharpe(strategy_returns)
        max_drawdown = calculate_max_drawdown(cumulative_returns)

        # Count trades
        position_changes = position != position.shift()
        trades = position_changes[position_changes].sum() // 2  # Entry + exit = 2 changes

        # Win rate
        win_rate = (strategy_returns > 0).sum() / len(strategy_returns)

        # Buy & hold comparison
        buyhold_return = (df_subset['close'].iloc[-1] / df_subset['close'].iloc[0]) - 1

        print(f"\n📊 RESULTS:")
        print(f"   Strategy Return: {total_return:+.2%}")
        print(f"   Buy & Hold:      {buyhold_return:+.2%}")
        print(f"   Outperformance:  {(total_return - buyhold_return):+.2%}")
        print(f"   Sharpe Ratio: {sharpe_ratio:.2f}")
        print(f"   Max Drawdown: {max_drawdown:.2%}")
        print(f"   Win Rate: {win_rate:.1%}")
        print(f"   Trades: {int(trades)}")
        if trades > 0:
            print(f"   Avg Return/Trade: {(total_return / trades):.3%}")

        return {
            'symbol': symbol,
            'days': days,
            'total_return': total_return,
            'buyhold_return': buyhold_return,
            'outperformance': total_return - buyhold_return,
            'sharpe_ratio': sharpe_ratio,
            'max_drawdown': max_drawdown,
            'win_rate': win_rate,
            'trades': int(trades),
            'candles': len(df_subset),
            'start_price': df_subset['close'].iloc[0],
            'end_price': df_subset['close'].iloc[-1],
        }

    except Exception as e:
        print(f"❌ Error: {e}")
        return None


def calculate_sharpe(returns: pd.Series, rf=0.0) -> float:
    """Calculate Sharpe ratio (annualized)."""
    if returns.std() == 0:
        return 0.0
    return (returns.mean() - rf) / returns.std() * np.sqrt(24 * 365)


def calculate_max_drawdown(cumulative_returns: pd.Series) -> float:
    """Calculate max drawdown."""
    running_max = cumulative_returns.expanding().max()
    drawdown = (cumulative_returns - running_max) / running_max
    return drawdown.min()


def main():
    """Run backtest on multiple timeframes."""

    symbols = ['BTC-USD', 'ETH-USD', 'SOL-USD', 'XRP-USD', 'AVAX-USD']

    all_results = []

    # Test 1 week and 1 month
    for days in [7, 30]:
        print(f"\n\n{'#'*60}")
        print(f"# TESTING LAST {days} DAYS")
        print(f"{'#'*60}")

        for symbol in symbols:
            result = backtest_period(symbol, days=days)
            if result:
                all_results.append(result)

    # Summary table
    if all_results:
        print(f"\n\n{'='*80}")
        print("SUMMARY TABLE")
        print(f"{'='*80}\n")

        results_df = pd.DataFrame(all_results)

        # Separate by timeframe
        for days in [7, 30]:
            print(f"\n📅 LAST {days} DAYS:")
            print("-" * 80)

            subset = results_df[results_df['days'] == days].copy()
            if not subset.empty:
                subset = subset.sort_values('total_return', ascending=False)

                for _, row in subset.iterrows():
                    print(f"{row['symbol']:10} | Strategy: {row['total_return']:+7.2%} | "
                          f"B&H: {row['buyhold_return']:+7.2%} | "
                          f"Out: {row['outperformance']:+7.2%} | "
                          f"Sharpe: {row['sharpe_ratio']:6.2f} | "
                          f"Trades: {row['trades']:3.0f}")

        # Overall performance
        print(f"\n\n{'='*80}")
        print("INTERPRETATION")
        print(f"{'='*80}\n")

        week_data = results_df[results_df['days'] == 7]
        month_data = results_df[results_df['days'] == 30]

        if not week_data.empty:
            avg_ret_week = week_data['total_return'].mean()
            avg_bh_week = week_data['buyhold_return'].mean()
            avg_out_week = week_data['outperformance'].mean()
            best_week = week_data['total_return'].max()
            print(f"📊 LAST 7 DAYS:")
            print(f"   Avg Strategy Return: {avg_ret_week:+.2%}")
            print(f"   Avg Buy & Hold:      {avg_bh_week:+.2%}")
            print(f"   Avg Outperformance:  {avg_out_week:+.2%}")
            print(f"   Best performer: {week_data.loc[week_data['total_return'].idxmax(), 'symbol']} ({best_week:+.2%})")

        if not month_data.empty:
            avg_ret_month = month_data['total_return'].mean()
            avg_bh_month = month_data['buyhold_return'].mean()
            avg_out_month = month_data['outperformance'].mean()
            best_month = month_data['total_return'].max()
            print(f"\n📊 LAST 30 DAYS:")
            print(f"   Avg Strategy Return: {avg_ret_month:+.2%}")
            print(f"   Avg Buy & Hold:      {avg_bh_month:+.2%}")
            print(f"   Avg Outperformance:  {avg_out_month:+.2%}")
            print(f"   Best performer: {month_data.loc[month_data['total_return'].idxmax(), 'symbol']} ({best_month:+.2%})")


if __name__ == "__main__":
    main()
