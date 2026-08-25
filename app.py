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
from strategy import SMCStrategy
from broker import ZerodhaClient, PaperTradingEngine
from data import MarketDataManager
from ai import AIAssistant
from news import NewsFeed

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
market_data = MarketDataManager(zerodha)
ai_assistant = AIAssistant(config)
news_feed = NewsFeed(config)

# Strategy instances per symbol
strategies = {}

# Trading state
bot_running = False
watchlist = ['NIFTY 50', 'NIFTY BANK', 'RELIANCE', 'TCS', 'INFY']
instrument_tokens = {}  # Will be populated from Zerodha

# Background scheduler
scheduler = BackgroundScheduler()

def init_db():
    """Initialize database tables"""
    with app.app_context():
        db.create_all()
        paper_engine.setup_portfolio()
        logger.info("Database initialized")

def load_instruments():
    """Load instrument tokens from Zerodha"""
    global instrument_tokens
    try:
        instruments = zerodha.get_instruments('NSE')
        if not instruments.empty:
            # Map common symbols to tokens
            for symbol in watchlist:
                match = instruments[instruments['tradingsymbol'] == symbol]
                if not match.empty:
                    instrument_tokens[symbol] = match.iloc[0]['instrument_token']
                    market_data.add_instrument(symbol, match.iloc[0]['instrument_token'])
            
            logger.info(f"Loaded {len(instrument_tokens)} instruments")
    except Exception as e:
        logger.error(f"Failed to load instruments: {e}")

