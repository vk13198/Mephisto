import threading
import time
from datetime import datetime
from collections import deque

from models.database import Tick
from models import db

class TickPersister:
    """Background batched persister for incoming ticks.

    Usage:
      persister = TickPersister(app, flush_interval=1.0, batch_size=200)
      persister.start()
      persister.enqueue(symbol, token, price, volume, timestamp)
    """
    def __init__(self, app, flush_interval=1.0, batch_size=200):
        self.app = app
        self.flush_interval = float(flush_interval)
        self.batch_size = int(batch_size)
        self._queue = deque()
        self._lock = threading.Lock()
        self._running = False
        self._thread = None

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=2.0)
        # flush remaining
        self._flush()

    def enqueue(self, symbol, token, price, volume=None, timestamp=None):
        with self._lock:
            self._queue.append((symbol, str(token) if token is not None else None, price, volume, timestamp))

    def _run(self):
        while self._running:
            try:
                time.sleep(self.flush_interval)
                self._flush()
            except Exception:
                # swallow exceptions to keep thread alive
                pass

    def _flush(self):
        items = []
        with self._lock:
            while self._queue and len(items) < self.batch_size:
                items.append(self._queue.popleft())
        if not items:
            return

        # write batch inside app context
        try:
            with self.app.app_context():
                objs = []
                now = datetime.utcnow()
                for sym, tok, price, vol, ts in items:
                    ts_val = ts if ts is not None else now
                    objs.append(Tick(symbol=sym or str(tok), token=tok, price=price or 0.0, volume=vol, timestamp=ts_val))
                try:
                    db.session.bulk_save_objects(objs)
                    db.session.commit()
                except Exception:
                    # fallback to individual insert
                    for o in objs:
                        try:
                            db.session.add(o)
                            db.session.commit()
                        except Exception:
                            db.session.rollback()
        except Exception:
            pass
