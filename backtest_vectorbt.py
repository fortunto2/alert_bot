"""
Backtest gen11-47 strategy using VectorBT Portfolio - fastest backtesting engine.
Uses actual trading signals from FuturesTradingStrategy to generate entries/exits.
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


def backtest_vectorbt(symbol: str, days: int = 30) -> dict:
    """
    Backtest strategy using VectorBT Portfolio - 1M orders in 70-100ms!

    Returns comprehensive backtest metrics.
    """
    print(f"\n{'='*70}")
    print(f"VECTORBT BACKTEST: {symbol} - Last {days} days")
    print(f"{'='*70}")

    try:
        # Determine period string
        if days <= 7:
            period_str = "1mo"
        elif days <= 30:
            period_str = "1mo"
        elif days <= 90:
            period_str = "3mo"
        else:
            period_str = "6mo"

        # Fetch data
        df = fetch_crypto_data(symbol, period=period_str, interval="1h", force_refresh=False)

        # Set datetime as index
        if 'datetime' in df.columns:
            df['datetime'] = pd.to_datetime(df['datetime'])
            df.set_index('datetime', inplace=True)
        else:
            df.index = pd.to_datetime(df.index)

        # Take only last N days
        cutoff_date = pd.Timestamp.now(tz='UTC') - timedelta(days=days)
        df_subset = df[df.index >= cutoff_date].copy()

        if len(df_subset) < 24:
            print(f"❌ Not enough data: only {len(df_subset)} candles")
            return None

        print(f"✅ Loaded {len(df_subset)} candles from {df_subset.index[0]} to {df_subset.index[-1]}")
        print(f"   Price range: ${df_subset['close'].min():.2f} - ${df_subset['close'].max():.2f}")

        # Run strategy to get signals
        strategy = FuturesTradingStrategy(df_subset)

        # Generate entry/exit signals based on crash probability and trend
        crash_prob = strategy.crash_probability
        trend_strength = strategy.trend_strength

        # Entry signal: strong uptrend + low crash risk
        entries = (trend_strength > 0.6) & (crash_prob < 0.3)

        # Exit signal: high crash probability (take profits/reduce risk)
        exits = crash_prob > 0.5

        # Convert to numpy for VectorBT
        price = df_subset['close'].values
        entries_arr = entries.values
        exits_arr = exits.values

        # Create Portfolio using VectorBT
        # fees=0.001 = 0.1% trading fee (typical exchange)
        # init_cash=10000 = start with $10k
        pf = vbt.Portfolio.from_signals(
            close=price,
            entries=entries_arr,
            exits=exits_arr,
            init_cash=10000,
            fees=0.001,  # 0.1% fee per trade
            freq='1h'
        )

        # Extract metrics
        total_return = pf.total_return()
        annual_return = pf.annualized_return()
        sharpe_ratio = pf.sharpe_ratio()
        max_drawdown = pf.max_drawdown()

        # Win rate - check if trades exist
        try:
            win_rate = float(pf.trades.win_rate) if hasattr(pf.trades, 'win_rate') else 0.0
        except:
            win_rate = 0.0

        num_trades = len(pf.trades.records) if hasattr(pf.trades, 'records') else 0

        # Buy and hold comparison
        buyhold_return = (price[-1] / price[0]) - 1

        # Get stats
        stats = pf.stats()

        print(f"\n📊 VECTORBT RESULTS:")
        print(f"   Total Return: {total_return:+.2%}")
        print(f"   Annualized: {annual_return:+.2%}")
        print(f"   Buy & Hold: {buyhold_return:+.2%}")
        print(f"   Outperformance: {(total_return - buyhold_return):+.2%}")
        print(f"   Sharpe Ratio: {sharpe_ratio:.2f}")
        print(f"   Max Drawdown: {max_drawdown:.2%}")
        print(f"   Win Rate: {win_rate:.1%}")
        print(f"   Total Trades: {num_trades}")
        if num_trades > 0:
            print(f"   Avg Trade PnL: {(total_return / num_trades):.3%}")

        # Show some stats
        print(f"\n📈 ADDITIONAL STATS:")
        print(f"   Starting Capital: $10,000")
        print(f"   Final Portfolio Value: ${pf.final_value():.2f}")
        print(f"   Total Profit/Loss: ${pf.final_value() - 10000:.2f}")

        return {
            'symbol': symbol,
            'days': days,
            'total_return': total_return,
            'annual_return': annual_return,
            'buyhold_return': buyhold_return,
            'outperformance': total_return - buyhold_return,
            'sharpe_ratio': sharpe_ratio,
            'max_drawdown': max_drawdown,
            'win_rate': win_rate,
            'trades': num_trades,
            'final_value': pf.final_value(),
            'start_price': price[0],
            'end_price': price[-1],
            'num_candles': len(price),
        }

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return None


def main():
    """Run VectorBT backtest on multiple timeframes."""

    symbols = ['BTC-USD', 'ETH-USD', 'SOL-USD', 'XRP-USD', 'AVAX-USD']

    all_results = []

    # Test 1 week and 1 month
    for days in [7, 30]:
        print(f"\n\n{'#'*70}")
        print(f"# VECTORBT BACKTEST - LAST {days} DAYS")
        print(f"{'#'*70}")

        for symbol in symbols:
            result = backtest_vectorbt(symbol, days=days)
            if result:
                all_results.append(result)

    # Summary table
    if all_results:
        print(f"\n\n{'='*90}")
        print("VECTORBT SUMMARY TABLE")
        print(f"{'='*90}\n")

        results_df = pd.DataFrame(all_results)

        # Separate by timeframe
        for days in [7, 30]:
            print(f"\n📅 LAST {days} DAYS (VectorBT Portfolio Simulation):")
            print("-" * 90)

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
        print(f"\n\n{'='*90}")
        print("INTERPRETATION (VectorBT - Fastest Backtester)")
        print(f"{'='*90}\n")

        week_data = results_df[results_df['days'] == 7]
        month_data = results_df[results_df['days'] == 30]

        if not week_data.empty:
            avg_ret_week = week_data['total_return'].mean()
            avg_out_week = week_data['outperformance'].mean()
            best_week = week_data['total_return'].max()
            print(f"📊 LAST 7 DAYS:")
            print(f"   Avg Strategy Return: {avg_ret_week:+.2%}")
            print(f"   Avg Outperformance: {avg_out_week:+.2%}")
            print(f"   Best: {week_data.loc[week_data['total_return'].idxmax(), 'symbol']} ({best_week:+.2%})")

        if not month_data.empty:
            avg_ret_month = month_data['total_return'].mean()
            avg_out_month = month_data['outperformance'].mean()
            best_month = month_data['total_return'].max()
            print(f"\n📊 LAST 30 DAYS:")
            print(f"   Avg Strategy Return: {avg_ret_month:+.2%}")
            print(f"   Avg Outperformance: {avg_out_month:+.2%}")
            print(f"   Best: {month_data.loc[month_data['total_return'].idxmax(), 'symbol']} ({best_month:+.2%})")

        print(f"\n⚡ Performance: VectorBT fills 1,000,000 orders in 70-100ms on M1!")
        print(f"   This backtest uses Portfolio.from_signals() - fastest open source engine")


if __name__ == "__main__":
    main()
