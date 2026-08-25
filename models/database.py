from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()

class Trade(db.Model):
    __tablename__ = 'trades'
    
    id = db.Column(db.Integer, primary_key=True)
    symbol = db.Column(db.String(20), nullable=False)
    trade_type = db.Column(db.String(10), nullable=False)  # LONG or SHORT
    entry_price = db.Column(db.Float, nullable=False)
    exit_price = db.Column(db.Float, nullable=True)
    quantity = db.Column(db.Integer, nullable=False)
    stop_loss = db.Column(db.Float, nullable=False)
    take_profit_1 = db.Column(db.Float, nullable=False)
    take_profit_2 = db.Column(db.Float, nullable=True)
    take_profit_3 = db.Column(db.Float, nullable=True)
    status = db.Column(db.String(20), default='OPEN')  # OPEN, CLOSED, PARTIAL
    entry_time = db.Column(db.DateTime, default=datetime.now)
    exit_time = db.Column(db.DateTime, nullable=True)
    pnl = db.Column(db.Float, default=0.0)
    brokerage = db.Column(db.Float, default=0.0)
    net_pnl = db.Column(db.Float, default=0.0)
    is_paper = db.Column(db.Boolean, default=True)
    strategy_signal = db.Column(db.String(50), default='PRIMARY')
    
    def to_dict(self):
        return {
            'id': self.id,
            'symbol': self.symbol,
            'trade_type': self.trade_type,
            'entry_price': self.entry_price,
            'exit_price': self.exit_price,
            'quantity': self.quantity,
            'stop_loss': self.stop_loss,
            'take_profit_1': self.take_profit_1,
            'status': self.status,
            'entry_time': self.entry_time.isoformat() if self.entry_time else None,
            'exit_time': self.exit_time.isoformat() if self.exit_time else None,
            'pnl': self.pnl,
            'brokerage': self.brokerage,
            'net_pnl': self.net_pnl,
            'is_paper': self.is_paper
        }

class Portfolio(db.Model):
    __tablename__ = 'portfolio'
    
    id = db.Column(db.Integer, primary_key=True)
    cash = db.Column(db.Float, default=100000)
    total_value = db.Column(db.Float, default=100000)
    margin_used = db.Column(db.Float, default=0.0)
    day_pnl = db.Column(db.Float, default=0.0)
    total_pnl = db.Column(db.Float, default=0.0)
    updated_at = db.Column(db.DateTime, default=datetime.now)
    
class DailySummary(db.Model):
    __tablename__ = 'daily_summary'
    
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, nullable=False, unique=True)
    starting_equity = db.Column(db.Float, nullable=False)
    ending_equity = db.Column(db.Float, nullable=False)
    total_trades = db.Column(db.Integer, default=0)
    winning_trades = db.Column(db.Integer, default=0)
    losing_trades = db.Column(db.Integer, default=0)
    gross_pnl = db.Column(db.Float, default=0.0)
    total_brokerage = db.Column(db.Float, default=0.0)
    net_pnl = db.Column(db.Float, default=0.0)
    max_drawdown = db.Column(db.Float, default=0.0)
    circuit_breaker = db.Column(db.Boolean, default=False)
    
class SignalLog(db.Model):
    __tablename__ = 'signal_logs'
    
    id = db.Column(db.Integer, primary_key=True)
    symbol = db.Column(db.String(20), nullable=False)
    signal_type = db.Column(db.String(10), nullable=False)
    price = db.Column(db.Float, nullable=False)
    score = db.Column(db.Integer, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.now)
    details = db.Column(db.Text, nullable=True)
    executed = db.Column(db.Boolean, default=False)
