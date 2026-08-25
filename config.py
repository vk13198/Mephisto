import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    # Flask
    SECRET_KEY = os.getenv('SECRET_KEY', 'your-secret-key-change-this')
    
    # Zerodha API Credentials
    ZERODHA_API_KEY = os.getenv('ZERODHA_API_KEY', '')
    ZERODHA_API_SECRET = os.getenv('ZERODHA_API_SECRET', '')
    ZERODHA_ACCESS_TOKEN = os.getenv('ZERODHA_ACCESS_TOKEN', '')
    
    # Trading Settings
    INITIAL_CAPITAL = float(os.getenv('INITIAL_CAPITAL', '100000'))
    RISK_PERCENT = float(os.getenv('RISK_PERCENT', '0.7'))
    MAX_TRADES_PER_DAY = int(os.getenv('MAX_TRADES_PER_DAY', '4'))
    
    # Market Hours (IST)
    MARKET_OPEN = "09:15"
    MARKET_CLOSE = "15:30"
    
    # Brokerage (Zerodha-like)
    BROKERAGE_PERCENT = 0.03  # 0.03% per order
    BROKERAGE_MAX = 20  # Max Rs 20 per order
    STT_PERCENT = 0.025  # Securities Transaction Tax (sell side only for intraday)
    STT_DELIVERY = 0.1
    EXCHANGE_TXN_CHARGE = 0.00325  # NSE transaction charges
    GST_PERCENT = 18  # 18% on brokerage + transaction charges
    SEBI_CHARGE = 10  # Rs 10 per crore
    STAMP_DUTY = 0.003  # State dependent, approx
    
    # Strategy Settings
    SWING_LENGTH = 5
    MICRO_SWING_LENGTH = 3
    CONT_ZONE_END = 0.786
    CONT_MAX_AGE = 15
    ADX_LENGTH = 14
    ADX_MIN = 20
    MIN_SCORE = 5
    ATR_PERIOD = 14
    TRAIL_ATR_MULT = 1.5
    MAX_DAILY_LOSS_PCT = 2.0
    
    # AI Settings
    AI_MODEL = os.getenv('AI_MODEL', 'huggingface')  # Options: huggingface, openrouter, local
    HF_API_KEY = os.getenv('HF_API_KEY', '')
    OPENROUTER_API_KEY = os.getenv('OPENROUTER_API_KEY', '')
    
    # News
    NEWS_API_KEY = os.getenv('NEWS_API_KEY', '')
    
    # Database
    DATABASE_URL = os.getenv('DATABASE_URL', 'sqlite:///trading_bot.db')
    
    # Mode
    PAPER_TRADING = os.getenv('PAPER_TRADING', 'true').lower() == 'true'
    LIVE_TRADING = os.getenv('LIVE_TRADING', 'false').lower() == 'true'
