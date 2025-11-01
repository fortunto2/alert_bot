"""
Initial crypto trading strategy for ShinkaEvolve using VectorBT with Futures.

Based on gen11-47 best strategy, adapted for futures with funding_rate.
Returns unified DataFrame with ALL features (inputs + intermediates + outputs).

Strategy overview:
- Use VectorBT's optimized technical indicators (RSI, MACD, Bollinger Bands, ATR)
- Add funding_rate analysis for futures sentiment
- Combine indicators to generate entry/exit signals
- Backtest with VectorBT's fast Portfolio engine
- Optimize for crash prediction and risk management
- Output complete feature DataFrame for Shinka to evolve

Key innovation: Unified feature DataFrame allows Shinka to:
- See all intermediate calculations
- Add new derived features
- Discover which features correlate with performance
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import vectorbt as vbt


# EVOLVE-BLOCK-START

class FuturesTradingStrategy:
    """
    Futures trading strategy focused on funding momentum and volatility regime transitions.
    """

    def __init__(self, df: pd.DataFrame):
        self.df = df.copy()
        self.close = df['close']
        self.high = df['high']
        self.low = df['low']
        self.volume = df['volume']

        # Funding rate (futures-specific)
        if 'funding_rate' in df.columns:
            self.funding_rate = df['funding_rate'].fillna(0)
        else:
            self.funding_rate = pd.Series(0, index=df.index)

        # Pre-compute all indicators and store in feature_df
        self.feature_df = pd.DataFrame(index=df.index)
        self._compute_base_indicators()
        self._compute_advanced_funding_features()
        self._detect_volatility_regimes()
        self._compute_crash_detection_indicators()
        self._calculate_market_state_classification()

    def _compute_base_indicators(self):
        """Compute core technical indicators with focus on momentum and volatility."""
        # RSI with multiple timeframes for confirmation
        rsi_result = vbt.RSI.run(self.close, window=14)
        self.rsi = rsi_result.rsi
        self.feature_df['rsi'] = self.rsi

        # Short-term RSI for quick signals
        rsi_fast_result = vbt.RSI.run(self.close, window=9)
        self.rsi_fast = rsi_fast_result.rsi
        self.feature_df['rsi_fast'] = self.rsi_fast

        # MACD for trend confirmation
        macd_result = vbt.MACD.run(self.close, fast_window=12, slow_window=26, signal_window=9)
        self.macd = macd_result.macd
        self.macd_signal = macd_result.signal
        self.macd_hist = macd_result.hist
        self.feature_df['macd'] = self.macd
        self.feature_df['macd_signal'] = self.macd_signal
        self.feature_df['macd_hist'] = self.macd_hist

        # Bollinger Bands with dynamic width for volatility tracking
        bb_result = vbt.BBANDS.run(self.close, window=20, alpha=2.0)
        self.bb_upper = bb_result.upper
        self.bb_middle = bb_result.middle
        self.bb_lower = bb_result.lower
        self.feature_df['bb_upper'] = self.bb_upper
        self.feature_df['bb_middle'] = self.bb_middle
        self.feature_df['bb_lower'] = self.bb_lower
        self.feature_df['bb_position'] = (self.close - self.bb_lower) / (self.bb_upper - self.bb_lower)

        # Bollinger Band Width as volatility indicator
        self.bb_width = (self.bb_upper - self.bb_lower) / self.bb_middle
        self.feature_df['bb_width'] = self.bb_width

        # ATR for volatility measurement
        atr_result = vbt.ATR.run(self.high, self.low, self.close, window=14)
        self.atr = atr_result.atr
        self.feature_df['atr'] = self.atr

        # Normalized ATR for regime detection
        self.norm_atr = self.atr / self.close
        self.feature_df['norm_atr'] = self.norm_atr

        # Moving averages for trend identification
        ema_fast = vbt.MA.run(self.close, window=9, ewm=True)
        ema_medium = vbt.MA.run(self.close, window=21, ewm=True)
        ema_slow = vbt.MA.run(self.close, window=50, ewm=True)
        self.ema_fast = ema_fast.ma
        self.ema_medium = ema_medium.ma
        self.ema_slow = ema_slow.ma
        self.feature_df['ema_fast'] = self.ema_fast
        self.feature_df['ema_medium'] = self.ema_medium
        self.feature_df['ema_slow'] = self.ema_slow

        # Volume analysis
        volume_ma = vbt.MA.run(self.volume, window=20)
        self.volume_ma = volume_ma.ma
        self.volume_ratio = self.volume / self.volume_ma
        self.feature_df['volume_ma'] = self.volume_ma
        self.feature_df['volume_ratio'] = self.volume_ratio

        # Price momentum and returns with acceleration slope for crash detection
        self.returns = self.close.pct_change()
        self.price_velocity = self.returns.rolling(window=3).mean()
        self.price_acceleration = self.price_velocity.diff()
        # Additional feature: acceleration slope over 3 periods
        self.price_accel_slope = self.price_acceleration.rolling(window=3).mean()
        self.feature_df['returns'] = self.returns
        self.feature_df['price_velocity'] = self.price_velocity
        self.feature_df['price_acceleration'] = self.price_acceleration
        self.feature_df['price_accel_slope'] = self.price_accel_slope

        # 4-hour trend confirmation
        try:
            close_4h = self.close.resample('4h').last()
            ema_4h_fast = vbt.MA.run(close_4h, window=9, ewm=True).ma
            ema_4h_slow = vbt.MA.run(close_4h, window=21, ewm=True).ma
            self.mtf_trend = ema_4h_fast > ema_4h_slow
            self.mtf_trend_aligned = self.mtf_trend.reindex(self.close.index, method='ffill')
        except:
            self.mtf_trend_aligned = pd.Series(True, index=self.close.index)
        self.feature_df['mtf_trend_aligned'] = self.mtf_trend_aligned.astype(int)

    def _compute_advanced_funding_features(self):
        """Compute advanced funding rate features including momentum and divergence."""
        # Basic funding statistics
        self.funding_ma_short = self.funding_rate.rolling(8).mean()
        self.funding_ma_long = self.funding_rate.rolling(24).mean()
        self.funding_std = self.funding_rate.rolling(24).std()

        self.feature_df['funding_rate'] = self.funding_rate
        self.feature_df['funding_ma_short'] = self.funding_ma_short
        self.feature_df['funding_ma_long'] = self.funding_ma_long
        self.feature_df['funding_std'] = self.funding_std

        # Funding momentum (rate of change)
        self.funding_momentum = self.funding_rate.diff(8)
        self.feature_df['funding_momentum'] = self.funding_momentum

        # New feature: funding momentum smoothed with 5-period EMA for early warnings
        self.funding_momentum_8h = vbt.MA.run(self.funding_momentum, window=5, ewm=True).ma
        self.feature_df['funding_momentum_8h'] = self.funding_momentum_8h

        # Funding acceleration
        self.funding_acceleration = self.funding_momentum.diff()
        self.feature_df['funding_acceleration'] = self.funding_acceleration

        # NEW: Early warning signal - rapidly rising funding acceleration (top 5%)
        self.funding_acceleration_rising = self.funding_acceleration > self.funding_acceleration.rolling(24).quantile(0.95)
        self.feature_df['funding_acceleration_rising'] = self.funding_acceleration_rising.astype(int)

        # NEW: Funding velocity (1st derivative smoothed) for trend detection
        self.funding_velocity = vbt.MA.run(self.funding_momentum, window=3, ewm=True).ma
        self.feature_df['funding_velocity'] = self.funding_velocity

        # NEW: Cross-timeframe funding stress detection
        self.funding_stress_4h = self.funding_rate.rolling(4).mean() - self.funding_rate.rolling(24).mean()
        self.funding_stress_8h = self.funding_rate.rolling(8).mean() - self.funding_rate.rolling(24).mean()
        self.cross_timeframe_funding_divergence = (self.funding_stress_4h > 0) & (self.funding_stress_8h > 0)
        self.feature_df['funding_stress_4h'] = self.funding_stress_4h
        self.feature_df['funding_stress_8h'] = self.funding_stress_8h
        self.feature_df['cross_timeframe_funding_divergence'] = self.cross_timeframe_funding_divergence.astype(int)

        # Funding jerk (3rd derivative) - extreme stress detection
        self.funding_jerk = self.funding_acceleration.diff()
        self.feature_df['funding_jerk'] = self.funding_jerk
        self.feature_df['funding_stress_spike'] = ((self.funding_acceleration < -0.00001) & (self.funding_jerk < 0)).astype(int)

        # Funding divergence signals
        price_higher_high = self.close > self.close.shift(8)
        funding_lower_high = self.funding_rate < self.funding_rate.shift(8)
        self.funding_bearish_divergence = price_higher_high & funding_lower_high

        price_lower_low = self.close < self.close.shift(8)
        funding_higher_low = self.funding_rate > self.funding_rate.shift(8)
        self.funding_bullish_divergence = price_lower_low & funding_higher_low

        self.feature_df['funding_bearish_divergence'] = self.funding_bearish_divergence.astype(int)
        self.feature_df['funding_bullish_divergence'] = self.funding_bullish_divergence.astype(int)

        # Extreme funding conditions
        self.funding_extreme_positive = self.funding_rate > 0.00015
        self.funding_extreme_negative = self.funding_rate < -0.00015
        self.funding_turned_negative = (self.funding_rate < 0) & (self.funding_rate.shift(1) >= 0)
        self.funding_turned_positive = (self.funding_rate > 0) & (self.funding_rate.shift(1) <= 0)

        self.feature_df['funding_extreme_positive'] = self.funding_extreme_positive.astype(int)
        self.feature_df['funding_extreme_negative'] = self.funding_extreme_negative.astype(int)
        self.feature_df['funding_turned_negative'] = self.funding_turned_negative.astype(int)
        self.feature_df['funding_turned_positive'] = self.funding_turned_positive.astype(int)

    def _detect_volatility_regimes(self):
        """Detect volatility regimes based on BB width and ATR changes."""
        # Volatility percentile ranks for regime detection
        vol_window = 50
        self.vol_low_threshold = self.norm_atr.rolling(vol_window).quantile(0.25)
        self.vol_high_threshold = self.norm_atr.rolling(vol_window).quantile(0.75)

        self.feature_df['vol_low_threshold'] = self.vol_low_threshold
        self.feature_df['vol_high_threshold'] = self.vol_high_threshold

        # Volatility regime flags
        self.low_volatility = self.norm_atr < self.vol_low_threshold
        self.high_volatility = self.norm_atr >= self.vol_high_threshold
        self.med_volatility = ~(self.low_volatility | self.high_volatility)

        self.feature_df['low_volatility'] = self.low_volatility.astype(int)
        self.feature_df['high_volatility'] = self.high_volatility.astype(int)
        self.feature_df['med_volatility'] = self.med_volatility.astype(int)

        # Volatility regime transitions
        self.vol_expanding = self.bb_width > self.bb_width.shift(5)
        self.vol_contracting = self.bb_width < self.bb_width.shift(5)

        self.feature_df['vol_expanding'] = self.vol_expanding.astype(int)
        self.feature_df['vol_contracting'] = self.vol_contracting.astype(int)

        # Volatility squeeze detection
        self.vol_squeeze = self.bb_width < self.bb_width.rolling(25).quantile(0.2)
        self.feature_df['vol_squeeze'] = self.vol_squeeze.astype(int)

        # Multi-timeframe volatility ratio - crash acceleration detection
        self.atr_1h = self.atr
        self.atr_4h = self.atr.rolling(4).mean()
        self.atr_24h = self.atr.rolling(24).mean()
        self.vol_ratio_4h = self.atr_1h / (self.atr_4h + 1e-8)
        self.vol_ratio_24h = self.atr_1h / (self.atr_24h + 1e-8)
        self.vol_cascade = (self.vol_ratio_4h > 1.1) & (self.vol_ratio_24h > 1.3)

        self.feature_df['vol_ratio_4h'] = self.vol_ratio_4h
        self.feature_df['vol_ratio_24h'] = self.vol_ratio_24h
        self.feature_df['vol_cascade'] = self.vol_cascade.astype(int)

    def _compute_crash_detection_indicators(self):
        """Compute advanced crash detection indicators based on feature correlation analysis."""
        # 1. ADX - Trend Exhaustion Detection (manual implementation)
        # Detects when strong trends are weakening (ADX declining from high = crash risk)
        window = 14

        # Calculate directional movement
        high_diff = self.high.diff()
        low_diff = -self.low.diff()

        plus_dm = pd.Series(np.where((high_diff > low_diff) & (high_diff > 0), high_diff, 0), index=self.close.index)
        minus_dm = pd.Series(np.where((low_diff > high_diff) & (low_diff > 0), low_diff, 0), index=self.close.index)

        # Calculate smoothed directional indicators using ATR
        plus_di = 100 * (plus_dm.rolling(window).mean() / self.atr)
        minus_di = 100 * (minus_dm.rolling(window).mean() / self.atr)

        # Calculate DX and ADX
        dx = 100 * np.abs(plus_di - minus_di) / (plus_di + minus_di + 1e-10)
        self.adx = dx.rolling(window).mean()
        self.adx_declining = self.adx < self.adx.shift(3)
        self.trend_exhaustion = (self.adx > 40) & self.adx_declining

        self.feature_df['adx'] = self.adx
        self.feature_df['plus_di'] = plus_di
        self.feature_df['minus_di'] = minus_di
        self.feature_df['adx_declining'] = self.adx_declining.astype(int)
        self.feature_df['trend_exhaustion'] = self.trend_exhaustion.astype(int)

        # 2. Stochastic Oscillator - Momentum Divergence
        # Detects overbought + bearish divergence (price higher, stoch lower)
        stoch_result = vbt.STOCH.run(self.high, self.low, self.close, k_window=14, d_window=3)
        self.stoch_k = stoch_result.percent_k
        self.stoch_d = stoch_result.percent_d
        self.stoch_overbought = self.stoch_k > 80
        self.stoch_bearish_div = (self.close > self.close.shift(24)) & (self.stoch_k < self.stoch_k.shift(24))

        self.feature_df['stoch_k'] = self.stoch_k
        self.feature_df['stoch_d'] = self.stoch_d
        self.feature_df['stoch_overbought'] = self.stoch_overbought.astype(int)
        self.feature_df['stoch_bearish_div'] = self.stoch_bearish_div.astype(int)

        # 3. OBV - Volume Divergence Detection
        # Price rising but OBV falling = weak rally, crash imminent
        obv_result = vbt.OBV.run(self.close, self.volume)
        self.obv = obv_result.obv
        self.obv_ma = self.obv.rolling(20).mean()
        self.obv_divergence = (self.close > self.close.shift(24)) & (self.obv < self.obv.shift(24))

        self.feature_df['obv'] = self.obv
        self.feature_df['obv_ma'] = self.obv_ma
        self.feature_df['obv_divergence'] = self.obv_divergence.astype(int)

        # 4. Price-Volume Correlation - Distribution Phase Detection
        # Rolling correlation turning negative = distribution (smart money selling)
        window = 20
        price_returns = self.close.pct_change()
        volume_changes = self.volume.pct_change()
        self.price_vol_corr = price_returns.rolling(window).corr(volume_changes)
        self.distribution_phase = self.price_vol_corr < -0.3
        self.distribution_strengthening = self.price_vol_corr < self.price_vol_corr.shift(5)

        self.feature_df['price_vol_corr'] = self.price_vol_corr
        self.feature_df['distribution_phase'] = self.distribution_phase.astype(int)
        self.feature_df['distribution_strengthening'] = self.distribution_strengthening.astype(int)

    def _calculate_market_state_classification(self):
        """Classify market state based on multiple factors for adaptive signal generation."""
        # Trend strength based on EMA alignment
        ema_alignment = ((self.ema_fast > self.ema_medium) & (self.ema_medium > self.ema_slow)).astype(int)
        ema_alignment += ((self.ema_fast > self.ema_slow) & (self.ema_medium > self.ema_slow)).astype(int) * 0.5
        self.trend_strength = ema_alignment / 1.5
        self.feature_df['trend_strength'] = self.trend_strength

        # Momentum strength
        self.momentum_strength = np.clip(self.price_velocity * 25, 0, 1)
        self.feature_df['momentum_strength'] = self.momentum_strength

        # Volume confirmation
        volume_confirmation = (self.volume_ratio > 1.0).rolling(3).mean()
        self.volume_strength = volume_confirmation.fillna(0.5)
        self.feature_df['volume_strength'] = self.volume_strength

        # Composite strength score
        self.market_strength = (
            0.4 * self.trend_strength +
            0.4 * self.momentum_strength +
            0.2 * self.volume_strength
        ).clip(0, 1)
        self.feature_df['market_strength'] = self.market_strength

        # Enhanced crash probability with volatility cascade and funding jerk
        # Volatility cascade detection with multi-timescale acceleration
        vol_cascade_1h = self.norm_atr > self.norm_atr.rolling(20).quantile(0.8)
        vol_expansion_4h = (self.vol_ratio_4h > 1.2) & (self.vol_ratio_24h > 1.4)
        vol_cascade_factor = (vol_cascade_1h | vol_expansion_4h).astype(int) * 0.25

        # Negative momentum acceleration with slope confirmation
        neg_momentum = (self.price_acceleration < self.price_acceleration.rolling(20).quantile(0.1)) | (self.price_accel_slope < -0.0005)
        neg_momentum_factor = neg_momentum.astype(int) * 0.2

        # Volume divergence
        volume_div = (self.close > self.close.shift(5)) & (self.volume_ratio < 0.8)
        volume_div_factor = volume_div.astype(int) * 0.15

        # Trend exhaustion
        price_extreme = (self.close / self.ema_slow - 1).abs() > 0.05
        momentum_slowing = self.price_velocity < self.price_velocity.rolling(5).mean() * 0.7
        trend_exhaustion = price_extreme & momentum_slowing
        trend_exhaustion_factor = trend_exhaustion.astype(int) * 0.2

        # Funding stress indicators including jerk spikes
        funding_stress_signal = self.funding_extreme_positive | self.funding_turned_negative | (self.funding_jerk < -0.00001)
        funding_stress_factor = funding_stress_signal.astype(int) * 0.2

        # NEW: Enhanced funding analysis factors
        funding_velocity_factor = (self.funding_velocity > self.funding_velocity.rolling(20).quantile(0.9)).astype(int) * 0.1
        cross_timeframe_funding_factor = self.cross_timeframe_funding_divergence.astype(int) * 0.1

        # Composite crash probability (0-1) with adaptive smoothing
        crash_factors = [
            vol_cascade_factor,                  # 0.25
            neg_momentum_factor,                 # 0.2
            volume_div_factor,                   # 0.15
            trend_exhaustion_factor,             # 0.2
            funding_stress_factor,               # 0.2
            # NEW: Early warning signal based on funding acceleration
            self.funding_acceleration_rising.astype(int) * 0.1,  # 0.1
            # NEW: Enhanced funding factors
            funding_velocity_factor,             # 0.1
            cross_timeframe_funding_factor       # 0.1
        ]
        raw_prob = sum(crash_factors).clip(0, 1)
        # Reduced smoothing window to 4 hours from 6 for even more responsive signals
        self.crash_probability = raw_prob.rolling(4).mean().fillna(0)
        self.feature_df['crash_probability'] = self.crash_probability

        # NEW: Enhanced crash phase detection for multi-stage shorting
        self.early_crash_warning = (self.crash_probability > 0.3) & (self.crash_probability <= 0.5)
        self.mid_crash_phase = (self.crash_probability > 0.5) & (self.crash_probability <= 0.7)
        self.late_crash_phase = self.crash_probability > 0.7
        self.feature_df['early_crash_warning'] = self.early_crash_warning.astype(int)
        self.feature_df['mid_crash_phase'] = self.mid_crash_phase.astype(int)
        self.feature_df['late_crash_phase'] = self.late_crash_phase.astype(int)

        # Risk levels
        self.high_risk = self.crash_probability > 0.6
        self.med_risk = (self.crash_probability > 0.3) & (self.crash_probability <= 0.6)
        self.low_risk = self.crash_probability <= 0.3
        self.feature_df['high_risk'] = self.high_risk.astype(int)
        self.feature_df['med_risk'] = self.med_risk.astype(int)
        self.feature_df['low_risk'] = self.low_risk.astype(int)

        # Funding stress indicator with enhanced sensitivity
        funding_stress = pd.Series(0.0, index=self.close.index)
        funding_stress[self.funding_extreme_positive] = 0.9
        funding_stress[self.funding_extreme_negative] = -0.7
        funding_stress[(self.funding_momentum > 0) & (self.funding_rate > 0.00005)] = 0.5
        funding_stress[(self.funding_momentum < 0) & (self.funding_rate < -0.00005)] = -0.4
        funding_stress[(self.funding_turned_negative)] = 0.7
        funding_stress[(self.funding_turned_positive)] = -0.5
        self.funding_stress = funding_stress
        self.feature_df['funding_stress'] = self.funding_stress

        # Market regime classification with crash awareness
        self.bull_market = (self.market_strength > 0.5) & (self.trend_strength > 0.4) & (~self.high_risk)
        self.bear_market = (self.market_strength < 0.3) & (self.momentum_strength < 0.2) & (~self.high_risk)
        self.consolidation = ~self.bull_market & ~self.bear_market & (~self.high_risk)
        self.crash_mode = self.high_risk  # Dedicated crash mode

        self.feature_df['bull_market'] = self.bull_market.astype(int)
        self.feature_df['bear_market'] = self.bear_market.astype(int)
        self.feature_df['consolidation'] = self.consolidation.astype(int)
        self.feature_df['crash_mode'] = self.crash_mode.astype(int)

    def get_adaptive_long_signals(self) -> tuple[pd.Series, pd.Series]:
        """Generate adaptive long entry/exit signals based on market regime."""
        # Base long entry conditions with enhanced filtering
        # Dynamic RSI upper threshold based on market strength (60-70 range)
        dynamic_rsi_upper = 60 + (self.market_strength * 10).clip(0, 10)

        base_long_entry = (
            (self.rsi < dynamic_rsi_upper) &
            (self.rsi > self.rsi.shift(1)) &
            (self.macd_hist > 0) &
            (self.macd_hist > self.macd_hist.shift(1)) &
            (self.volume_ratio > 0.75) &  # Slightly relaxed threshold
            (self.close > self.ema_medium) &  # Price above medium EMA for trend confirmation
            ~self.high_risk  # Don't enter during high risk
        )

        # Bull market aggressive entry with crash protection
        bull_entry = (
            self.bull_market &
            base_long_entry &
            self.mtf_trend_aligned &
            ~self.funding_extreme_positive &
            (self.funding_momentum >= 0) &
            ~self.crash_mode
        )

        # Consolidation mean reversion entry with risk adjustment
        consolidation_entry = (
            self.consolidation &
            (self.close < self.bb_middle) &
            (self.close > self.bb_lower) &
            (self.rsi < 40) &
            (self.rsi > self.rsi.shift(1)) &
            self.vol_contracting &
            (self.volume_ratio > 1.0) &
            ~self.high_risk
        )

        # Funding divergence entry (contrarian) with safety filters
        funding_div_entry = (
            self.funding_bullish_divergence &
            (self.rsi < 45) &
            (self.close < self.ema_medium) &
            (self.funding_rate < 0) &
            (self.volume_ratio > 0.9) &
            ~self.high_risk &
            (self.crash_probability < 0.5)  # Only mild crash risk
        )

        # Volatility expansion breakout entry with risk controls
        vol_breakout_entry = (
            self.vol_squeeze.shift(1) &
            ~self.vol_squeeze &  # Squeeze just ended
            (self.close > self.bb_upper.shift(1)) &  # Breakout
            (self.volume_ratio > 1.2) &
            self.mtf_trend_aligned &
            ~self.high_risk &
            (self.market_strength > 0.3)
        )

        # Crash recovery entry - specialized for post-crash opportunities
        crash_recovery_entry = (
            self.crash_mode.shift(1) &  # Was in crash mode
            ~self.crash_mode &  # Now exiting crash mode
            (self.crash_probability < 0.4) &  # Risk declining
            (self.funding_extreme_negative | self.funding_bullish_divergence) &  # Shorts overextended
            (self.price_velocity > 0) &  # Momentum improving
            (self.rsi < 60) &  # Relaxed RSI condition to 60
            (self.volume_ratio > 1.0)   # Volume confirming momentum
        )

        # Combine all long entries
        long_entries = (
            bull_entry |
            consolidation_entry |
            funding_div_entry |
            vol_breakout_entry |
            crash_recovery_entry
        )

        # Long exit conditions with enhanced risk management
        base_long_exit = (
            (self.rsi > 70) |
            (self.macd_hist < 0) |
            (self.close < self.ema_fast)
        )

        # Profit taking in bull market
        bull_exit = (
            self.bull_market &
            base_long_exit &
            (self.rsi > 65)
        )

        # Enhanced stop loss with volatility adaptation
        stop_loss_level = self.ema_fast - (1.5 * self.atr)
        stop_loss_exit = self.close < stop_loss_level

        # Funding stress exit with tighter controls
        funding_exit = (
            (self.funding_extreme_positive & (self.funding_momentum > 0)) |  # Increasing positive funding
            self.funding_turned_negative
        ) & (self.close < self.close.shift(1))

        # Volatility expansion exit with momentum filter
        vol_expansion_exit = (
            self.vol_expanding &
            (self.rsi > 60) &
            (self.price_velocity < 0) &
            (self.close < self.ema_medium)
        )

        # Crash protection exit - mandatory during high risk
        crash_protection_exit = (
            self.high_risk |
            self.crash_mode |
            (self.crash_probability > 0.7)
        )

        # Combine all long exits with priority for risk management
        long_exits = (
            bull_exit |
            stop_loss_exit |
            funding_exit |
            vol_expansion_exit |
            crash_protection_exit
        )

        return long_entries, long_exits

    def get_adaptive_short_signals(self) -> tuple[pd.Series, pd.Series]:
        """Generate adaptive short entry/exit signals based on market regime."""
        # Base short entry conditions with risk controls
        base_short_entry = (
            (self.rsi > 40) &
            (self.rsi < self.rsi.shift(1)) &
            (self.macd_hist < 0) &
            (self.macd_hist < self.macd_hist.shift(1)) &
            (self.volume_ratio > 0.8) &
            ~self.high_risk &  # Don't enter during high risk
            ~self.bull_market  # Avoid shorting in strong bull markets
        )

        # Bear market aggressive entry with enhanced controls
        bear_entry = (
            self.bear_market &
            base_short_entry &
            (~self.mtf_trend_aligned) &
            ~self.funding_extreme_negative &
            (self.funding_momentum <= 0) &
            (self.market_strength < 0.4)
        )

        # Consolidation mean reversion entry with risk adjustment
        consolidation_short = (
            self.consolidation &
            (self.close > self.bb_middle) &
            (self.close < self.bb_upper) &
            (self.rsi > 60) &
            (self.rsi < self.rsi.shift(1)) &
            self.vol_contracting &
            (self.volume_ratio > 1.0) &
            ~self.high_risk &
            (self.market_strength < 0.5)
        )

        # Funding divergence short entry (contrarian) with safety
        funding_div_short = (
            self.funding_bearish_divergence &
            (self.rsi > 55) &
            (self.close > self.ema_medium) &
            (self.funding_rate > 0) &
            (self.volume_ratio > 0.9) &
            ~self.high_risk &
            (self.crash_probability < 0.5)
        )

        # Enhanced crash mode short entry - require volatility expansion confirmation
        crash_short_entry = (
            self.crash_mode &
            (self.price_velocity < 0) &
            (self.rsi < 40) &
            (self.funding_momentum < 0) &
            (self.volume_ratio > 1.1) &
            (self.vol_expanding | self.vol_cascade) &  # Accept either condition
            (self.vol_ratio_4h > 1.0)
        )

        # NEW: Early crash short entry - enter before full crash_mode activation
        early_crash_short = (
            self.early_crash_warning &  # Early warning phase (crash probability 0.3-0.5)
            (self.price_velocity < 0) &
            (self.funding_momentum < 0) &
            (self.funding_acceleration_rising) &  # Rapidly rising funding acceleration
            (self.cross_timeframe_funding_divergence) &  # Cross-timeframe confirmation
            (self.volume_ratio > 0.8) &  # Relaxed threshold
            (self.vol_expanding | (self.vol_ratio_4h > 1.0)) &
            (self.rsi < 55)  # Less restrictive RSI threshold
        )

        # NEW: Mid-phase crash short entry - more aggressive position
        mid_crash_short = (
            self.mid_crash_phase &  # Mid-phase (crash probability 0.6-0.8)
            (self.funding_momentum < 0) &
            (self.price_velocity < 0) &
            (self.volume_ratio > 1.0)
        )

        # Combine all short entries
        short_entries = (
            bear_entry |
            consolidation_short |
            funding_div_short |
            crash_short_entry |
            early_crash_short |  # NEW: Early warning crash entry
            mid_crash_short     # NEW: Mid-phase crash entry
        )

        # Short exit conditions with enhanced protection
        base_short_exit = (
            (self.rsi < 30) |
            (self.macd_hist > 0) |
            (self.close > self.ema_fast)
        )

        # Profit taking in bear market
        bear_exit = (
            self.bear_market &
            base_short_exit &
            (self.rsi < 35)
        )

        # Enhanced stop loss with volatility adaptation and crash-specific tuning
        # Crash mode gets tighter stops based on volatility spike
        crash_stop_multiplier = np.where(
            self.vol_ratio_4h > 1.3,
            0.8,
            1.5
        )
        stop_loss_level = self.ema_fast + (crash_stop_multiplier * self.atr)
        stop_loss_exit = self.close > stop_loss_level

        # New exit: funding-induced squeeze for crash recovery detection
        funding_squeeze = (self.funding_stress < -0.7) & (self.price_velocity > 0)

        # Funding stress exit with tighter controls
        funding_cover = (
            (self.funding_extreme_negative & (self.funding_momentum < 0)) |  # Increasing negative funding
            self.funding_turned_positive
        ) & (self.close > self.close.shift(1))

        # Crash protection exit - mandatory coverage during extreme risk
        crash_protection_cover = (
            self.high_risk |
            self.crash_mode |
            (self.crash_probability > 0.7) |
            (self.funding_extreme_positive & (self.close > self.ema_medium))
        )

        # Consolidation exit
        consolidation_exit = (
            self.consolidation &
            (self.close > self.bb_middle) &
            (self.rsi > 50)
        )

        # Combine all short exits with priority for risk management
        short_exits = (
            bear_exit |
            stop_loss_exit |
            funding_cover |
            crash_protection_cover |
            consolidation_exit |
            funding_squeeze  # New exit condition for crash recovery
        )

        return short_entries, short_exits

    def generate_adaptive_signals(self) -> tuple[pd.Series, pd.Series]:
        """Generate final adaptive signals combining long and short strategies."""
        # Get long and short signals
        long_entries, long_exits = self.get_adaptive_long_signals()
        short_entries, short_exits = self.get_adaptive_short_signals()

        # Enhanced conflict resolution with risk prioritization
        # During high risk periods, exits take absolute priority
        high_risk_exits = self.high_risk | self.crash_mode

        # Force exits during extreme risk regardless of entries
        forced_long_exits = high_risk_exits & long_entries
        forced_short_exits = high_risk_exits & short_entries

        # Remove conflicting entries
        long_entries = long_entries & ~forced_long_exits
        short_entries = short_entries & ~forced_short_exits

        # Apply forced exits
        long_exits = long_exits | forced_long_exits
        short_exits = short_exits | forced_short_exits

        # Standard conflict resolution - prioritize exits over entries
        conflicts = long_entries & long_exits
        long_entries = long_entries & ~conflicts

        conflicts = short_entries & short_exits
        short_entries = short_entries & ~conflicts

        # Prevent simultaneous long and short entries
        simultaneous_entries = long_entries & short_entries
        # In bull market, prefer longs; in bear market, prefer shorts
        long_entries = long_entries & ~(simultaneous_entries & (self.bull_market | self.consolidation))
        short_entries = short_entries & ~(simultaneous_entries & self.bear_market)

        # Convert to buy/sell signals
        entries = long_entries | short_entries
        exits = long_exits | short_exits

        # Store individual signals for analysis
        self.feature_df['long_entries'] = long_entries.astype(int)
        self.feature_df['long_exits'] = long_exits.astype(int)
        self.feature_df['short_entries'] = short_entries.astype(int)
        self.feature_df['short_exits'] = short_exits.astype(int)

        return entries, exits

    def calculate_position_sizing(self) -> pd.Series:
        """Calculate adaptive position sizing based on market regime and risk."""
        # Base size based on market strength with crash awareness
        # Increased multiplier from 0.4 to 0.5 to allow larger positions in strong bull markets
        base_size = self.market_strength * 0.45 + 0.15  # Slightly reduced to account for new phases

        # NEW: Phase-based crash position sizing
        crash_phase_multiplier = pd.Series(1.0, index=self.close.index)
        # Early warning phase: smaller position for early entry
        crash_phase_multiplier[self.early_crash_warning] = 0.7
        # Mid-phase: aggressive position as crash develops
        crash_phase_multiplier[self.mid_crash_phase] = 1.3
        # Late phase: reduce position as crash matures
        crash_phase_multiplier[self.late_crash_phase] = 0.8

        # Volatility adjustment with percentile ranking
        vol_percentile = (self.norm_atr.rank(pct=True) / self.norm_atr.rolling(50).rank(pct=True)).clip(0.1, 2.0)
        vol_adjustment = 1.0 - (vol_percentile - 1).clip(0, 0.8)

        # Funding stress adjustment with enhanced sensitivity
        funding_risk = np.abs(self.funding_stress)
        funding_adjustment = 1.0 - funding_risk * 0.8

        # Crash risk adjustment - major reduction during high risk
        crash_risk_adjustment = pd.Series(1.0, index=self.close.index)
        crash_risk_adjustment[self.high_risk] = 0.3  # Severe reduction
        crash_risk_adjustment[self.med_risk] = 0.6   # Moderate reduction
        crash_risk_adjustment[self.crash_mode] = 0.2 # Maximum reduction

        # Bull/bear market adjustments
        regime_adjustment = pd.Series(0.8, index=self.close.index)  # Conservative default
        regime_adjustment[self.bull_market] = 1.0   # Full size in bull market
        regime_adjustment[self.consolidation] = 0.7 # Reduced size in consolidation

        # Combine all adjustments with weighting
        size_multiplier = (
            base_size *
            vol_adjustment *
            crash_phase_multiplier *  # NEW: Add phase-based sizing
            funding_adjustment *
            crash_risk_adjustment *
            regime_adjustment
        )

        # Additional reduction during extreme volatility percentiles
        extreme_vol = self.norm_atr > self.norm_atr.rolling(50).quantile(0.9)
        size_multiplier[extreme_vol] *= 0.5

        # Ensure minimum position size for recovery trades
        recovery_condition = (
            (self.crash_mode.shift(1)) &
            (self.early_crash_warning) &  # NEW: Only reduce position if early warning is active
            (~self.crash_mode) &
            (self.funding_extreme_negative)
        )
        size_multiplier[recovery_condition] = np.maximum(size_multiplier[recovery_condition], 0.4)

        # Cap position size with dynamic maximum based on regime
        max_position = pd.Series(0.7, index=self.close.index)
        max_position[self.bull_market] = 0.8
        max_position[self.high_risk | self.crash_mode] = 0.3

        position_size = size_multiplier.clip(0.1, max_position)

        self.feature_df['position_size_calc'] = position_size

        return position_size

    def get_all_features(self) -> pd.DataFrame:
        """
        Return unified DataFrame with ALL features.
        """
        return self.feature_df.copy()


# Backward compatibility alias for old code that uses AdaptiveTradingSystem
AdaptiveTradingSystem = FuturesTradingStrategy


def generate_signals(df: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    """
    Generate adaptive trading signals for futures with funding rate.

    Args:
        df: DataFrame with OHLCV + funding_rate data
            Required columns: open, high, low, close, volume
            Optional: funding_rate (if missing, set to 0)
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

    # Initialize futures trading system
    system = FuturesTradingStrategy(df)

    # Generate adaptive signals
    entries, exits = system.generate_adaptive_signals()

    # Fill NaN values with False
    entries = entries.fillna(False)
    exits = exits.fillna(False)

    return entries, exits


