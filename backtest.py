"""
Universal VectorBT backtest for OKX perpetual futures with fresh data.
Downloads latest data via data_loader, backtests with configurable thresholds.

Usage:
    uv run python backtest.py BTC                    # Test BTC last 90 days
    uv run python backtest.py TRUMP --days 7         # Test TRUMP last 7 days
    uv run python backtest.py ETH --days 30          # Test ETH last 30 days
    uv run python backtest.py SOL XRP AVAX           # Test multiple symbols
    uv run python backtest.py BTC --fresh            # Force re-download data
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import vectorbt as vbt
from dotenv import load_dotenv

# Add alert_bot to path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from data_loader import fetch_crypto_data
from initial import FuturesTradingStrategy

# Load environment
load_dotenv()


def fetch_futures_data(symbol: str, days: int = 90, force: bool = False) -> pd.DataFrame:
    """
    Fetch OKX perpetual futures data using data_loader.

    Args:
        symbol: Crypto symbol (BTC, ETH, SOL, etc.)
        days: How many days of data to fetch
        force: Force re-download even if cached

    Returns:
        DataFrame with OHLCV data
    """

    print(f"📥 Fetching {symbol}/USDT perpetual futures data...")

    # Determine period based on days
    if days <= 7:
        period = "1mo"
    elif days <= 30:
        period = "1mo"
    elif days <= 90:
        period = "3mo"
    elif days <= 180:
        period = "6mo"
    else:
        period = "1y"

    # Use Yahoo Finance symbol format (data_loader converts to OKX if needed)
    yf_symbol = f"{symbol}-USD"

    try:
        # Fetch data - this uses caching smart logic
        df = fetch_crypto_data(yf_symbol, period=period, interval="1h", force_refresh=force)

        # Set datetime as index
        if 'datetime' in df.columns:
            df['datetime'] = pd.to_datetime(df['datetime'])
            df.set_index('datetime', inplace=True)
        else:
            df.index = pd.to_datetime(df.index)

        # Take last N days
        cutoff_date = pd.Timestamp.now(tz='UTC') - timedelta(days=days)
        df_subset = df[df.index >= cutoff_date].copy()

        if len(df_subset) < 24:
            print(f"   ⚠️  Only {len(df_subset)} candles, using all available data...")
            df_subset = df.tail(max(168, len(df)))  # At least 1 week

        print(f"   ✅ Loaded {len(df_subset)} candles ({len(df_subset) / 24:.1f} days)")
        print(f"   📅 {df_subset.index[0].strftime('%Y-%m-%d %H:%M')} → {df_subset.index[-1].strftime('%Y-%m-%d %H:%M')}")
        print(f"   💵 ${df_subset['close'].min():.4f} - ${df_subset['close'].max():.4f}")

        return df_subset

    except Exception as e:
        print(f"   ❌ Error fetching {yf_symbol}: {e}")
        return None


def run_backtest(symbol: str, df: pd.DataFrame) -> dict:
    """Run VectorBT backtest with signals from gen11-47 strategy."""

    print(f"\n{'='*70}")
    print(f"BACKTEST: {symbol}/USDT Perpetual Futures")
    print(f"{'='*70}")

    try:
        print(f"✅ Data: {len(df)} candles")
        print(f"   Period: {len(df) / 24:.1f} days")

        # Run gen11-47 strategy
        strategy = FuturesTradingStrategy(df)

        crash_prob = strategy.crash_probability
        trend_strength = strategy.trend_strength

        print(f"\n📊 STRATEGY METRICS:")
        print(f"   Crash Prob: {crash_prob.mean():.1%} avg (max {crash_prob.max():.1%})")
        print(f"   Trend Strength: {trend_strength.mean():.1%} avg (max {trend_strength.max():.1%})")

        # Get thresholds from .env or use defaults
        entry_trend = float(os.environ.get('BACKTEST_ENTRY_TREND', '0.5'))
        entry_crash = float(os.environ.get('BACKTEST_ENTRY_CRASH', '0.35'))
        exit_crash = float(os.environ.get('BACKTEST_EXIT_CRASH', '0.40'))
        exit_trend = float(os.environ.get('BACKTEST_EXIT_TREND', '0.30'))

        # Generate entry/exit signals
        entries = (trend_strength > entry_trend) & (crash_prob < entry_crash)
        exit_crash_sig = crash_prob > exit_crash
        exit_trend_sig = trend_strength < exit_trend
        exits = exit_crash_sig | exit_trend_sig

        print(f"\n📈 SIGNALS:")
        print(f"   Entry: trend > {entry_trend:.2f} AND crash < {entry_crash:.2f} → {entries.sum()} signals")
        print(f"   Exit: crash > {exit_crash:.2f} OR trend < {exit_trend:.2f} → {exits.sum()} signals")
        print(f"   Ratio: {exits.sum() / max(entries.sum(), 1):.2f}x exits per entry")

        # Run VectorBT portfolio
        price = df['close'].values
        init_cash = float(os.environ.get('BACKTEST_INIT_CASH', '10000'))
        fees = float(os.environ.get('BACKTEST_FEES', '0.001'))

        pf = vbt.Portfolio.from_signals(
            close=price,
            entries=entries.values,
            exits=exits.values,
            init_cash=init_cash,
            fees=fees,
            freq='1h'
        )

        # Extract metrics
        total_return = pf.total_return()
        annual_return = pf.annualized_return()
        sharpe_ratio = pf.sharpe_ratio()
        max_drawdown = pf.max_drawdown()

        try:
            win_rate = float(pf.trades.win_rate) if hasattr(pf.trades, 'win_rate') else 0.0
        except:
            win_rate = 0.0

        num_trades = len(pf.trades.records) if hasattr(pf.trades, 'records') else 0
        final_value = pf.final_value()

        # Buy & hold comparison
        buyhold_return = (price[-1] / price[0]) - 1
        outperformance = total_return - buyhold_return

        print(f"\n🚀 RESULTS:")
        print(f"   Strategy: {total_return:+.2%}")
        print(f"   Buy & Hold: {buyhold_return:+.2%}")
        print(f"   Outperformance: {outperformance:+.2%}")
        print(f"   Sharpe: {sharpe_ratio:.2f}")
        print(f"   Max DD: {max_drawdown:.2%}")
        print(f"   Trades: {num_trades} ({win_rate:.0%} win)")

        print(f"\n💰 P&L:")
        print(f"   Start: ${init_cash:,.0f}")
        print(f"   Final: ${final_value:,.0f}")
        print(f"   Profit: ${final_value - init_cash:+,.0f}")

        status = "✅" if outperformance > 0 else "⚠️"
        print(f"\n{status} {outperformance:+.2%} vs buy-and-hold")

        return {
            'symbol': symbol,
            'total_return': total_return,
            'annual_return': annual_return,
            'buyhold_return': buyhold_return,
            'outperformance': outperformance,
            'sharpe_ratio': sharpe_ratio,
            'max_drawdown': max_drawdown,
            'win_rate': win_rate,
            'trades': num_trades,
            'final_value': final_value,
            'profit': final_value - init_cash,
            'num_candles': len(df),
        }

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return None


def main():
    """Main entry point with CLI arguments."""

    parser = argparse.ArgumentParser(
        description="VectorBT backtest for OKX perpetual futures with fresh data",
        epilog="Examples:\n"
               "  python backtest.py BTC\n"
               "  python backtest.py TRUMP --days 7\n"
               "  python backtest.py ETH SOL XRP\n"
               "  python backtest.py BTC --fresh",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    parser.add_argument(
        'symbols',
        nargs='*',
        default=['BTC', 'ETH', 'SOL', 'XRP', 'AVAX'],
        help='Crypto symbols (default: BTC ETH SOL XRP AVAX)'
    )

    parser.add_argument(
        '--days',
        type=int,
        default=90,
        help='Days to backtest (default: 90). Min recommended: 7'
    )

    parser.add_argument(
        '--fresh',
        action='store_true',
        help='Force re-download fresh data'
    )

    parser.add_argument(
        '--init-cash',
        type=float,
        default=None,
        help='Initial capital (default: $10,000)'
    )

    args = parser.parse_args()

    # Override env if provided
    if args.init_cash:
        os.environ['BACKTEST_INIT_CASH'] = str(args.init_cash)

    print(f"\n{'#'*70}")
    print(f"VectorBT BACKTEST - OKX Perpetual Futures")
    print(f"{'#'*70}\n")

    print(f"⚙️  CONFIG:")
    print(f"   Symbols: {', '.join(args.symbols)}")
    print(f"   Period: {args.days} days")
    print(f"   Fresh data: {'Yes (re-downloading)' if args.fresh else 'Smart cache'}")
    print(f"   Init cash: ${os.environ.get('BACKTEST_INIT_CASH', '10000')}")
    print()

    all_results = []

    # Backtest each symbol
    for symbol in args.symbols:
        # Fetch data
        df = fetch_futures_data(symbol, days=args.days, force=args.fresh)

        if df is not None and len(df) > 0:
            # Run backtest
            result = run_backtest(symbol, df)
            if result:
                all_results.append(result)
        else:
            print(f"❌ Skipping {symbol} - no data")

    # Summary table
    if all_results:
        print(f"\n\n{'='*80}")
        print("SUMMARY")
        print(f"{'='*80}\n")

        results_df = pd.DataFrame(all_results).sort_values('outperformance', ascending=False)

        print(f"{'Symbol':<10} | {'Return':>10} | {'B&H':>10} | {'Out':>10} | {'Sharpe':>7} | {'Trades':>6} | {'P&L':>10}")
        print("-" * 80)

        for _, row in results_df.iterrows():
            print(f"{row['symbol']:<10} | {row['total_return']:>10.2%} | "
                  f"{row['buyhold_return']:>10.2%} | {row['outperformance']:>10.2%} | "
                  f"{row['sharpe_ratio']:>7.2f} | {row['trades']:>6.0f} | ${row['profit']:>9,.0f}")

        print("-" * 80)
        avg_out = results_df['outperformance'].mean()
        avg_profit = results_df['profit'].mean()
        print(f"{'AVERAGE':<10} | {'':<12} | {'':<12} | {avg_out:>10.2%} | {'':<9} | {'':<8} | ${avg_profit:>9,.0f}")

        print(f"\n✅ Tested {len(all_results)} symbols")
        print(f"⚡ VectorBT: Ultra-fast backtesting engine")


if __name__ == "__main__":
    main()
