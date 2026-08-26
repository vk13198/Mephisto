import os
import logging
import json
from datetime import datetime, timedelta
from threading import Thread
import time

from flask import Flask, render_template, request, jsonify
from flask_socketio import SocketIO, emit
from apscheduler.schedulers.background import BackgroundScheduler

from config import Config
from models import db, Trade, Portfolio, DailySummary, SignalLog
from models.database import persist_tick, get_recent_ticks
from strategy import SMCStrategy
from broker import ZerodhaClient, PaperTradingEngine
from data import MarketDataManager
from ai import AIAssistant
from news import NewsFeed
from services.tick_persister import TickPersister

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('trading_bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Initialize Flask app
app = Flask(__name__)
app.config.from_object(Config)
app.config['SQLALCHEMY_DATABASE_URI'] = Config.DATABASE_URL
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Initialize extensions
db.init_app(app)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

# Global instances
config = Config()
zerodha = ZerodhaClient(config.ZERODHA_API_KEY, config.ZERODHA_ACCESS_TOKEN)
paper_engine = PaperTradingEngine(config)
# Construct MarketDataManager with matching signature
market_data = MarketDataManager(zerodha_client=zerodha, provider=config.MARKET_PROVIDER, api_key=config.MARKET_API_KEY)
ai_assistant = AIAssistant(config)
news_feed = NewsFeed(config)

# Strategy instances per symbol
strategies = {}

# Trading state
bot_running = False
watchlist = [s.strip() for s in config.WATCHLIST.split(',') if s.strip()]
instrument_tokens = {}  # Will be populated from Zerodha or simulated tokens

# Background scheduler
scheduler = BackgroundScheduler()

# Tick persister (buffered DB writes)
tick_persister = TickPersister(app, flush_interval=1.0, batch_size=200)

def init_db():
    """Initialize database tables"""
    with app.app_context():
        db.create_all()
        paper_engine.setup_portfolio()
        logger.info("Database initialized")

def load_instruments():
    """Load instrument tokens from Zerodha or create simulated tokens"""
    global instrument_tokens
    try:
        if zerodha and getattr(zerodha, 'kite', None):
            instruments = zerodha.get_instruments('NSE')
            if instruments is not None and not instruments.empty:
                for symbol in watchlist:
                    match = instruments[instruments['tradingsymbol'] == symbol]
                    if not match.empty:
                        token = match.iloc[0]['instrument_token']
                        instrument_tokens[symbol] = token
                        market_data.add_instrument(symbol, token, base_price=match.iloc[0].get('last_price', None))
        else:
            # create simple simulated tokens
            for i, symbol in enumerate(watchlist, start=1):
                token = f"SIM{1000 + i}"
                instrument_tokens[symbol] = token
                market_data.add_instrument(symbol, token, base_price=None)

        logger.info(f"Loaded {len(instrument_tokens)} instruments")
    except Exception as e:
        logger.error(f"Failed to load instruments: {e}")

def on_ticks(ticks):
    """Handle incoming market ticks"""
    try:
        for tick in ticks:
            # Persist tick to in-memory manager and DB (batched)
            market_data.process_tick(tick)
            token = tick.get('instrument_token')
            price = tick.get('last_price') or tick.get('price')
            symbol = None
            for sym, tok in instrument_tokens.items():
                if str(tok) == str(token):
                    symbol = sym
                    break

            # Enqueue to batched persister (non-blocking)
            try:
                tick_persister.enqueue(symbol or str(token), token, price, volume=tick.get('volume_traded') or tick.get('volume'), timestamp=None)
            except Exception:
                # Fallback to direct DB persist if persister fails
                try:
                    persist_tick(db.session, symbol or str(token), token, price, volume=tick.get('volume_traded') or tick.get('volume'), timestamp=None)
                except Exception:
                    logger.debug('Failed to persist tick to DB')

            if symbol and bot_running:
                process_strategy(symbol, token)

        # Emit to frontend
        socketio.emit('market_tick', {
            'timestamp': datetime.utcnow().isoformat(),
            'ticks': [{k: v for k, v in tick.items() if k != 'depth'} for tick in ticks]
        })

    except Exception as e:
        logger.error(f"Error processing ticks: {e}")

def process_strategy(symbol, token):
    """Process strategy for a symbol"""
    try:
        # Get dataframes
        df_5m = market_data.get_dataframe(token, '5minute', 100)
        df_15m = market_data.get_dataframe(token, '15minute', 100)

        if df_5m.empty or len(df_5m) < 10:
            return

        # Get or create strategy instance
        if symbol not in strategies:
            strategies[symbol] = SMCStrategy(config)

        strategy = strategies[symbol]

        # Get portfolio value
        portfolio = paper_engine.get_portfolio_summary()
        current_equity = portfolio.get('total_value', 0)

        # Analyze for signal
        signal = strategy.analyze(df_5m, df_15m, current_equity)

        if signal:
            logger.info(f"Signal generated: {signal['type']} {symbol} @ {signal['price']}")

            # Log signal
            signal_log = SignalLog(
                symbol=symbol,
                signal_type=signal['type'],
                price=signal['price'],
                score=signal.get('score', 0),
                details=json.dumps(signal.get('details', {})),
                executed=False
            )
            db.session.add(signal_log)
            db.session.commit()

            # Execute paper trade
            if config.PAPER_TRADING:
                trade = paper_engine.execute_entry(signal, is_paper=True)
                if trade:
                    signal_log.executed = True
                    db.session.commit()

                    socketio.emit('new_trade', {
                        'trade': trade.to_dict(),
                        'signal': signal
                    })

            # Execute live trade
            elif config.LIVE_TRADING and getattr(zerodha, 'kite', None):
                # Place order via Zerodha
                variety = 'regular'
                exchange = 'NSE'
                transaction_type = 'BUY' if signal['type'] == 'LONG' else 'SELL'
                order_type = 'MARKET'
                product = 'MIS'  # Intraday

                order_id = zerodha.place_order(
                    variety=variety,
                    exchange=exchange,
                    tradingsymbol=symbol,
                    transaction_type=transaction_type,
                    quantity=signal['quantity'],
                    product=product,
                    order_type=order_type,
                    tag='SMC_BOT'
                )

                if order_id:
                    signal_log.executed = True
                    db.session.commit()

                    # Place SL order
                    sl_transaction = 'SELL' if signal['type'] == 'LONG' else 'BUY'
                    zerodha.place_order(
                        variety='regular',
                        exchange='NSE',
                        tradingsymbol=symbol,
                        transaction_type=sl_transaction,
                        quantity=signal['quantity'],
                        product='MIS',
                        order_type='SL',
                        price=signal['stop_loss'],
                        trigger_price=signal['stop_loss'],
                        tag='SMC_BOT_SL'
                    )

        # Check open positions for exits
        check_position_exits(symbol, token, strategy)

    except Exception as e:
        logger.error(f"Strategy processing error for {symbol}: {e}")

# rest of app.py unchanged (omitted here for brevity)
