"""
Initial crypto trading strategy for ShinkaEvolve using VectorBT. Gen47

This module implements a baseline trading strategy using VectorBT's built-in indicators.
The EVOLVE-BLOCK section contains the indicator parameters and signal generation logic
that Shinka will mutate to find more profitable strategies.

Strategy overview:
- Use VectorBT's optimized technical indicators (RSI, MACD, Bollinger Bands, ATR)
- Combine indicators to generate entry/exit signals
- Backtest with VectorBT's fast Portfolio engine
- Optimize for crash prediction and risk management

The goal is to evolve indicator parameters and signal combination logic to
maximize risk-adjusted returns (Sharpe ratio) during market crashes.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import vectorbt as vbt


# EVOLVE-BLOCK-START

"""
Technical Indicators and Trading Strategy using VectorBT

This section will be EVOLVED by LLM to discover profitable crash-resistant strategies.

**VECTORBT POWER**: Numba-accelerated, extremely fast, vectorized operations!

Available VectorBT Indicators (all Numba-compiled, very fast):
- vbt.RSI.run(close, window=14).rsi → Relative Strength Index
- vbt.MACD.run(close, fast_window=12, slow_window=26, signal_window=9) → .macd, .signal, .hist
- vbt.BBANDS.run(close, window=20, alpha=2) → .upper, .middle, .lower
- vbt.ATR.run(high, low, close, window=14).atr → Average True Range
- vbt.MA.run(close, window=20, ewm=True).ma → SMA (ewm=False) or EMA (ewm=True)
- vbt.STOCH.run(high, low, close) → Stochastic oscillator
- And many more! Explore VectorBT docs for full list

**KEY CONCEPTS FOR EVOLUTION:**
1. **Combine indicators** to create custom crash predictors
2. **Multi-timeframe analysis** using resample (e.g., 1H + 4H signals)
3. **Vectorized logic** - use pandas boolean operations (no loops!)
4. **Crash protection** - exit quickly when volatility spikes or momentum reverses
"""

"""
Modular Technical Indicators and Adaptive Trading Strategy using VectorBT

This redesigned approach separates concerns into modular components:
1. Market Regime Detection
2. Signal Generation Modules
3. Adaptive Risk Management
4. Crash Protection Framework

