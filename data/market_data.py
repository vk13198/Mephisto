import logging
import pandas as pd
import numpy as np
from collections import deque
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

# optional adapters
try:
    from .adapters.finnhub_adapter import FinnhubAdapter
except Exception:
    FinnhubAdapter = None

try:
    from .adapters.yfinance_adapter import YFinanceAdapter
except Exception:
    YFinanceAdapter = None

class MarketDataManager:
    def __init__(self, zerodha_client=None, max_candles=1000, provider='simulated', api_key=None):
        self.zerodha = zerodha_client
        self.max_candles = max_candles
        # Store candles by instrument_token
        self.candles = {}
        self.instrument_map = {}   # token -> {symbol, exchange}
        self.symbol_to_token = {}  # symbol -> token
        self.last_update = {}
        self.provider = provider or 'simulated'
        self.api_key = api_key
        self.adapter = None
        self._started = False

        # choose adapter if available
        if self.provider == 'finnhub' and FinnhubAdapter is not None and self.api_key:
            self.adapter = FinnhubAdapter(self.api_key, on_ticks=self._on_adapter_ticks)
        # yfinance used for historical fetch when zerodha not available
        if YFinanceAdapter is not None:
            self.yf = YFinanceAdapter()
        else:
            self.yf = None

    def start(self):
        if self.adapter:
            try:
                self.adapter.start()
                self._started = True
                logger.info(f"MarketDataManager: started adapter {self.provider}")
            except Exception as e:
                logger.error(f"Failed to start adapter: {e}")

    def stop(self):
        if self.adapter:
            try:
                self.adapter.stop()
                self._started = False
            except Exception:
                pass

    def subscribe(self, symbol_or_token):
        """Request market data for a symbol or token (adapter-specific)"""
        if self.adapter is None:
            return
        # map symbol to adapter subscription
        symbol = None
        if isinstance(symbol_or_token, str) and symbol_or_token.startswith('SIM'):
            # simulated
            symbol = self.instrument_map.get(symbol_or_token, {}).get('symbol')
        else:
            symbol = symbol_or_token
        try:
            if hasattr(self.adapter, 'subscribe'):
                self.adapter.subscribe(symbol)
        except Exception:
            pass

    def unsubscribe(self, symbol_or_token):
        if self.adapter is None:
            return
        symbol = symbol_or_token
        try:
            if hasattr(self.adapter, 'unsubscribe'):
                self.adapter.unsubscribe(symbol)
        except Exception:
            pass

    def add_instrument(self, symbol, instrument_token, exchange='NSE'):
        """Add instrument to track"""
        token = str(instrument_token)
        self.instrument_map[token] = {
            'symbol': symbol,
            'exchange': exchange
        }
        self.symbol_to_token[symbol] = token
        if token not in self.candles:
            self.candles[token] = {
                '1minute': deque(maxlen=self.max_candles),
                '5minute': deque(maxlen=self.max_candles),
                '15minute': deque(maxlen=self.max_candles),
                '60minute': deque(maxlen=self.max_candles)
            }

    def _on_adapter_ticks(self, ticks):
        """Callback from external adapter (finnhub etc.)"""
        # Convert adapter tick to internal format expected by process_tick
        norm_ticks = []
        for t in ticks:
            # adapter may return symbol-based ticks
            symbol = t.get('symbol') or t.get('tradingsymbol')
            token = self.symbol_to_token.get(symbol) or t.get('instrument_token') or t.get('token')
            norm = {
                'instrument_token': token,
                'symbol': symbol,
                'last_price': t.get('last_price') or t.get('price') or t.get('p'),
                'volume_traded': t.get('volume') or t.get('v') or t.get('volume_traded'),
                'timestamp': t.get('timestamp')
            }
            norm_ticks.append(norm)
        if norm_ticks:
            self.process_ticks(norm_ticks)

    def process_ticks(self, ticks):
        """Process list of ticks"""
        for tick in ticks:
            try:
                self.process_tick(tick)
            except Exception as e:
                logger.debug(f"Failed to process tick: {e}")

    def process_tick(self, tick):
        """Process incoming tick and build candles"""
        token = tick.get('instrument_token')
        # if token missing, try symbol lookup
        if not token:
            symbol = tick.get('symbol')
            if symbol:
                token = self.symbol_to_token.get(symbol)
        if not token:
            # unknown instrument, skip
            return

        if token not in self.instrument_map:
            return

        timestamp = tick.get('timestamp', datetime.now())
        if isinstance(timestamp, str):
            try:
                timestamp = pd.to_datetime(timestamp)
            except Exception:
                timestamp = datetime.now()

        price = tick.get('last_price', tick.get('price', 0)) or 0
        volume = tick.get('volume_traded', tick.get('volume', 0)) or 0
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
        token = str(token)
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
        token = str(token)
        # try zerodha live cache
        try:
            if self.zerodha and hasattr(self.zerodha, 'live_data') and token in self.zerodha.live_data:
                return self.zerodha.live_data[token]['last_price']
        except Exception:
            pass
        # fall back to latest candle
        if token in self.candles and self.candles[token]['1minute']:
            return self.candles[token]['1minute'][-1]['close']
        return None

    def preload_historical_data(self, instrument_token, interval='5minute', days=5):
        """Preload historical data from Zerodha or yfinance"""
        try:
            if self.zerodha:
                df = self.zerodha.get_historical_data(
                    instrument_token,
                    interval=interval,
                    from_date=datetime.now() - timedelta(days=days),
                    to_date=datetime.now()
                )
                if not df.empty:
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
                    logger.info(f"Preloaded {len(df)} candles for {instrument_token} from Zerodha")
                    return True

            # fall back to yfinance (symbol based)
            if self.yf and instrument_token in self.instrument_map:
                symbol = self.instrument_map[instrument_token]['symbol']
                df = self.yf.get_ohlc(symbol, period=f"{days}d", interval='5m')
                if df is not None and not df.empty:
                    candles = self.candles[instrument_token][interval]
                    for idx, row in df.iterrows():
                        candle = {
                            'timestamp': idx.to_pydatetime(),
                            'open': row['open'],
                            'high': row['high'],
                            'low': row['low'],
                            'close': row['close'],
                            'volume': row.get('volume', 0)
                        }
                        candles.append(candle)
                    logger.info(f"Preloaded {len(df)} candles for {instrument_token} from yfinance")
                    return True

        except Exception as e:
            logger.error(f"Failed to preload historical data: {e}")

        return False

    def get_all_symbols(self):
        """Get all tracked symbols"""
        return {token: info['symbol'] for token, info in self.instrument_map.items()}
