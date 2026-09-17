import pytest
from data.market_data import MarketDataManager
from broker.paper_trading import PaperTradingEngine
from config import Config
from app import app
from models import db


def test_marketdata_add_and_tick():
    # run inside app context to ensure any DB-backed components are available
    with app.app_context():
        md = MarketDataManager(zerodha_client=None, max_candles=10)
        # add instrument
        md.add_instrument('TEST', 'SIM1001')
        assert 'SIM1001' in md.candles

        # process a tick
        tick = {'instrument_token': 'SIM1001', 'last_price': 123.45, 'volume_traded': 100}
        md.process_tick(tick)
        latest = md.get_latest_price('SIM1001')
        assert latest == 123.45


def test_paper_engine_setup():
    with app.app_context():
        # Ensure DB tables exist for portfolio creation
        db.create_all()
        cfg = Config()
        pe = PaperTradingEngine(cfg)
        portfolio = pe.setup_portfolio()
        assert portfolio is not None
