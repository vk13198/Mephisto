import logging
import math
from datetime import datetime
from models import db, Trade, Portfolio, DailySummary

logger = logging.getLogger(__name__)

class PaperTradingEngine:
    def __init__(self, config):
        self.config = config
        self.initial_capital = config.INITIAL_CAPITAL
        self.setup_portfolio()
    
    def setup_portfolio(self):
        """Initialize or load portfolio"""
        portfolio = Portfolio.query.first()
        if not portfolio:
            portfolio = Portfolio(
                cash=self.initial_capital,
                total_value=self.initial_capital,
                margin_used=0.0,
                day_pnl=0.0,
                total_pnl=0.0,
                updated_at=datetime.now()
            )
            db.session.add(portfolio)
            db.session.commit()
        return portfolio
    
    def calculate_brokerage(self, trade_value, is_buy=True, is_intraday=True):
        """
        Calculate brokerage and taxes as per Zerodha-like structure
        """
        turnover = trade_value
        
        # Brokerage (0.03% or Rs 20 per order, whichever is lower)
        brokerage = min(turnover * (self.config.BROKERAGE_PERCENT / 100), self.config.BROKERAGE_MAX)
        
        # STT (Securities Transaction Tax)
        # Intraday: 0.025% on sell side only
        # Delivery: 0.1% on both sides
        if is_intraday:
            stt = turnover * (self.config.STT_PERCENT / 100) if not is_buy else 0
        else:
            stt = turnover * (self.config.STT_DELIVERY / 100)
        
        # Exchange Transaction Charges (NSE: 0.00325%)
        txn_charge = turnover * self.config.EXCHANGE_TXN_CHARGE
        
        # SEBI Charges (Rs 10 per crore = 0.0001%)
        sebi_charge = turnover * 0.0001
        
        # Stamp Duty (varies by state, approx 0.003% on buy)
        stamp_duty = turnover * (self.config.STAMP_DUTY / 100) if is_buy else 0
        
        # GST (18% on brokerage + transaction charges)
        gst = (brokerage + txn_charge) * (self.config.GST_PERCENT / 100)
        
        total_charges = brokerage + stt + txn_charge + sebi_charge + stamp_duty + gst
        
        return {
            'brokerage': round(brokerage, 2),
            'stt': round(stt, 2),
            'txn_charge': round(txn_charge, 2),
            'sebi_charge': round(sebi_charge, 2),
            'stamp_duty': round(stamp_duty, 2),
            'gst': round(gst, 2),
            'total': round(total_charges, 2)
        }
    
    def execute_entry(self, signal, is_paper=True):
        """Execute entry order"""
        try:
            portfolio = Portfolio.query.first()
            if not portfolio:
                portfolio = self.setup_portfolio()
            
            # Check if we have enough capital
            required_margin = signal['price'] * signal['quantity']
            if portfolio.cash < required_margin:
                logger.warning(f"Insufficient funds. Required: {required_margin}, Available: {portfolio.cash}")
                return None
            
            # Calculate entry brokerage
            trade_value = signal['price'] * signal['quantity']
            charges = self.calculate_brokerage(trade_value, is_buy=True, is_intraday=True)
            
            # Create trade record
            trade = Trade(
                symbol=signal['symbol'],
                trade_type=signal['type'],
                entry_price=signal['price'],
                quantity=signal['quantity'],
                stop_loss=signal['stop_loss'],
                take_profit_1=signal['take_profit_1'],
                take_profit_2=signal.get('take_profit_2'),
                take_profit_3=signal.get('take_profit_3'),
                status='OPEN',
                entry_time=datetime.now(),
                brokerage=charges['total'],
                is_paper=is_paper,
                strategy_signal='CONTINUATION' if signal.get('is_continuation') else 'PRIMARY'
            )
            
            db.session.add(trade)
            
            # Update portfolio
            portfolio.cash -= (required_margin + charges['total'])
            portfolio.margin_used += required_margin
            portfolio.updated_at = datetime.now()
            
            db.session.commit()
            
            logger.info(f"Entry executed: {signal['type']} {signal['symbol']} @ {signal['price']} "
                       f"Qty: {signal['quantity']} SL: {signal['stop_loss']} TP1: {signal['take_profit_1']}")
            
            return trade
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"Failed to execute entry: {e}")
            return None
    
    def execute_exit(self, trade_id, exit_price, exit_type='MARKET', partial_qty=None):
        """Execute exit order"""
        try:
            trade = Trade.query.get(trade_id)
            if not trade or trade.status == 'CLOSED':
                return None
            
            portfolio = Portfolio.query.first()
            if not portfolio:
                return None
            
            # Calculate exit quantity
            exit_qty = partial_qty if partial_qty else trade.quantity
            
            # Calculate P&L
            if trade.trade_type == 'LONG':
                pnl = (exit_price - trade.entry_price) * exit_qty
            else:
                pnl = (trade.entry_price - exit_price) * exit_qty
            
            # Calculate exit brokerage
            trade_value = exit_price * exit_qty
            charges = self.calculate_brokerage(trade_value, is_buy=False, is_intraday=True)
            
            net_pnl = pnl - charges['total']
            
            # Update trade
            if partial_qty and partial_qty < trade.quantity:
                trade.status = 'PARTIAL'
                trade.quantity -= exit_qty
                trade.pnl += pnl
                trade.brokerage += charges['total']
                trade.net_pnl += net_pnl
            else:
                trade.status = 'CLOSED'
                trade.exit_price = exit_price
                trade.exit_time = datetime.now()
                trade.pnl += pnl
                trade.brokerage += charges['total']
                trade.net_pnl += net_pnl
            
            # Update portfolio
            margin_released = trade.entry_price * exit_qty
            portfolio.cash += (margin_released + pnl - charges['total'])
            portfolio.margin_used -= margin_released
            portfolio.day_pnl += net_pnl
            portfolio.total_pnl += net_pnl
            portfolio.total_value = portfolio.cash + portfolio.margin_used
            portfolio.updated_at = datetime.now()
            
            db.session.commit()
            
            logger.info(f"Exit executed: {trade.symbol} @ {exit_price} "
                       f"PnL: {pnl:.2f} Net: {net_pnl:.2f} Type: {exit_type}")
            
            return trade
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"Failed to execute exit: {e}")
            return None
    
    def check_stop_loss(self, trade, current_price):
        """Check if stop loss is hit"""
        if trade.trade_type == 'LONG':
            return current_price <= trade.stop_loss
        else:
            return current_price >= trade.stop_loss
    
    def check_take_profit(self, trade, current_price, tp_level=1):
        """Check if take profit is hit"""
        tp_price = getattr(trade, f'take_profit_{tp_level}', None)
        if not tp_price:
            return False
        
        if trade.trade_type == 'LONG':
            return current_price >= tp_price
        else:
            return current_price <= tp_price
    
    def get_open_positions(self):
        """Get all open positions"""
        return Trade.query.filter(Trade.status.in_(['OPEN', 'PARTIAL'])).all()
    
    def get_portfolio_summary(self):
        """Get portfolio summary"""
        portfolio = Portfolio.query.first()
        if not portfolio:
            portfolio = self.setup_portfolio()
        
        open_trades = self.get_open_positions()
        total_open_pnl = sum(t.pnl for t in open_trades)
        
        today_trades = Trade.query.filter(
            db.func.date(Trade.entry_time) == datetime.now().date()
        ).all()
        
        return {
            'cash': round(portfolio.cash, 2),
            'total_value': round(portfolio.total_value, 2),
            'margin_used': round(portfolio.margin_used, 2),
            'day_pnl': round(portfolio.day_pnl, 2),
            'total_pnl': round(portfolio.total_pnl, 2),
            'open_positions': len(open_trades),
            'open_pnl': round(total_open_pnl, 2),
            'today_trades': len(today_trades),
            'initial_capital': self.initial_capital,
            'returns_pct': round(((portfolio.total_value - self.initial_capital) / self.initial_capital) * 100, 2)
        }
    
    def update_daily_summary(self):
        """Update daily summary"""
        today = datetime.now().date()
        summary = DailySummary.query.filter_by(date=today).first()
        
        if not summary:
            portfolio = Portfolio.query.first()
            summary = DailySummary(
                date=today,
                starting_equity=portfolio.total_value if portfolio else self.initial_capital,
                ending_equity=portfolio.total_value if portfolio else self.initial_capital
            )
            db.session.add(summary)
        
        # Calculate stats
        today_trades = Trade.query.filter(
            db.func.date(Trade.entry_time) == today
        ).all()
        
        summary.total_trades = len(today_trades)
        summary.winning_trades = len([t for t in today_trades if t.net_pnl > 0])
        summary.losing_trades = len([t for t in today_trades if t.net_pnl < 0])
        summary.gross_pnl = sum(t.pnl for t in today_trades)
        summary.total_brokerage = sum(t.brokerage for t in today_trades)
        summary.net_pnl = sum(t.net_pnl for t in today_trades)
        
        portfolio = Portfolio.query.first()
        if portfolio:
            summary.ending_equity = portfolio.total_value
        
        db.session.commit()
        return summary
