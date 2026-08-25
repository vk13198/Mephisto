import numpy as np
import pandas as pd

class TechnicalIndicators:
    @staticmethod
    def atr(high, low, close, period=14):
        """Calculate Average True Range"""
        high = pd.Series(high)
        low = pd.Series(low)
        close = pd.Series(close)
        
        tr1 = high - low
        tr2 = abs(high - close.shift(1))
        tr3 = abs(low - close.shift(1))
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr = tr.rolling(window=period).mean()
        return atr.values
    
    @staticmethod
    def rsi(close, period=14):
        """Calculate RSI"""
        close = pd.Series(close)
        delta = close.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        return rsi.values
    
    @staticmethod
    def ema(data, period):
        """Calculate EMA"""
        return pd.Series(data).ewm(span=period, adjust=False).mean().values
    
    @staticmethod
    def sma(data, period):
        """Calculate SMA"""
        return pd.Series(data).rolling(window=period).mean().values
    
    @staticmethod
    def adx(high, low, close, period=14):
        """Calculate ADX, DI+, DI-"""
        high = pd.Series(high)
        low = pd.Series(low)
        close = pd.Series(close)
        
        plus_dm = high.diff()
        minus_dm = -low.diff()
        
        plus_dm[plus_dm < 0] = 0
        minus_dm[minus_dm < 0] = 0
        
        tr1 = high - low
        tr2 = abs(high - close.shift(1))
        tr3 = abs(low - close.shift(1))
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        
        atr = tr.rolling(window=period).mean()
        
        plus_di = 100 * (plus_dm.rolling(window=period).mean() / atr)
        minus_di = 100 * (minus_dm.rolling(window=period).mean() / atr)
        
        dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di)
        adx = dx.rolling(window=period).mean()
        
        return plus_di.values, minus_di.values, adx.values
    
    @staticmethod
    def pivot_high(high, left_bars, right_bars):
        """Find pivot highs"""
        high = pd.Series(high)
        pivots = np.zeros(len(high))
        
        for i in range(left_bars, len(high) - right_bars):
            if all(high.iloc[i] >= high.iloc[i-left_bars:i]) and                all(high.iloc[i] >= high.iloc[i+1:i+right_bars+1]):
                pivots[i] = high.iloc[i]
            else:
                pivots[i] = np.nan
        
        return pivots
    
    @staticmethod
    def pivot_low(low, left_bars, right_bars):
        """Find pivot lows"""
        low = pd.Series(low)
        pivots = np.zeros(len(low))
        
        for i in range(left_bars, len(low) - right_bars):
            if all(low.iloc[i] <= low.iloc[i-left_bars:i]) and                all(low.iloc[i] <= low.iloc[i+1:i+right_bars+1]):
                pivots[i] = low.iloc[i]
            else:
                pivots[i] = np.nan
        
        return pivots
