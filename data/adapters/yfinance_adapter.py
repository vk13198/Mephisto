import yfinance as yf
import pandas as pd

class YFinanceAdapter:
    """Simple adapter to fetch OHLC data using yfinance.

    Methods:
      - get_ohlc(symbol, period='5d', interval='5m') -> DataFrame with open/high/low/close/volume
    """
    def __init__(self):
        pass

    def get_ohlc(self, symbol, period='5d', interval='5m'):
        try:
            # yfinance expects ticker symbols like 'AAPL' or 'RELIANCE.NS' for NSE
            data = yf.download(tickers=symbol, period=period, interval=interval, progress=False, threads=False)
            if data is None or data.empty:
                return pd.DataFrame()
            # ensure columns: Open, High, Low, Close, Volume
            df = data.rename(columns={'Open':'open','High':'high','Low':'low','Close':'close','Volume':'volume'})
            return df[['open','high','low','close','volume']]
        except Exception:
            return pd.DataFrame()