def run_experiment(val_df: pd.DataFrame) -> pd.DataFrame:
    """
    Run the futures trading experiment.

    Returns unified DataFrame with:
    - Original OHLCV data
    - ALL intermediate features (indicators, scores, regimes)
    - Trading signals (entries, exits)
    - Portfolio metrics (positions, values, returns)

    Args:
        val_df: Validation DataFrame with OHLCV + funding_rate data

    Returns:
        DataFrame with ALL features + backtest results
    """
    # Generate entry/exit signals
    entries, exits = generate_signals(val_df)

    # Initialize futures trading system
    system = FuturesTradingStrategy(val_df)

    # Get ALL features (this is the key innovation!)
    all_features = system.get_all_features()

    # Calculate dynamic position sizing
    size_multiplier = system.calculate_position_sizing()
    all_features['position_size'] = size_multiplier

    # Calculate volatility-based stop loss distance with crash protection
    stop_distance = 1.5 + (all_features['norm_atr'] - all_features['vol_low_threshold']) / \
                   (all_features['vol_high_threshold'] - all_features['vol_low_threshold']) * 1.5
    stop_distance = stop_distance.clip(1.5, 4.0)

    # Increase stop distance during high volatility regimes
    high_vol_stop_mult = pd.Series(1.0, index=val_df.index)
    high_vol_stop_mult[all_features['high_volatility'].astype(bool)] = 1.3
    high_vol_stop_mult[all_features['crash_mode'].astype(bool)] = 1.5
    stop_distance = stop_distance * high_vol_stop_mult

    stop_percents = (all_features['atr'] * stop_distance / val_df['close']) * 100
    stop_percents = stop_percents.clip(1.0, 8.0)
    all_features['stop_loss_pct'] = stop_percents

    # Run VectorBT backtest with dynamic sizing and stops
    portfolio = vbt.Portfolio.from_signals(
        close=val_df['close'],
        entries=entries,
        exits=exits,
        size=size_multiplier,
        sl_stop=stop_percents,
        init_cash=10000.0,
        fees=0.001,  # 0.1% commission
        freq='1h',   # Hourly data
    )

    # Create result DataFrame with original OHLCV
    result_df = val_df.copy()

    # Add ALL features to result
    for col in all_features.columns:
        result_df[col] = all_features[col]

    # Add trading signals
    result_df['entry_signal'] = entries.astype(float)
    result_df['exit_signal'] = exits.astype(float)

    # Create combined signal column (required by evaluator)
    # 1.0 = buy, -1.0 = sell, 0.0 = hold
    result_df['signal'] = 0.0
    result_df['signal'] = result_df['signal'].mask(entries, 1.0)
    result_df['signal'] = result_df['signal'].mask(exits, -1.0)

    # Add portfolio metrics (outputs/predictions)
    result_df['position'] = portfolio.position_mask().astype(float)
    result_df['portfolio_value'] = portfolio.value()
    result_df['cash'] = portfolio.cash()
    result_df['returns'] = portfolio.returns()

    # Store metrics in attrs
    result_df.attrs['total_return'] = portfolio.total_return()
    result_df.attrs['sharpe_ratio'] = portfolio.sharpe_ratio()
    result_df.attrs['max_drawdown'] = portfolio.max_drawdown()

    return result_df


# EVOLVE-BLOCK-END


# Example standalone usage
if __name__ == "__main__":
    print("Futures Trading Strategy with Unified Feature DataFrame")
    print("=" * 80)
    print("This module outputs ALL features for Shinka to evolve:")
    print("  - Input features: OHLCV, funding_rate")
    print("  - Intermediate features: indicators, scores, regimes")
    print("  - Output features: signals, positions, portfolio values")
    print("=" * 80)
    print("\nRun: python evaluate.py --program_path initial.py")
