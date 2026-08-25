import json
import logging
import threading
import time
from websocket import create_connection, WebSocketConnectionClosedException

logger = logging.getLogger(__name__)

class FinnhubAdapter:
    """Simple Finnhub WebSocket adapter.

    Usage:
      adapter = FinnhubAdapter(api_key, on_ticks=callable)
      adapter.start()
      adapter.subscribe('AAPL')
      adapter.stop()

    Notes:
    - Uses websocket-client create_connection in a background thread.
    - For stability, the adapter reconnects on error with backoff.
    - Finnhub messages: {"type":"trade","data":[{...}]}
    """
    def __init__(self, api_key, on_ticks=None):
        self.api_key = api_key
        self.ws_url = f"wss://ws.finnhub.io?token={api_key}"
        self.on_ticks = on_ticks
        self._stop = threading.Event()
        self._thread = None
        self._ws = None
        self._subscriptions = set()
        self._lock = threading.Lock()

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        try:
            if self._ws:
                self._ws.close()
        except Exception:
            pass
        if self._thread:
            self._thread.join(timeout=2.0)

    def subscribe(self, symbol):
        with self._lock:
            if symbol in self._subscriptions:
                return
            self._subscriptions.add(symbol)
        if self._ws:
            try:
                msg = json.dumps({"type": "subscribe", "symbol": symbol})
                self._ws.send(msg)
            except Exception:
                pass

    def unsubscribe(self, symbol):
        with self._lock:
            if symbol in self._subscriptions:
                self._subscriptions.discard(symbol)
        if self._ws:
            try:
                msg = json.dumps({"type": "unsubscribe", "symbol": symbol})
                self._ws.send(msg)
            except Exception:
                pass

    def _run(self):
        backoff = 1
        while not self._stop.is_set():
            try:
                self._ws = create_connection(self.ws_url)
                logger.info("Finnhub WebSocket connected")

                # re-subscribe
                with self._lock:
                    for sym in list(self._subscriptions):
                        try:
                            self._ws.send(json.dumps({"type": "subscribe", "symbol": sym}))
                        except Exception:
                            pass

                backoff = 1
                while not self._stop.is_set():
                    try:
                        raw = self._ws.recv()
                        if not raw:
                            continue
                        msg = json.loads(raw)
                        if msg.get('type') == 'trade' and 'data' in msg:
                            trades = msg['data']
                            ticks = []
                            for t in trades:
                                # finnhub trade has s (symbol), p (price), t (timestamp ms), v (volume)
                                ticks.append({
                                    'symbol': t.get('s'),
                                    'last_price': t.get('p'),
                                    'volume': t.get('v'),
                                    'timestamp': datetime_from_ms(t.get('t'))
                                })
                            if self.on_ticks:
                                try:
                                    self.on_ticks(ticks)
                                except Exception:
                                    pass
                    except WebSocketConnectionClosedException:
                        logger.warning('Finnhub websocket closed, reconnecting')
                        break
                    except Exception as e:
                        logger.error(f'Error reading Finnhub websocket: {e}')
                        break
            except Exception as e:
                logger.error(f'Finnhub connection error: {e}')

            # reconnect backoff
            time.sleep(backoff)
            backoff = min(backoff * 2, 60)


def datetime_from_ms(ms):
    try:
        import datetime as _dt
        return _dt.datetime.utcfromtimestamp(ms / 1000.0).isoformat()
    except Exception:
        return None
