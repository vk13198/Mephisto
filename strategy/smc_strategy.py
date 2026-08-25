import numpy as np
import pandas as pd
from .indicators import TechnicalIndicators

class SMCStrategy:
    def __init__(self, config):
        self.config = config
        self.swing_len = config.SWING_LENGTH
        self.micro_swing_len = config.MICRO_SWING_LENGTH
        self.cont_zone_end = config.CONT_ZONE_END
        self.cont_max_age = config.CONT_MAX_AGE
        self.adx_len = config.ADX_LENGTH
        self.adx_min = config.ADX_MIN
        self.min_score = config.MIN_SCORE
        self.atr_period = config.ATR_PERIOD
        self.trail_atr_mult = config.TRAIL_ATR_MULT
        self.max_daily_loss_pct = config.MAX_DAILY_LOSS_PCT
        
        # State variables
        self.trend = 0
        self.last_high = None
        self.last_low = None
        self.last_high_bar = None
        self.last_low_bar = None
        self.prev_high = None
        self.prev_low = None
        
        self.leg_high = None
        self.leg_low = None
        self.leg_high_bar = None
        self.leg_low_bar = None
        self.leg_active = False
        self.leg_dir = 0
        
        self.fvg_top = None
        self.fvg_bot = None
        self.fvg_bar = None
        self.fvg_dir = 0
        
        self.ob_top = None
        self.ob_bot = None
        self.ob_bar = None
        self.ob_dir = 0
        
        self.micro_high = None
        self.micro_low = None
        self.micro_high_bar = None
        self.micro_low_bar = None
        
        self.recent_bull_sweep = False
        self.recent_bear_sweep = False
        self.sweep_bar = None
        
        self.trades_today = 0
        self.day_start_equity = None
        self.circuit_tripped = False
        self.current_date = None
        
        self.entry_price = None
        self.risk_dist = None
        self.sl_long = None
        self.sl_short = None
        self.tp1_long = None
        self.tp1_short = None
        self.tp2_long = None
        self.tp2_short = None
        self.tp3_long = None
        self.tp3_short = None
        self.trail_stop_long = None
        self.trail_stop_short = None
        self.tp1_long_done = False
        self.tp2_long_done = False
        self.tp1_short_done = False
        self.tp2_short_done = False
    
    def reset_daily(self, current_equity, date):
        """Reset daily counters"""
        if self.current_date != date:
            self.trades_today = 0
            self.day_start_equity = current_equity
            self.circuit_tripped = False
            self.current_date = date
    
    def calculate_fib(self, level):
        """Calculate Fibonacci level for active leg"""
        if not self.leg_active or self.leg_high is None or self.leg_low is None:
            return None
        
        if self.leg_dir == 1:
            return self.leg_high - (self.leg_high - self.leg_low) * level
        else:
            return self.leg_low + (self.leg_high - self.leg_low) * level
    
    def analyze(self, df, htf_df=None, current_equity=100000):
        """
        Main analysis function
        df: DataFrame with OHLCV data for current timeframe
        htf_df: DataFrame for higher timeframe analysis
        current_equity: Current portfolio equity
        """
        if len(df) < 50:
            return None
        
        # Reset daily counters
        current_date = pd.Timestamp.now().date()
        self.reset_daily(current_equity, current_date)
        
        # Extract data
        opens = df['open'].values
        highs = df['high'].values
        lows = df['low'].values
        closes = df['close'].values
        volumes = df['volume'].values
        
        latest_idx = len(df) - 1
        close = closes[latest_idx]
        high = highs[latest_idx]
        low = lows[latest_idx]
        open_price = opens[latest_idx]
        volume = volumes[latest_idx]
        prev_close = closes[latest_idx - 1] if latest_idx > 0 else close
        
        # Calculate indicators
        ti = TechnicalIndicators()
        atr = ti.atr(highs, lows, closes, self.atr_period)[-1]
        rsi = ti.rsi(closes, 14)[-1]
        vol_sma = ti.sma(volumes, 20)[-1]
        di_plus, di_minus, adx_val = ti.adx(highs, lows, closes, self.adx_len)
        adx_val = adx_val[-1] if not np.isnan(adx_val[-1]) else 0
        
        # Higher timeframe bias
        htf_bull = False
        htf_bear = False
        if htf_df is not None and len(htf_df) > 50:
            htf_close = htf_df['close'].iloc[-1]
            htf_ema = ti.ema(htf_df['close'].values, 50)[-1]
            htf_bull = htf_close > htf_ema
            htf_bear = htf_close < htf_ema
        
        # Detect swing points
        ph = ti.pivot_high(highs, self.swing_len, self.swing_len)
        pl = ti.pivot_low(lows, self.swing_len, self.swing_len)
        
        # Update swing state
        for i in range(len(ph)):
            if not np.isnan(ph[i]):
                self.prev_high = self.last_high
                self.last_high = ph[i]
                self.last_high_bar = i
        
        for i in range(len(pl)):
            if not np.isnan(pl[i]):
                self.prev_low = self.last_low
                self.last_low = pl[i]
                self.last_low_bar = i
        
        # CHOCH / BOS Detection
        bull_choch = (self.trend <= 0 and self.last_high is not None and 
                      close > self.last_high and prev_close <= self.last_high)
        bear_choch = (self.trend >= 0 and self.last_low is not None and 
                      close < self.last_low and prev_close >= self.last_low)
        bull_bos = (self.trend == 1 and self.last_high is not None and 
                    close > self.last_high and prev_close <= self.last_high)
        bear_bos = (self.trend == -1 and self.last_low is not None and 
                    close < self.last_low and prev_close >= self.last_low)
        
        if bull_choch or bull_bos:
            self.trend = 1
        if bear_choch or bear_bos:
            self.trend = -1
        
        # Liquidity sweep detection
        bull_sweep = (self.prev_low is not None and low < self.prev_low and close > self.prev_low)
        bear_sweep = (self.prev_high is not None and high > self.prev_high and close < self.prev_high)
        
        if bull_sweep:
            self.recent_bull_sweep = True
            self.recent_bear_sweep = False
            self.sweep_bar = latest_idx
        if bear_sweep:
            self.recent_bear_sweep = True
            self.recent_bull_sweep = False
            self.sweep_bar = latest_idx
        
        sweep_valid = (self.sweep_bar is not None and 
                      (latest_idx - self.sweep_bar <= 10))
        
        # Active leg + Fibonacci
        if bull_choch:
            self.leg_low = self.last_low
            self.leg_low_bar = self.last_low_bar
            self.leg_high = high
            self.leg_high_bar = latest_idx
            self.leg_active = True
            self.leg_dir = 1
        
        if bear_choch:
            self.leg_high = self.last_high
            self.leg_high_bar = self.last_high_bar
            self.leg_low = low
            self.leg_low_bar = latest_idx
            self.leg_active = True
            self.leg_dir = -1
        
        if self.leg_active and self.leg_dir == 1 and high > self.leg_high:
            self.leg_high = high
            self.leg_high_bar = latest_idx
        if self.leg_active and self.leg_dir == -1 and low < self.leg_low:
            self.leg_low = low
            self.leg_low_bar = latest_idx
        
        # FVG Detection
        if latest_idx >= 2:
            bull_fvg = (low > highs[latest_idx-2] and 
                       (low - highs[latest_idx-2]) > atr * 0.15)
            bear_fvg = (high < lows[latest_idx-2] and 
                       (lows[latest_idx-2] - high) > atr * 0.15)
            
            if bull_fvg and self.leg_active and self.leg_dir == 1:
                self.fvg_top = low
                self.fvg_bot = highs[latest_idx-2]
                self.fvg_bar = latest_idx
                self.fvg_dir = 1
            
            if bear_fvg and self.leg_active and self.leg_dir == -1:
                self.fvg_top = lows[latest_idx-2]
                self.fvg_bot = high
                self.fvg_bar = latest_idx
                self.fvg_dir = -1
        
        fvg_valid = (self.fvg_top is not None and 
                    (latest_idx - self.fvg_bar <= 30))
        
        # Order Block Detection
        if bull_choch:
            for i in range(min(8, latest_idx)):
                if closes[i] < opens[i]:
                    self.ob_top = highs[i]
                    self.ob_bot = lows[i]
                    self.ob_bar = i
                    self.ob_dir = 1
                    break
        
        if bear_choch:
            for i in range(min(8, latest_idx)):
                if closes[i] > opens[i]:
                    self.ob_top = highs[i]
                    self.ob_bot = lows[i]
                    self.ob_bar = i
                    self.ob_dir = -1
                    break
        
        ob_valid = (self.ob_top is not None and 
                   (latest_idx - self.ob_bar <= 30) and 
                   self.ob_dir == self.leg_dir)
        
        # Golden Zone
        g_top = self.calculate_fib(0.5)
        g_bot = self.calculate_fib(0.618)
        
        in_golden = False
        if self.leg_active and g_top is not None and g_bot is not None:
            if self.leg_dir == 1:
                in_golden = (low <= g_top and high >= g_bot)
            else:
                in_golden = (high >= g_bot and low <= g_top)
        
        # Micro Structure (for continuation trades)
        ph_m = ti.pivot_high(highs, self.micro_swing_len, self.micro_swing_len)
        pl_m = ti.pivot_low(lows, self.micro_swing_len, self.micro_swing_len)
        
        for i in range(len(ph_m)):
            if not np.isnan(ph_m[i]):
                self.micro_high = ph_m[i]
                self.micro_high_bar = i
        
        for i in range(len(pl_m)):
            if not np.isnan(pl_m[i]):
                self.micro_low = pl_m[i]
                self.micro_low_bar = i
        
        micro_range_valid = (self.micro_high is not None and 
                            self.micro_low is not None and 
                            self.micro_high > self.micro_low)
        
        # Continuation zones
        cont_zone_top_long = None
        cont_zone_bot_long = None
        cont_zone_top_short = None
        cont_zone_bot_short = None
        
        if micro_range_valid:
            range_size = self.micro_high - self.micro_low
            cont_zone_top_long = self.micro_high - range_size * 0.5
            cont_zone_bot_long = self.micro_high - range_size * self.cont_zone_end
            cont_zone_top_short = self.micro_low + range_size * self.cont_zone_end
            cont_zone_bot_short = self.micro_low + range_size * 0.5
        
        micro_fresh_long = (micro_range_valid and 
                           (latest_idx - self.micro_high_bar) <= self.cont_max_age and 
                           self.micro_high_bar > self.micro_low_bar)
        micro_fresh_short = (micro_range_valid and 
                            (latest_idx - self.micro_low_bar) <= self.cont_max_age and 
                            self.micro_low_bar > self.micro_high_bar)
        
        cont_in_golden_long = (micro_fresh_long and 
                              low <= cont_zone_top_long and 
                              high >= cont_zone_bot_long)
        cont_in_golden_short = (micro_fresh_short and 
                               high >= cont_zone_bot_short and 
                               low <= cont_zone_top_short)
        
        # Circuit breaker check
        if self.day_start_equity is not None:
            daily_loss_pct = ((self.day_start_equity - current_equity) / self.day_start_equity) * 100
            if daily_loss_pct >= self.max_daily_loss_pct:
                self.circuit_tripped = True
        
        can_trade = (self.trades_today < self.config.MAX_TRADES_PER_DAY and 
                    not self.circuit_tripped)
        
        # Confluence Score
        vol_ok = volume > vol_sma * 1.2
        rsi_long_ok = rsi < 68
        rsi_short_ok = rsi > 32
        htf_long_ok = htf_bull
        htf_short_ok = htf_bear
        adx_ok = adx_val > self.adx_min
        
        strong_bull = close > open_price and (close - open_price) > atr * 0.3
        strong_bear = close < open_price and (open_price - close) > atr * 0.3
        
        poi_long = ((fvg_valid and self.fvg_dir == 1) or 
                   (ob_valid and self.ob_dir == 1))
        poi_short = ((fvg_valid and self.fvg_dir == -1) or 
                    (ob_valid and self.ob_dir == -1))
        
        # Score calculation
        score_long = 0
        score_long += 2 if poi_long else 0
        score_long += 1 if strong_bull else 0
        score_long += 1 if vol_ok else 0
        score_long += 1 if rsi_long_ok else 0
        score_long += 2 if htf_long_ok else 0
        score_long += 1 if adx_ok else 0
        score_long += 1 if (self.recent_bull_sweep and sweep_valid) else 0
        
        score_short = 0
        score_short += 2 if poi_short else 0
        score_short += 1 if strong_bear else 0
        score_short += 1 if vol_ok else 0
        score_short += 1 if rsi_short_ok else 0
        score_short += 2 if htf_short_ok else 0
        score_short += 1 if adx_ok else 0
        score_short += 1 if (self.recent_bear_sweep and sweep_valid) else 0
        
        long_confluence_ok = score_long >= self.min_score
        short_confluence_ok = score_short >= self.min_score
        
        # Final signals
        primary_long = (self.leg_active and self.leg_dir == 1 and 
                       self.trend == 1 and in_golden and 
                       long_confluence_ok and can_trade)
        primary_short = (self.leg_active and self.leg_dir == -1 and 
                        self.trend == -1 and in_golden and 
                        short_confluence_ok and can_trade)
        
        cont_long = (self.trend == 1 and cont_in_golden_long and 
                    long_confluence_ok and can_trade)
        cont_short = (self.trend == -1 and cont_in_golden_short and 
                     short_confluence_ok and can_trade)
        
        long_signal = primary_long or cont_long
        short_signal = primary_short or cont_short
        is_cont_long = cont_long and not primary_long
        is_cont_short = cont_short and not primary_short
        
        # Prepare signal details
        signal = None
        if long_signal or short_signal:
            is_long = long_signal
            is_cont = is_cont_long if is_long else is_cont_short
            
            # Calculate levels
            if is_cont and micro_range_valid:
                if is_long:
                    sl = self.micro_low - atr * 0.25
                    risk_dist = close - sl
                    tp2 = self.micro_high + (self.micro_high - self.micro_low) * 0.272
                    tp3 = self.micro_high + (self.micro_high - self.micro_low) * 0.618
                else:
                    sl = self.micro_high + atr * 0.25
                    risk_dist = sl - close
                    tp2 = self.micro_low - (self.micro_high - self.micro_low) * 0.272
                    tp3 = self.micro_low - (self.micro_high - self.micro_low) * 0.618
            else:
                fib_100 = self.calculate_fib(1.0)
                fib_neg_272 = self.calculate_fib(-0.272)
                fib_neg_618 = self.calculate_fib(-0.618)
                
                if is_long:
                    sl = min(fib_100, low) - atr * 0.25 if fib_100 is not None else low - atr * 0.25
                    risk_dist = close - sl
                    tp2 = fib_neg_272 if fib_neg_272 is not None else close + risk_dist * 2
                    tp3 = fib_neg_618 if fib_neg_618 is not None else close + risk_dist * 3
                else:
                    sl = max(fib_100, high) + atr * 0.25 if fib_100 is not None else high + atr * 0.25
                    risk_dist = sl - close
                    tp2 = fib_neg_272 if fib_neg_272 is not None else close - risk_dist * 2
                    tp3 = fib_neg_618 if fib_neg_618 is not None else close - risk_dist * 3
            
            tp1 = close + risk_dist if is_long else close - risk_dist
            
            # Calculate quantity based on risk
            risk_amount = current_equity * (self.config.RISK_PERCENT / 100)
            qty = int(risk_amount / risk_dist) if risk_dist > 0 else 0
            
            signal = {
                'type': 'LONG' if is_long else 'SHORT',
                'symbol': df['symbol'].iloc[-1] if 'symbol' in df.columns else 'UNKNOWN',
                'price': close,
                'quantity': qty,
                'stop_loss': sl,
                'take_profit_1': tp1,
                'take_profit_2': tp2,
                'take_profit_3': tp3,
                'risk_distance': risk_dist,
                'score': score_long if is_long else score_short,
                'is_continuation': is_cont,
                'strategy': 'SMC_FIB_V2',
                'timestamp': pd.Timestamp.now(),
                'details': {
                    'trend': self.trend,
                    'leg_dir': self.leg_dir,
                    'in_golden': in_golden,
                    'fib_50': g_top,
                    'fib_618': g_bot,
                    'atr': atr,
                    'rsi': rsi,
                    'adx': adx_val,
                    'poi_long': poi_long,
                    'poi_short': poi_short,
                    'sweep_valid': sweep_valid,
                    'micro_range_valid': micro_range_valid,
                    'circuit_tripped': self.circuit_tripped,
                    'trades_today': self.trades_today
                }
            }
            
            self.trades_today += 1
        
        return signal
    
    def update_trailing_stop(self, df, position):
        """Update trailing stop for open positions"""
        if position is None or len(df) < 2:
            return None
        
        ti = TechnicalIndicators()
        atr = ti.atr(df['high'].values, df['low'].values, df['close'].values, self.atr_period)[-1]
        latest = df.iloc[-1]
        
        if position['type'] == 'LONG':
            if latest['high'] >= position['entry_price'] + position['risk_distance'] * 1.5:
                candidate = latest['high'] - atr * self.trail_atr_mult
                if self.trail_stop_long is None:
                    self.trail_stop_long = candidate
                else:
                    self.trail_stop_long = max(self.trail_stop_long, candidate)
                return self.trail_stop_long
        else:
            if latest['low'] <= position['entry_price'] - position['risk_distance'] * 1.5:
                candidate = latest['low'] + atr * self.trail_atr_mult
                if self.trail_stop_short is None:
                    self.trail_stop_short = candidate
                else:
                    self.trail_stop_short = min(self.trail_stop_short, candidate)
                return self.trail_stop_short
        
        return None
