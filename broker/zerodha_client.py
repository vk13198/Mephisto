import logging
import pandas as pd
from kiteconnect import KiteConnect, KiteTicker

logger = logging.getLogger(__name__)

class ZerodhaClient:
    def __init__(self, api_key, access_token=None):
        self.api_key = api_key
        self.access_token = access_token
        self.kite = None
        self.ticker = None
        self.subscribed_tokens = set()
        self.on_ticks_callback = None
        self.on_connect_callback = None
        self.on_close_callback = None
        self.live_data = {}
        
        if api_key and access_token:
            self.connect()
    
    def connect(self):
        """Initialize Kite Connect"""
        try:
            self.kite = KiteConnect(api_key=self.api_key)
            self.kite.set_access_token(self.access_token)
            logger.info("Zerodha Kite Connect initialized")
            return True
        except Exception as e:
            logger.error(f"Failed to connect to Zerodha: {e}")
            return False
    
    def get_login_url(self):
        """Get login URL for user authentication"""
        if self.kite:
            return self.kite.login_url()
        return None
    
    def generate_session(self, request_token, api_secret):
        """Generate access token from request token"""
        try:
            data = self.kite.generate_session(request_token, api_secret=api_secret)
            self.access_token = data["access_token"]
            self.kite.set_access_token(self.access_token)
            logger.info("Session generated successfully")
            return self.access_token
        except Exception as e:
            logger.error(f"Failed to generate session: {e}")
            return None
    
    def get_instruments(self, exchange='NSE'):
        """Get list of tradable instruments"""
        try:
            instruments = self.kite.instruments(exchange)
            return pd.DataFrame(instruments)
        except Exception as e:
            logger.error(f"Failed to get instruments: {e}")
            return pd.DataFrame()
    
    def get_historical_data(self, instrument_token, interval='5minute', 
                           from_date=None, to_date=None, continuous=False):
        """Fetch historical candle data"""
        try:
            if from_date is None:
                from_date = pd.Timestamp.now() - pd.Timedelta(days=5)
            if to_date is None:
                to_date = pd.Timestamp.now()
            
            data = self.kite.historical_data(
                instrument_token, 
                from_date.strftime('%Y-%m-%d %H:%M:%S'),
                to_date.strftime('%Y-%m-%d %H:%M:%S'),
                interval,
                continuous=continuous
            )
            
            df = pd.DataFrame(data)
            if not df.empty:
                df['date'] = pd.to_datetime(df['date'])
                df.set_index('date', inplace=True)
            return df
        except Exception as e:
            logger.error(f"Failed to get historical data: {e}")
            return pd.DataFrame()
    
    def place_order(self, variety, exchange, tradingsymbol, transaction_type, 
                   quantity, product, order_type, price=None, trigger_price=None,
                   tag=None):
        """Place an order"""
        try:
            order_params = {
                'variety': variety,
                'exchange': exchange,
                'tradingsymbol': tradingsymbol,
                'transaction_type': transaction_type,
                'quantity': quantity,
                'product': product,
                'order_type': order_type,
            }
            
            if price:
                order_params['price'] = price
            if trigger_price:
                order_params['trigger_price'] = trigger_price
            if tag:
                order_params['tag'] = tag
            
            order_id = self.kite.place_order(**order_params)
            logger.info(f"Order placed: {order_id}")
            return order_id
        except Exception as e:
            logger.error(f"Failed to place order: {e}")
            return None
    
    def modify_order(self, variety, order_id, parent_order_id=None, 
                    quantity=None, price=None, trigger_price=None, 
                    order_type=None, validity=None, disclosed_quantity=None):
        """Modify an existing order"""
        try:
            params = {'variety': variety, 'order_id': order_id}
            if parent_order_id:
                params['parent_order_id'] = parent_order_id
            if quantity:
                params['quantity'] = quantity
            if price:
                params['price'] = price
            if trigger_price:
                params['trigger_price'] = trigger_price
            if order_type:
                params['order_type'] = order_type
            if validity:
                params['validity'] = validity
            if disclosed_quantity:
                params['disclosed_quantity'] = disclosed_quantity
            
            order_id = self.kite.modify_order(**params)
            logger.info(f"Order modified: {order_id}")
            return order_id
        except Exception as e:
            logger.error(f"Failed to modify order: {e}")
            return None
    
    def cancel_order(self, variety, order_id, parent_order_id=None):
        """Cancel an order"""
        try:
            params = {'variety': variety, 'order_id': order_id}
            if parent_order_id:
                params['parent_order_id'] = parent_order_id
            
            order_id = self.kite.cancel_order(**params)
            logger.info(f"Order cancelled: {order_id}")
            return order_id
        except Exception as e:
            logger.error(f"Failed to cancel order: {e}")
            return None
    
    def get_orders(self):
        """Get all orders"""
        try:
            return self.kite.orders()
        except Exception as e:
            logger.error(f"Failed to get orders: {e}")
            return []
    
    def get_positions(self):
        """Get current positions"""
        try:
            return self.kite.positions()
        except Exception as e:
            logger.error(f"Failed to get positions: {e}")
            return {'day': [], 'net': []}
    
    def get_holdings(self):
        """Get holdings"""
        try:
            return self.kite.holdings()
        except Exception as e:
            logger.error(f"Failed to get holdings: {e}")
            return []
    
    def get_margins(self):
        """Get available margins"""
        try:
            return self.kite.margins()
        except Exception as e:
            logger.error(f"Failed to get margins: {e}")
            return {}
    
    def start_websocket(self, api_key, access_token, on_ticks, on_connect=None, on_close=None):
        """Start WebSocket for live market data"""
        self.on_ticks_callback = on_ticks
        self.on_connect_callback = on_connect
        self.on_close_callback = on_close
        
        self.ticker = KiteTicker(api_key, access_token)
        self.ticker.on_ticks = self._on_ticks
        self.ticker.on_connect = self._on_connect
        self.ticker.on_close = self._on_close
        self.ticker.on_error = self._on_error
        self.ticker.on_reconnect = self._on_reconnect
        self.ticker.on_noreconnect = self._on_noreconnect
        
        self.ticker.connect()
    
    def _on_ticks(self, ws, ticks):
        """Handle incoming ticks"""
        for tick in ticks:
            token = tick['instrument_token']
            self.live_data[token] = {
                'last_price': tick.get('last_price', 0),
                'volume': tick.get('volume_traded', 0),
                'buy_quantity': tick.get('buy_quantity', 0),
                'sell_quantity': tick.get('sell_quantity', 0),
                'ohlc': tick.get('ohlc', {}),
                'timestamp': tick.get('timestamp', pd.Timestamp.now())
            }
        
        if self.on_ticks_callback:
            self.on_ticks_callback(ticks)
    
    def _on_connect(self, ws, response):
        """Handle WebSocket connection"""
        logger.info("WebSocket connected")
        if self.subscribed_tokens:
            self.ticker.subscribe(self.subscribed_tokens)
            self.ticker.set_mode(self.ticker.MODE_FULL, self.subscribed_tokens)
        if self.on_connect_callback:
            self.on_connect_callback(response)
    
    def _on_close(self, ws, code, reason):
        """Handle WebSocket close"""
        logger.info(f"WebSocket closed: {code} - {reason}")
        if self.on_close_callback:
            self.on_close_callback(code, reason)
    
    def _on_error(self, ws, code, reason):
        """Handle WebSocket error"""
        logger.error(f"WebSocket error: {code} - {reason}")
    
    def _on_reconnect(self, ws, attempt_count):
        """Handle WebSocket reconnect"""
        logger.info(f"WebSocket reconnecting... Attempt {attempt_count}")
    
    def _on_noreconnect(self, ws):
        """Handle WebSocket no reconnect"""
        logger.error("WebSocket could not reconnect")
    
    def subscribe(self, tokens):
        """Subscribe to instrument tokens"""
        self.subscribed_tokens.update(tokens)
        if self.ticker and self.ticker.is_connected():
            self.ticker.subscribe(list(tokens))
            self.ticker.set_mode(self.ticker.MODE_FULL, list(tokens))
    
    def unsubscribe(self, tokens):
        """Unsubscribe from instrument tokens"""
        self.subscribed_tokens.difference_update(tokens)
        if self.ticker and self.ticker.is_connected():
            self.ticker.unsubscribe(list(tokens))
    
    def stop_websocket(self):
        """Stop WebSocket connection"""
        if self.ticker:
            self.ticker.close()
