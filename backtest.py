"""
Universal VectorBT backtest using REAL signals from trained strategy.
Uses actual entry/exit from initial.py with dynamic sizing and stop loss.
Fetches perpetual futures data from OKX using CCXT.

Usage:
    uv run python backtest.py BTC                    # Test BTC, 90 days
    uv run python backtest.py BTC --days 7           # Test BTC, 7 days
    uv run python backtest.py ETH SOL XRP --fresh    # Fresh data
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

from data_loader_futures import fetch_crypto_futures_data
from initial import run_experiment

# Load environment
load_dotenv()


def fetch_futures_data(symbol: str, days: int = 90, force: bool = False) -> pd.DataFrame:
    """Fetch perpetual futures data using CCXT."""

    print(f"📥 Fetching {symbol}/USDT perpetual futures data...")

    # Determine period
    if days <= 7:
        period = "1w"
    elif days <= 30:
        period = "1mo"
    elif days <= 90:
        period = "3mo"
    elif days <= 180:
        period = "6mo"
    else:
        period = "1y"

    # CCXT symbol format for perpetual futures
    ccxt_symbol = f"{symbol}/USDT:USDT"

    try:
        df = fetch_crypto_futures_data(
            symbol=ccxt_symbol,
            timeframe="1h",
            period=period,
            force_refresh=force,
            include_funding=True,
            exchange="okx"
        )

        # Set datetime as index
        if 'datetime' in df.columns:
            df['datetime'] = pd.to_datetime(df['datetime'], utc=True)
            df.set_index('datetime', inplace=True)
        else:
            df.index = pd.to_datetime(df.index, utc=True)

        # Take last N days
        cutoff_date = pd.Timestamp.now(tz='UTC') - timedelta(days=days)
        df_subset = df[df.index >= cutoff_date].copy()

        if len(df_subset) < 24:
            print(f"   ⚠️  Only {len(df_subset)} candles, using all available...")
            df_subset = df.tail(max(168, len(df)))

        print(f"   ✅ {len(df_subset)} candles ({len(df_subset) / 24:.1f} days)")
        print(f"   📅 {df_subset.index[0].strftime('%Y-%m-%d %H:%M')} → {df_subset.index[-1].strftime('%Y-%m-%d %H:%M')}")
        print(f"   💵 ${df_subset['close'].min():.4f} - ${df_subset['close'].max():.4f}")

        return df_subset

    except Exception as e:
        print(f"   ❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return None


def run_backtest(symbol: str, df: pd.DataFrame) -> dict:
    """
    Run VectorBT backtest using REAL signals from trained strategy.
    Uses actual entry/exit + stop loss + dynamic sizing from initial.py
    """

    print(f"\n{'='*70}")
    print(f"BACKTEST: {symbol}/USDT (Using REAL Trained Signals)")
    print(f"{'='*70}")

    try:
        print(f"✅ Data: {len(df)} candles ({len(df) / 24:.1f} days)")

        # Run the ACTUAL trained strategy from initial.py
        # This returns DataFrame with:
        # - entry_signal, exit_signal (from trained strategy)
        # - stop_loss_pct (dynamic ATR-based)
        # - position_size (dynamic sizing)
        # - ALL intermediate features
        print("   Running trained gen11-47 strategy...")
        result_df = run_experiment(df)

        # Extract REAL signals from trained strategy
        entries = result_df['entry_signal'].fillna(False).astype(bool)
        exits = result_df['exit_signal'].fillna(False).astype(bool)
        stop_percents = result_df['stop_loss_pct'].fillna(3.0)  # Default 3% if NaN
        position_sizes = result_df['position_size'].fillna(1.0)  # Default 1x if NaN

        print(f"\n📊 STRATEGY SIGNALS:")
        print(f"   Entry signals: {entries.sum()}")
        print(f"   Exit signals: {exits.sum()}")
        print(f"   Avg stop loss: {stop_percents.mean():.2f}%")
        print(f"   Avg position size: {position_sizes.mean():.2f}x")

        # Get config from .env
        init_cash = float(os.environ.get('BACKTEST_INIT_CASH', '10000'))
        fees = float(os.environ.get('BACKTEST_FEES', '0.001'))

        # Run VectorBT Portfolio with REAL signals + dynamic sizing + stop loss
        price = df['close'].values

        pf = vbt.Portfolio.from_signals(
            close=price,
            entries=entries.values,
            exits=exits.values,
            size=position_sizes.values,      # Dynamic sizing from strategy!
            sl_stop=stop_percents.values,    # Dynamic stop loss from strategy!
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

        # Buy & hold
        buyhold_return = (price[-1] / price[0]) - 1
        outperformance = total_return - buyhold_return

        # Check strategy features
        crash_prob = result_df['crash_probability']
        print(f"\n📈 STRATEGY FEATURES:")
        print(f"   Crash Prob: {crash_prob.mean():.1%} avg (max {crash_prob.max():.1%})")
        print(f"   Market Regime: {result_df.get('market_regime', 'N/A').mode()[0] if 'market_regime' in result_df else 'N/A'}")

        print(f"\n🚀 RESULTS:")
        print(f"   Strategy: {total_return:+.2%}")
        print(f"   Annualized: {annual_return:+.2%}")
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
        description="VectorBT backtest using REAL trained signals from gen11-47\n"
                    "Fetches perpetual futures data from OKX exchange via CCXT",
        epilog="Examples:\n"
               "  python backtest.py BTC\n"
               "  python backtest.py BTC --days 7\n"
               "  python backtest.py ETH SOL XRP --fresh",
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
        help='Days to backtest (default: 90)'
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

    if args.init_cash:
        os.environ['BACKTEST_INIT_CASH'] = str(args.init_cash)

    print(f"\n{'#'*70}")
    print(f"VectorBT BACKTEST - Using REAL Trained Signals")
    print(f"{'#'*70}\n")

    print(f"⚙️  CONFIG:")
    print(f"   Strategy: gen11-47 (from initial.py)")
    print(f"   Symbols: {', '.join(args.symbols)}")
    print(f"   Period: {args.days} days")
    print(f"   Fresh data: {'Yes' if args.fresh else 'Smart cache'}")
    print(f"   Init cash: ${os.environ.get('BACKTEST_INIT_CASH', '10000')}")
    print(f"   Features: Dynamic sizing + Stop loss + Real signals")
    print()

    all_results = []

    # Backtest each symbol
    for symbol in args.symbols:
        df = fetch_futures_data(symbol, days=args.days, force=args.fresh)

        if df is not None and len(df) > 0:
            result = run_backtest(symbol, df)
            if result:
                all_results.append(result)
        else:
            print(f"❌ Skipping {symbol} - no data")

    # Summary
    if all_results:
        print(f"\n\n{'='*80}")
        print("SUMMARY - REAL Trained Strategy Performance")
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

        print(f"\n✅ Tested {len(all_results)} symbols using REAL trained signals")
        print(f"⚡ VectorBT + gen11-47 strategy")


if __name__ == "__main__":
    main()
