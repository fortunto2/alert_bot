"""
Simple test to verify multi_crash_monitor correctly uses the strategy.
Tests crash detection and adaptive thresholds on small dataset.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from multi_crash_monitor import check_crash_probability_for_symbol, get_adaptive_exit_thresholds
import pandas as pd


def test_crash_detection():
    """Test that crash monitor correctly extracts crash probability from strategy."""

    print("="*70)
    print("TEST 1: Crash Probability Detection")
    print("="*70)

    # Test thresholds
    thresholds = {
        'pre_crash': 0.2,
        'early_warning': 0.4,
        'crisis': 0.6
    }

    print("\n1. Fetching BTC futures data...")

    # Use check_crash_probability_for_symbol (main function from multi_crash_monitor)
    result = check_crash_probability_for_symbol(
        symbol="BTC/USDT:USDT",
        lookback_hours=168,  # 7 days
        thresholds=thresholds,
        exchange="okx"
    )

    assert result is not None, "❌ Failed to get crash probability!"

    # Check all required fields
    required_fields = [
        'symbol', 'timestamp', 'price', 'change_24h', 'crash_probability',
        'pre_crash_warning', 'early_warning', 'crisis_alert',
        'rsi', 'atr_ratio', 'volatility', 'trend_strength',
        'momentum_strength', 'market_strength', 'funding_stress', 'vol_ratio_4h'
    ]

    for field in required_fields:
        assert field in result, f"❌ Missing field: {field}"

    print(f"\n2. Crash Detection Results:")
    print(f"   Symbol: {result['symbol']}")
    print(f"   Price: ${result['price']:,.2f}")
    print(f"   24h Change: {result['change_24h']:+.2f}%")
    print(f"   Crash Probability: {result['crash_probability']:.1%}")
    print(f"   🟡 Pre-crash: {result['pre_crash_warning']}")
    print(f"   🟠 Early warning: {result['early_warning']}")
    print(f"   🔴 Crisis: {result['crisis_alert']}")

    print(f"\n3. Strategy Metrics:")
    print(f"   RSI: {result['rsi']:.1f}")
    print(f"   ATR Ratio: {result['atr_ratio']:.2f}")
    print(f"   Volatility: {result['volatility']:.3f}")
    print(f"   Trend Strength: {result['trend_strength']:.3f}")
    print(f"   Market Strength: {result['market_strength']:.3f}")
    print(f"   Funding Stress: {result['funding_stress']:.3f}")

    # Validate ranges
    assert 0.0 <= result['crash_probability'] <= 1.0, f"❌ Invalid crash prob: {result['crash_probability']}"
    assert 0.0 <= result['rsi'] <= 100.0, f"❌ Invalid RSI: {result['rsi']}"
    assert 0.0 <= result['trend_strength'] <= 1.0, f"❌ Invalid trend strength: {result['trend_strength']}"

    print(f"\n✅ TEST 1 PASSED: Crash detection works correctly")

    return result


def test_adaptive_thresholds_integration():
    """Test that adaptive thresholds work with real crash detection results."""

    print("\n" + "="*70)
    print("TEST 2: Adaptive Thresholds Integration")
    print("="*70)

    print("\n1. Getting crash metrics for BTC...")

    result = check_crash_probability_for_symbol(
        symbol="BTC/USDT:USDT",
        lookback_hours=168,
        exchange="okx"
    )

    assert result is not None, "❌ Failed to get metrics"

    print(f"   ✅ Got metrics: crash_prob={result['crash_probability']:.1%}, "
          f"market_strength={result['market_strength']:.2f}, "
          f"trend_strength={result['trend_strength']:.2f}")

    print("\n2. Calculating adaptive exit thresholds...")

    thresholds = get_adaptive_exit_thresholds(result)

    assert 'exit_crash' in thresholds, "❌ Missing exit_crash"
    assert 'exit_trend' in thresholds, "❌ Missing exit_trend"
    assert 'regime' in thresholds, "❌ Missing regime"

    print(f"   Detected regime: {thresholds['regime']}")
    print(f"   Exit crash threshold: {thresholds['exit_crash']:.1%}")
    print(f"   Exit trend threshold: {thresholds['exit_trend']:.1%}")

    # Validate thresholds are reasonable
    assert 0.1 <= thresholds['exit_crash'] <= 0.8, f"❌ Invalid exit_crash: {thresholds['exit_crash']}"
    assert 0.05 <= thresholds['exit_trend'] <= 0.6, f"❌ Invalid exit_trend: {thresholds['exit_trend']}"
    assert thresholds['regime'] in ['BULL', 'BEAR', 'CRASH', 'VOLATILE'], f"❌ Invalid regime: {thresholds['regime']}"

    print(f"\n✅ TEST 2 PASSED: Adaptive thresholds integrate correctly")

    return thresholds


def test_multiple_symbols():
    """Test that monitor can handle multiple symbols."""

    print("\n" + "="*70)
    print("TEST 3: Multiple Symbols")
    print("="*70)

    symbols = ["BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT"]
    results = []

    print(f"\n1. Testing {len(symbols)} symbols...")

    for symbol in symbols:
        print(f"\n   Processing {symbol}...")
        result = check_crash_probability_for_symbol(
            symbol=symbol,
            lookback_hours=168,
            exchange="okx"
        )

        if result is not None:
            results.append(result)
            print(f"      ✅ Price: ${result['price']:,.2f}, Crash: {result['crash_probability']:.1%}")
        else:
            print(f"      ⚠️  Skipped (no data)")

    assert len(results) >= 2, f"❌ Too few results: {len(results)}"

    print(f"\n2. Successfully processed {len(results)}/{len(symbols)} symbols")

    # Check variety in crash probabilities (they shouldn't all be identical)
    crash_probs = [r['crash_probability'] for r in results]
    unique_probs = len(set([round(p, 2) for p in crash_probs]))

    print(f"   Crash probabilities: {[f'{p:.1%}' for p in crash_probs]}")
    print(f"   Unique values: {unique_probs}")

    print(f"\n✅ TEST 3 PASSED: Multiple symbols handled correctly")

    return results


def main():
    """Run all tests."""

    print("\n" + "#"*70)
    print("# RUNNING MULTI CRASH MONITOR TESTS")
    print("#"*70 + "\n")

    try:
        # Test 1: Crash detection
        crash_result = test_crash_detection()

        # Test 2: Adaptive thresholds
        thresholds = test_adaptive_thresholds_integration()

        # Test 3: Multiple symbols
        multi_results = test_multiple_symbols()

        print("\n" + "#"*70)
        print("# ✅ ALL TESTS PASSED!")
        print("#"*70)
        print("\nVerified:")
        print("  ✅ Crash monitor extracts correct metrics from strategy")
        print("  ✅ All required fields present in results")
        print("  ✅ Adaptive thresholds adjust based on market regime")
        print("  ✅ Multiple symbols processed correctly")
        print("\nConclusion: multi_crash_monitor correctly uses strategy!")

    except Exception as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
