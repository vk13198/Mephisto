import logging
import pandas as pd
import numpy as np
from collections import deque
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

class MarketDataManager:
    def __init__(self, zerodha_client, max_candles=1000):
        self.zerodha = zerodha_client
        self.max_candles = max_candles
        # Store candles by instrument_token
        self.candles = {}
        self.instrument_map = {}
        self.last_update = {}
    
    def add_instrument(self, symbol, instrument_token, exchange='NSE'):
        """Add instrument to track"""
        self.instrument_map[instrument_token] = {
            'symbol': symbol,
            'exchange': exchange
        }
        if instrument_token not in self.candles:
            self.candles[instrument_token] = {
                '1minute': deque(maxlen=self.max_candles),
                '5minute': deque(maxlen=self.max_candles),
                '15minute': deque(maxlen=self.max_candles),
                '60minute': deque(maxlen=self.max_candles)
            }
    
    def process_tick(self, tick):
        """Process incoming tick and build candles"""
        token = tick['instrument_token']
        
        if token not in self.instrument_map:
            return
        
        timestamp = tick.get('timestamp', datetime.now())
        if isinstance(timestamp, str):
            timestamp = pd.to_datetime(timestamp)
        
        price = tick.get('last_price', 0)
        volume = tick.get('volume_traded', 0)
        ohlc = tick.get('ohlc', {})
        
        # Update 1-minute candle
        self._update_candle(token, '1minute', timestamp, price, volume, ohlc)
    
    def _update_candle(self, token, interval, timestamp, price, volume, ohlc):
        """Update candle data for given interval"""
        candles = self.candles[token][interval]
        
        # Determine current candle time
        if interval == '1minute':
            candle_time = timestamp.replace(second=0, microsecond=0)
        elif interval == '5minute':
            minute = (timestamp.minute // 5) * 5
            candle_time = timestamp.replace(minute=minute, second=0, microsecond=0)
        elif interval == '15minute':
            minute = (timestamp.minute // 15) * 15
            candle_time = timestamp.replace(minute=minute, second=0, microsecond=0)
        elif interval == '60minute':
            candle_time = timestamp.replace(minute=0, second=0, microsecond=0)
        else:
            candle_time = timestamp
        
        if not candles or candles[-1]['timestamp'] != candle_time:
            # New candle
            new_candle = {
                'timestamp': candle_time,
                'open': ohlc.get('open', price),
                'high': ohlc.get('high', price),
                'low': ohlc.get('low', price),
                'close': price,
                'volume': volume
            }
            candles.append(new_candle)
        else:
            # Update existing candle
            candles[-1]['high'] = max(candles[-1]['high'], price)
            candles[-1]['low'] = min(candles[-1]['low'], price)
            candles[-1]['close'] = price
            candles[-1]['volume'] = volume
    
    def get_dataframe(self, token, interval='5minute', n=100):
        """Get DataFrame for analysis"""
        if token not in self.candles:
            return pd.DataFrame()
        
        candles = list(self.candles[token][interval])
        if not candles:
            return pd.DataFrame()
        
        df = pd.DataFrame(candles)
        df['symbol'] = self.instrument_map[token]['symbol']
        df.set_index('timestamp', inplace=True)
        
        return df.tail(n)
    
    def get_latest_price(self, token):
        """Get latest price for instrument"""
        if token in self.zerodha.live_data:
            return self.zerodha.live_data[token]['last_price']
        return None
    
    def preload_historical_data(self, instrument_token, interval='5minute', days=5):
        """Preload historical data from Zerodha"""
        try:
            df = self.zerodha.get_historical_data(
                instrument_token,
                interval=interval,
                from_date=datetime.now() - timedelta(days=days),
                to_date=datetime.now()
            )
            
            if not df.empty:
                # Convert to candle format and store
                candles = self.candles[instrument_token][interval]
                for idx, row in df.iterrows():
                    candle = {
                        'timestamp': idx,
                        'open': row['open'],
                        'high': row['high'],
                        'low': row['low'],
                        'close': row['close'],
                        'volume': row['volume']
                    }
                    candles.append(candle)
                
                logger.info(f"Preloaded {len(df)} candles for {instrument_token}")
                return True
            
        except Exception as e:
            logger.error(f"Failed to preload historical data: {e}")
        
        return False
    
    def get_all_symbols(self):
        """Get all tracked symbols"""
        return {token: info['symbol'] for token, info in self.instrument_map.items()}