def on_ticks(ticks):
    """Handle incoming market ticks"""
    try:
        for tick in ticks:
            market_data.process_tick(tick)
            
            token = tick['instrument_token']
            symbol = None
            for sym, tok in instrument_tokens.items():
                if tok == token:
                    symbol = sym
                    break
            
            if symbol and bot_running:
                process_strategy(symbol, token)
        
        # Emit to frontend
        socketio.emit('market_tick', {
            'timestamp': datetime.now().isoformat(),
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
        
        if df_5m.empty or len(df_5m) < 50:
            return
        
        # Get or create strategy instance
        if symbol not in strategies:
            strategies[symbol] = SMCStrategy(config)
        
        strategy = strategies[symbol]
        
        # Get portfolio value
        portfolio = paper_engine.get_portfolio_summary()
        current_equity = portfolio['total_value']
        
        # Analyze for signal
        signal = strategy.analyze(df_5m, df_15m, current_equity)
        
        if signal:
            logger.info(f"Signal generated: {signal['type']} {symbol} @ {signal['price']}")
            
            # Log signal
            signal_log = SignalLog(
                symbol=symbol,
                signal_type=signal['type'],
                price=signal['price'],
                score=signal['score'],
                details=json.dumps(signal['details']),
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
            elif config.LIVE_TRADING and zerodha.kite:
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

def check_position_exits(symbol, token, strategy):
    """Check and manage open positions"""
    try:
        open_positions = paper_engine.get_open_positions()
        
        for trade in open_positions:
            if trade.symbol != symbol:
                continue
            
            latest_price = market_data.get_latest_price(token)
            if not latest_price:
                continue
            
            # Check stop loss
            if paper_engine.check_stop_loss(trade, latest_price):
                paper_engine.execute_exit(trade.id, latest_price, 'STOP_LOSS')
                socketio.emit('trade_closed', {
                    'trade_id': trade.id,
                    'exit_price': latest_price,
                    'reason': 'STOP_LOSS'
                })
                continue
            
            # Check TP1
            if trade.status == 'OPEN' and paper_engine.check_take_profit(trade, latest_price, 1):
                # Close 50% position
                exit_qty = trade.quantity // 2
                paper_engine.execute_exit(trade.id, latest_price, 'TP1', exit_qty)
                
                # Move SL to breakeven
                trade.stop_loss = trade.entry_price
                db.session.commit()
                
                socketio.emit('trade_update', {
                    'trade_id': trade.id,
                    'event': 'TP1_HIT',
                    'price': latest_price
                })
                continue
            
            # Check TP2
            if trade.status == 'PARTIAL' and paper_engine.check_take_profit(trade, latest_price, 2):
                # Close 30% of original position (60% of remaining)
                remaining = trade.quantity
                exit_qty = int(remaining * 0.6)
                paper_engine.execute_exit(trade.id, latest_price, 'TP2', exit_qty)
                
                socketio.emit('trade_update', {
                    'trade_id': trade.id,
                    'event': 'TP2_HIT',
                    'price': latest_price
                })
                continue
            
            # Check trailing stop
            position = {
                'type': trade.trade_type,
                'entry_price': trade.entry_price,
                'risk_distance': trade.entry_price - trade.stop_loss if trade.trade_type == 'LONG' else trade.stop_loss - trade.entry_price
            }
            
            trail_stop = strategy.update_trailing_stop(
                market_data.get_dataframe(token, '5minute', 50),
                position
            )
            
            if trail_stop:
                if trade.trade_type == 'LONG' and latest_price <= trail_stop:
                    paper_engine.execute_exit(trade.id, latest_price, 'TRAIL_STOP')
                    socketio.emit('trade_closed', {
                        'trade_id': trade.id,
                        'exit_price': latest_price,
                        'reason': 'TRAIL_STOP'
                    })
                elif trade.trade_type == 'SHORT' and latest_price >= trail_stop:
                    paper_engine.execute_exit(trade.id, latest_price, 'TRAIL_STOP')
                    socketio.emit('trade_closed', {
                        'trade_id': trade.id,
                        'exit_price': latest_price,
                        'reason': 'TRAIL_STOP'
                    })
    
    except Exception as e:
        logger.error(f"Position exit check error: {e}")

def scheduled_tasks():
    """Run scheduled tasks"""
    try:
        # Update daily summary
        paper_engine.update_daily_summary()
        
        # Emit portfolio update
        portfolio = paper_engine.get_portfolio_summary()
        socketio.emit('portfolio_update', portfolio)
        
        # Emit news update
        news = news_feed.get_market_news(limit=5)
        socketio.emit('news_update', news)
        
    except Exception as e:
        logger.error(f"Scheduled task error: {e}")

# Routes
@app.route('/')
def index():
    """Main dashboard"""
    return render_template('index.html')

@app.route('/api/portfolio')
def api_portfolio():
    """Get portfolio summary"""
    return jsonify(paper_engine.get_portfolio_summary())

@app.route('/api/trades')
def api_trades():
    """Get trade history"""
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    
    trades = Trade.query.order_by(Trade.entry_time.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )
    
    return jsonify({
        'trades': [t.to_dict() for t in trades.items],
        'total': trades.total,
        'pages': trades.pages,
        'current_page': page
    })

@app.route('/api/open_positions')
def api_open_positions():
    """Get open positions"""
    positions = paper_engine.get_open_positions()
    return jsonify([p.to_dict() for p in positions])

@app.route('/api/signals')
def api_signals():
    """Get recent signals"""
    signals = SignalLog.query.order_by(SignalLog.timestamp.desc()).limit(50).all()
    return jsonify([{
        'id': s.id,
        'symbol': s.symbol,
        'type': s.signal_type,
        'price': s.price,
        'score': s.score,
        'timestamp': s.timestamp.isoformat(),
        'executed': s.executed
    } for s in signals])

@app.route('/api/news')
def api_news():
    """Get market news"""
    limit = request.args.get('limit', 10, type=int)
    news = news_feed.get_market_news(limit=limit)
    sentiment = news_feed.get_sentiment_summary()
    return jsonify({
        'news': news,
        'sentiment': sentiment
    })

@app.route('/api/ask', methods=['POST'])
def api_ask():
    """Ask AI assistant"""
    data = request.json
    question = data.get('question', '')
    
    # Get current portfolio context
    portfolio = paper_engine.get_portfolio_summary()
    open_positions = paper_engine.get_open_positions()
    
    context = {
        'portfolio': portfolio,
        'open_positions': [p.to_dict() for p in open_positions],
        'mode': 'PAPER' if config.PAPER_TRADING else 'LIVE'
    }
    
    answer = ai_assistant.ask(question, context)
    return jsonify({'answer': answer})

@app.route('/api/bot/start', methods=['POST'])
def api_bot_start():
    """Start the trading bot"""
    global bot_running
    
    if not zerodha.kite:
        return jsonify({'error': 'Zerodha not connected'}), 400
    
    if not instrument_tokens:
        load_instruments()
    
    # Subscribe to instruments
    tokens = list(instrument_tokens.values())
    zerodha.subscribe(tokens)
    
    bot_running = True
    logger.info("Trading bot started")
    
    return jsonify({'status': 'started', 'symbols': list(instrument_tokens.keys())})

@app.route('/api/bot/stop', methods=['POST'])
def api_bot_stop():
    """Stop the trading bot"""
    global bot_running
    bot_running = False
    
    # Unsubscribe from instruments
    tokens = list(instrument_tokens.values())
    zerodha.unsubscribe(tokens)
    
    logger.info("Trading bot stopped")
    return jsonify({'status': 'stopped'})

@app.route('/api/bot/status')
def api_bot_status():
    """Get bot status"""
    return jsonify({
        'running': bot_running,
        'mode': 'PAPER' if config.PAPER_TRADING else 'LIVE',
        'watchlist': list(instrument_tokens.keys()),
        'zerodha_connected': zerodha.kite is not None
    })

@app.route('/api/settings', methods=['GET', 'POST'])
def api_settings():
    """Get/Update settings"""
    if request.method == 'GET':
        return jsonify({
            'initial_capital': config.INITIAL_CAPITAL,
            'risk_percent': config.RISK_PERCENT,
            'max_trades_per_day': config.MAX_TRADES_PER_DAY,
            'swing_length': config.SWING_LENGTH,
            'min_score': config.MIN_SCORE,
            'max_daily_loss_pct': config.MAX_DAILY_LOSS_PCT,
            'paper_trading': config.PAPER_TRADING,
            'live_trading': config.LIVE_TRADING
        })
    
    elif request.method == 'POST':
        data = request.json
        # Note: In production, persist to database or config file
        return jsonify({'status': 'updated'})

@app.route('/api/manual_trade', methods=['POST'])
def api_manual_trade():
    """Place manual trade"""
    data = request.json
    
    signal = {
        'symbol': data.get('symbol'),
        'type': data.get('type', 'LONG'),
        'price': data.get('price'),
        'quantity': data.get('quantity'),
        'stop_loss': data.get('stop_loss'),
        'take_profit_1': data.get('take_profit_1'),
        'take_profit_2': data.get('take_profit_2'),
        'take_profit_3': data.get('take_profit_3'),
        'risk_distance': abs(data.get('price') - data.get('stop_loss')),
        'score': 10,  # Manual override
        'is_continuation': False,
        'strategy': 'MANUAL'
    }
    
    if config.PAPER_TRADING:
        trade = paper_engine.execute_entry(signal, is_paper=True)
        if trade:
            return jsonify({'status': 'success', 'trade': trade.to_dict()})
    
    return jsonify({'error': 'Failed to execute trade'}), 400

# WebSocket events
@socketio.on('connect')
def handle_connect():
    logger.info("Client connected")
    emit('connected', {'status': 'connected', 'timestamp': datetime.now().isoformat()})

@socketio.on('disconnect')
def handle_disconnect():
    logger.info("Client disconnected")

# Initialize
with app.app_context():
    init_db()
    
    # Start scheduler
    scheduler.add_job(scheduled_tasks, 'interval', seconds=30, id='portfolio_update')
    scheduler.start()
    
    # Try to connect to Zerodha if credentials available
    if config.ZERODHA_API_KEY and config.ZERODHA_ACCESS_TOKEN:
        zerodha.connect()
        if zerodha.kite:
            # Start WebSocket in background
            def start_ws():
                zerodha.start_websocket(
                    config.ZERODHA_API_KEY,
                    config.ZERODHA_ACCESS_TOKEN,
                    on_ticks
                )
            
            ws_thread = Thread(target=start_ws)
            ws_thread.daemon = True
            ws_thread.start()
            
            logger.info("WebSocket started")

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=5000, debug=False)
