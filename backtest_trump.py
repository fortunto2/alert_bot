"""
Quick VectorBT backtest on TRUMP futures using gen11-47 strategy.
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

from initial import FuturesTradingStrategy


def backtest_trump_futures():
    """Backtest TRUMP/USDT futures from OKX."""

    print("\n" + "="*70)
    print("VECTORBT BACKTEST: TRUMP/USDT FUTURES (OKX)")
    print("="*70)

    try:
        # Load TRUMP futures data
        df = pd.read_parquet("/home/rustam/alert_bot/datasets/okx_TRUMP-USDT_USDT_1h_2025-10-02_820.parquet")

        # Set datetime as index
        df['datetime'] = pd.to_datetime(df['datetime'])
        df.set_index('datetime', inplace=True)

        print(f"✅ Loaded {len(df)} candles")
        print(f"   Date range: {df.index[0]} to {df.index[-1]}")
        print(f"   Price range: ${df['close'].min():.4f} - ${df['close'].max():.4f}")
        print(f"   Total period: ~{(df.index[-1] - df.index[0]).days} days")

        # Run strategy
        strategy = FuturesTradingStrategy(df)

        # Get signals
        crash_prob = strategy.crash_probability
        trend_strength = strategy.trend_strength

        print(f"\n📊 STRATEGY SIGNALS:")
        print(f"   Avg Crash Probability: {crash_prob.mean():.2%}")
        print(f"   Max Crash Prob: {crash_prob.max():.2%}")
        print(f"   Min Crash Prob: {crash_prob.min():.2%}")
        print(f"   Avg Trend Strength: {trend_strength.mean():.2%}")

        # Entry: strong uptrend + low crash risk
        entries = (trend_strength > 0.6) & (crash_prob < 0.3)

        # Exit: high crash probability
        exits = crash_prob > 0.5

        num_entries = entries.sum()
        num_exits = exits.sum()

        print(f"\n📈 SIGNALS GENERATED:")
        print(f"   Entry signals: {num_entries}")
        print(f"   Exit signals: {num_exits}")

        # Run VectorBT backtest
        price = df['close'].values

        pf = vbt.Portfolio.from_signals(
            close=price,
            entries=entries.values,
            exits=exits.values,
            init_cash=10000,
            fees=0.001,  # 0.1% exchange fee
            freq='1h'
        )

        # Get metrics
        total_return = pf.total_return()
        annual_return = pf.annualized_return()
        sharpe_ratio = pf.sharpe_ratio()
        max_drawdown = pf.max_drawdown()

        # Buy & hold
        buyhold_return = (price[-1] / price[0]) - 1
        outperformance = total_return - buyhold_return

        # Trades
        num_trades = len(pf.trades.records) if hasattr(pf.trades, 'records') else 0

        try:
            win_rate = float(pf.trades.win_rate) if hasattr(pf.trades, 'win_rate') else 0.0
        except:
            win_rate = 0.0

        print(f"\n🚀 BACKTEST RESULTS (VectorBT):")
        print(f"   Strategy Return: {total_return:+.2%}")
        print(f"   Annualized Return: {annual_return:+.2%}")
        print(f"   Buy & Hold Return: {buyhold_return:+.2%}")
        print(f"   Outperformance: {outperformance:+.2%}")
        print(f"   Sharpe Ratio: {sharpe_ratio:.2f}")
        print(f"   Max Drawdown: {max_drawdown:.2%}")
        print(f"   Win Rate: {win_rate:.1%}")
        print(f"   Total Trades: {num_trades}")

        # Portfolio value
        start_val = 10000
        final_val = pf.final_value()

        print(f"\n💰 PORTFOLIO:")
        print(f"   Starting Capital: ${start_val:,.2f}")
        print(f"   Final Value: ${final_val:,.2f}")
        print(f"   Profit/Loss: ${final_val - start_val:+,.2f}")

        # Analysis
        print(f"\n📋 ANALYSIS:")
        if outperformance > 0:
            print(f"   ✅ Strategy OUTPERFORMED buy-and-hold by {outperformance:+.2%}")
        else:
            print(f"   ❌ Strategy UNDERPERFORMED buy-and-hold by {outperformance:+.2%}")

        if num_trades > 0:
            print(f"   Average P&L per trade: {(total_return / num_trades):.3%}")

        print(f"\n⚡ VectorBT: Fills 1M orders in 70-100ms!")

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    backtest_trump_futures()