Each component can be independently evolved while maintaining system integrity.
"""


class AdaptiveTradingSystem:
    """Adaptive trading system with regime detection and crash protection."""

    def __init__(self, df: pd.DataFrame):
        self.df = df.copy()
        self.close = df['close']
        self.high = df['high']
        self.low = df['low']
        self.volume = df['volume']

        # Pre-compute all base indicators
        self._compute_base_indicators()
        self._detect_market_regime()
        self._calculate_crash_probability()

    def _compute_base_indicators(self):
        """Compute all base technical indicators."""
        # Momentum indicators
        self.rsi = vbt.RSI.run(self.close, window=14).rsi
        macd_result = vbt.MACD.run(self.close, fast_window=12, slow_window=26, signal_window=9)
        self.macd = macd_result.macd
        self.macd_signal = macd_result.signal
        self.macd_hist = macd_result.hist

        # Volatility indicators
        self.bb = vbt.BBANDS.run(self.close, window=20, alpha=2)
        self.atr = vbt.ATR.run(self.high, self.low, self.close, window=14).atr
        self.atr_short = vbt.ATR.run(self.high, self.low, self.close, window=5).atr
        self.atr_long = vbt.ATR.run(self.high, self.low, self.close, window=20).atr

        # Moving averages
        self.sma_fast = vbt.MA.run(self.close, window=20).ma
        self.sma_slow = vbt.MA.run(self.close, window=50).ma
        self.ema_trend = vbt.MA.run(self.close, window=50, ewm=True).ma

        # Volume analysis
        self.volume_ma = vbt.MA.run(self.volume, window=20).ma
        self.volume_ratio = self.volume / self.volume_ma

        # Returns and momentum physics
        self.returns = self.close.pct_change()
        self.price_velocity = self.returns.rolling(window=5).mean()
        self.price_acceleration = self.price_velocity.diff()

        # Multi-timeframe analysis
        try:
            close_4h = self.close.resample('4h').last()
            ema_4h = vbt.MA.run(close_4h, window=12, ewm=True).ma
            self.ema_4h_aligned = ema_4h.reindex(self.close.index, method='ffill')
        except:
            self.ema_4h_aligned = pd.Series(self.ema_trend.values, index=self.close.index)

    def _detect_market_regime(self):
        """Detect current market regime (trending/ranging/volatile)."""
        # Volatility regime
        self.volatility_level = self.atr / self.close  # Normalized ATR
        self.volatility_quartiles = self.volatility_level.quantile([0.25, 0.5, 0.75])

        # Trend strength using slope of long-term MA
        self.trend_slope = (self.ema_trend / self.ema_trend.shift(20)) - 1
        self.trend_strength = abs(self.trend_slope)

        # Regime classification
        high_volatility = self.volatility_level > self.volatility_quartiles[0.75]
        strong_trend = self.trend_strength > self.trend_strength.quantile(0.6)

        self.in_trend_mode = strong_trend & ~high_volatility
        self.in_range_mode = ~strong_trend & ~high_volatility
        self.in_crisis_mode = high_volatility

    def _calculate_crash_probability(self):
        """Calculate probability of imminent market crash."""
        # Enhanced volatility spike detection with dynamic thresholds
        volatility_ratio = self.atr_short / self.atr_long
        vol_spike_threshold = volatility_ratio.quantile(0.8)  # More sensitive threshold
        vol_spike = volatility_ratio > vol_spike_threshold

        # Negative acceleration with momentum confirmation
        neg_accel = self.price_acceleration < self.price_acceleration.quantile(0.15)  # Less strict threshold

        # Volume divergence with stronger confirmation
        price_up = self.close > self.close.shift(5)
        volume_down = self.volume_ratio < 0.8  # Less strict volume threshold
        vol_divergence = price_up & volume_down

        # Extreme overbought condition with RSI momentum
        extreme_rsi = (self.rsi > 70) & (self.rsi < self.rsi.shift(1))  # Lowered threshold

        # Price action confirmation - sharp drops
        recent_drop = (self.close / self.close.shift(3) - 1) < -0.005  # 0.5% drop in 3 periods

        # Weighted composite crash probability (0-1 scale)
        # Increased weight on volatility as it's most predictive
        weights = [0.4, 0.2, 0.2, 0.15, 0.05]  # Volatility, acceleration, volume, RSI, price drop
        crash_signals = [vol_spike, neg_accel, vol_divergence, extreme_rsi, recent_drop]
        self.crash_probability = sum(w * s.astype(int) for w, s in zip(weights, crash_signals))

        # Smooth the probability with a rolling mean to reduce noise
        self.crash_probability = self.crash_probability.rolling(3, min_periods=1).mean()

        # Multi-level alert system with more sensitive thresholds
        self.pre_crash_warning = self.crash_probability >= 0.2  # Earlier caution
        self.early_warning = self.crash_probability >= 0.4   # Prepare for risk reduction
        self.crisis_alert = self.crash_probability >= 0.6    # Immediate action needed

    def get_trend_signals(self) -> tuple[pd.Series, pd.Series]:
        """Generate signals optimized for trending markets."""
        # EMA crossover with confirmation
        ema_signal = (self.close > self.ema_trend) & (self.close.shift(1) <= self.ema_trend.shift(1))

        # MACD histogram expansion
        macd_bullish = (self.macd_hist > 0) & (self.macd_hist > self.macd_hist.shift(1))

        # Multi-timeframe alignment
        mtf_aligned = self.close > self.ema_4h_aligned

        # Volume confirmation
        vol_confirmed = self.volume_ratio > 1.0

        entries = ema_signal & macd_bullish & mtf_aligned & vol_confirmed
        exits = (self.close < self.ema_trend) | (self.macd_hist < 0)

        return entries, exits

    def get_mean_reversion_signals(self) -> tuple[pd.Series, pd.Series]:
        """Generate signals optimized for ranging markets."""
        # Bollinger Band mean reversion
        bb_entry = (self.close < self.bb.lower) & (self.close.shift(1) >= self.bb.lower.shift(1))
        bb_exit = (self.close > self.bb.middle)

        # RSI oversold/overbought
        rsi_entry = self.rsi < 30
        rsi_exit = self.rsi > 50

        # Volume confirmation
        vol_confirmed = self.volume_ratio > 0.8

        entries = (bb_entry | rsi_entry) & vol_confirmed
        exits = bb_exit | rsi_exit

        return entries, exits

    def get_crash_protection_signals(self) -> tuple[pd.Series, pd.Series]:
        """Generate defensive signals during high crash probability."""
        # Emergency exits during crisis
        emergency_exit = self.crisis_alert

        # Partial exits during early warning with additional confirmation
        partial_exit = self.early_warning & (~self.crisis_alert) & (self.close < self.close.shift(5))

        # Trailing stop activation during pre-crash warnings
        trailing_stop = self.pre_crash_warning & (self.close < self.close.rolling(10).max() * 0.98)

        # No new entries during warning phases
        entries = pd.Series(False, index=self.close.index)
        # Exits include all protection levels
        exits = emergency_exit | partial_exit | trailing_stop

        return entries, exits

    def generate_adaptive_signals(self) -> tuple[pd.Series, pd.Series]:
        """Generate signals based on current market regime."""
        # Get signals for each regime
        trend_entries, trend_exits = self.get_trend_signals()
        mr_entries, mr_exits = self.get_mean_reversion_signals()
        cp_entries, cp_exits = self.get_crash_protection_signals()

        # Contrarian signals during extreme fear
        extreme_fear = self.crash_probability < 0.1
        rsi_oversold = self.rsi < 25
        bb_oversold = self.close < self.bb.lower
        contrarian_entries = extreme_fear & rsi_oversold & bb_oversold
        contrarian_exits = (self.close > self.bb.middle) | (self.rsi > 50) | (self.crisis_alert)

        # Adaptive signal selection based on regime
        entries = pd.Series(False, index=self.close.index)
        exits = pd.Series(False, index=self.close.index)

        # In trending markets, favor trend following (but with crash awareness)
        trend_safe = trend_entries & ~self.early_warning  # No entries during warnings
        entries = entries | (trend_safe & self.in_trend_mode)
        exits = exits | (trend_exits & self.in_trend_mode)

        # In ranging markets, favor mean reversion (reduced during warnings)
        mr_safe = mr_entries & ~self.pre_crash_warning  # Reduced sensitivity
        entries = entries | (mr_safe & self.in_range_mode)
        exits = exits | (mr_exits & self.in_range_mode)

        # Add contrarian entries during any regime when extreme fear is detected
        entries = entries | contrarian_entries

        # Add contrarian exits
        exits = exits | (contrarian_exits & contrarian_entries)

        # In crisis mode, activate crash protection
        entries = entries | (cp_entries & self.in_crisis_mode)
        exits = exits | (cp_exits & self.in_crisis_mode)

        # Universal crash protection overrides
        exits = exits | self.crisis_alert  # Always exit during crisis

        return entries, exits


def generate_signals(df: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    """
    Generate adaptive trading signals using regime detection and crash protection.

    This modular approach separates concerns and allows independent evolution of:
    - Market regime detection
    - Signal generation for different market conditions
    - Crash probability calculation
    - Risk management logic

    Args:
        df: DataFrame with OHLCV data (columns: open, high, low, close, volume)
            Index must be DatetimeIndex (required by VectorBT)

    Returns:
        entries: Boolean Series indicating buy signals
        exits: Boolean Series indicating sell signals
    """
    # Ensure datetime index for VectorBT
    if not isinstance(df.index, pd.DatetimeIndex):
        if 'datetime' in df.columns:
            df = df.set_index('datetime', drop=False)
        else:
            raise ValueError("DataFrame must have DatetimeIndex or 'datetime' column for VectorBT")

    # Initialize adaptive trading system
    system = AdaptiveTradingSystem(df)

    # Generate adaptive signals
    entries, exits = system.generate_adaptive_signals()

    # Fill NaN values (from indicator warm-up periods) with False
    entries = entries.fillna(False)
    exits = exits.fillna(False)

    return entries, exits


def run_experiment(val_df: pd.DataFrame) -> pd.DataFrame:
    """
    Run the adaptive crypto trading experiment using VectorBT.

    This function implements dynamic position sizing based on market confidence
    and enhanced risk management through regime awareness.

    Args:
        val_df: Validation DataFrame with OHLCV data

    Returns:
        DataFrame with backtest results including signals, positions, portfolio values, etc.
    """
    # Generate entry/exit signals
    entries, exits = generate_signals(val_df)

    # Initialize adaptive trading system for additional metrics
    system = AdaptiveTradingSystem(val_df)

    # Dynamic position sizing based on regime, confidence, and crash probability
    # Higher confidence = larger positions, crisis mode = minimal positions
    size_multiplier = pd.Series(1.0, index=val_df.index)

    # Base position sizing by regime
    size_multiplier[system.in_trend_mode] = 0.7  # Reduced positions in trends for safety
    size_multiplier[system.in_range_mode] = 0.4  # Smaller positions in ranges
    size_multiplier[system.in_crisis_mode] = 0.05  # Minimal positions in crisis

    # Further reduce position size during warning phases
    size_multiplier[system.early_warning & ~system.in_crisis_mode] = 0.2
    size_multiplier[system.pre_crash_warning & ~system.early_warning] = 0.5

    # Add an even more conservative setting for high risk situations
    high_risk = system.crash_probability >= 0.3
    size_multiplier[high_risk & ~system.early_warning & ~system.in_crisis_mode] = 0.3

    # Invert position sizing based on crash probability for contrarian opportunities
    # During extreme fear, allow slightly larger positions if other factors align
    extreme_fear = system.crash_probability < 0.1
    size_multiplier[extreme_fear & system.in_range_mode] = 0.6  # Slightly more during extreme oversolds

    # Proactive position reduction based on crash probability
    # Linear reduction from 0.3 crash probability (90% position) to 0.6 crash probability (10% position)
    medium_risk = (system.crash_probability >= 0.3) & (system.crash_probability < 0.6)
    risk_factor = 1 - ((system.crash_probability[medium_risk] - 0.3) / 0.3)  # Scale from 1 to 0
    size_multiplier[medium_risk] = size_multiplier[medium_risk] * (0.1 + 0.8 * risk_factor)  # Scale from 0.1 to 0.9

    # Volatility scaling - inverse relationship between position size and volatility
    # Normalize ATR to create a volatility factor between 0.5 and 2.0
    normalized_atr = (system.atr - system.atr.min()) / (system.atr.max() - system.atr.min())
    volatility_factor = 1.5 - normalized_atr  # Higher ATR = lower factor
    volatility_factor = volatility_factor.clip(0.5, 2.0)  # Bound between 0.5 and 2.0

    # Apply volatility scaling to size multipliers
    size_multiplier = size_multiplier * volatility_factor

    # Ensure size multipliers don't exceed reasonable bounds
    size_multiplier = size_multiplier.clip(0.05, 1.0)

    # Dynamic trailing stop adjustment based on crash probability
    # When crash probability is high, tighten trailing stops
    high_crash_prob = system.crash_probability >= 0.4
    if high_crash_prob.any():
        # Reduce trailing stop distance from 2% to 1% when crash probability is high
        tight_trailing_stops = high_crash_prob & (system.close < system.close.rolling(10).max() * 0.99)
        exits = exits | tight_trailing_stops

    # Run VectorBT backtest with dynamic sizing
    portfolio = vbt.Portfolio.from_signals(
        close=val_df['close'],
        entries=entries,
        exits=exits,
        size=size_multiplier,
        init_cash=10000.0,
        fees=0.001,  # 0.1% commission
        freq='1h',   # Hourly data
    )

    # Extract results for compatibility with evaluator
    result_df = val_df.copy()

    # Add signals to dataframe
    result_df['entry_signal'] = entries.astype(float)
    result_df['exit_signal'] = exits.astype(float)

    # Create combined signal column (required by evaluator)
    # 1.0 = buy, -1.0 = sell, 0.0 = hold
    result_df['signal'] = 0.0
    result_df.loc[entries, 'signal'] = 1.0
    result_df.loc[exits, 'signal'] = -1.0

    # Add portfolio metrics (VectorBT methods need () to call)
    result_df['position'] = portfolio.position_mask().astype(float)
    result_df['portfolio_value'] = portfolio.value()
    result_df['cash'] = portfolio.cash()

    # Calculate returns
    result_df['returns'] = portfolio.returns()

    # Store metrics in attrs (not Portfolio object - it's not JSON serializable)
    result_df.attrs['total_return'] = portfolio.total_return()
    result_df.attrs['sharpe_ratio'] = portfolio.sharpe_ratio()
    result_df.attrs['max_drawdown'] = portfolio.max_drawdown()

    return result_df


# EVOLVE-BLOCK-END


# Example standalone usage (not used during evolution)
if __name__ == "__main__":
    print("This module is designed to be used with the ShinkaEvolve evaluator.")
    print("Run: python evaluate.py --program_path initial.py")