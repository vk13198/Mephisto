import logging
import requests
import json
from datetime import datetime

logger = logging.getLogger(__name__)

class AIAssistant:
    def __init__(self, config):
        self.config = config
        self.model = config.AI_MODEL
        self.hf_api_key = config.HF_API_KEY
        self.openrouter_key = config.OPENROUTER_API_KEY
        self.conversation_history = []
        self.max_history = 10
    
    def ask(self, question, context=None):
        """Ask the AI assistant a question"""
        try:
            # Build system prompt with trading context
            system_prompt = self._build_system_prompt(context)
            
            # Build messages
            messages = [
                {"role": "system", "content": system_prompt},
            ]
            
            # Add conversation history
            for msg in self.conversation_history[-self.max_history:]:
                messages.append(msg)
            
            # Add current question
            messages.append({"role": "user", "content": question})
            
            # Get response based on configured model
            if self.model == 'huggingface' and self.hf_api_key:
                response = self._call_huggingface(messages)
            elif self.model == 'openrouter' and self.openrouter_key:
                response = self._call_openrouter(messages)
            else:
                response = self._local_response(question, context)
            
            # Store in history
            self.conversation_history.append({"role": "user", "content": question})
            self.conversation_history.append({"role": "assistant", "content": response})
            
            return response
            
        except Exception as e:
            logger.error(f"AI Assistant error: {e}")
            return self._local_response(question, context)
    
    def _build_system_prompt(self, context):
        """Build system prompt with trading context"""
        prompt = """You are an expert Indian stock market trading assistant. You specialize in:
- Smart Money Concepts (SMC) and Price Action
- Technical analysis for NSE/BSE
- Risk management and position sizing
- Zerodha Kite platform operations
- Indian market regulations and taxation

Key facts about Indian markets:
- Market hours: 9:15 AM - 3:30 PM IST (Monday-Friday)
- Major indices: NIFTY 50, NIFTY Bank, SENSEX
- Currency: Indian Rupee (INR)
- Settlement: T+1 for equities
- STT: 0.025% for intraday sell, 0.1% for delivery
- GST: 18% on brokerage

Current context: """
        
        if context:
            prompt += json.dumps(context, indent=2)
        else:
            prompt += "No active trades"
        
        return prompt
    
    def _call_huggingface(self, messages):
        """Call Hugging Face Inference API"""
        try:
            # Using a free model like Mistral or Llama
            api_url = "https://api-inference.huggingface.co/models/mistralai/Mistral-7B-Instruct-v0.2"
            headers = {"Authorization": f"Bearer {self.hf_api_key}"}
            
            # Format for instruction model
            prompt = self._format_messages_for_hf(messages)
            
            payload = {
                "inputs": prompt,
                "parameters": {
                    "max_new_tokens": 500,
                    "temperature": 0.7,
                    "return_full_text": False
                }
            }
            
            response = requests.post(api_url, headers=headers, json=payload, timeout=30)
            
            if response.status_code == 200:
                result = response.json()
                if isinstance(result, list) and len(result) > 0:
                    return result[0].get('generated_text', 'No response generated')
            
            logger.warning(f"HF API returned status {response.status_code}")
            return self._local_response(messages[-1]['content'])
            
        except Exception as e:
            logger.error(f"HF API error: {e}")
            return self._local_response(messages[-1]['content'])
    
    def _call_openrouter(self, messages):
        """Call OpenRouter API (free models available)"""
        try:
            api_url = "https://openrouter.ai/api/v1/chat/completions"
            headers = {
                "Authorization": f"Bearer {self.openrouter_key}",
                "HTTP-Referer": "http://localhost:5000",
                "X-Title": "Indian Trading Bot"
            }
            
            payload = {
                "model": "mistralai/mistral-7b-instruct:free",
                "messages": messages,
                "max_tokens": 500,
                "temperature": 0.7
            }
            
            response = requests.post(api_url, headers=headers, json=payload, timeout=30)
            
            if response.status_code == 200:
                result = response.json()
                return result['choices'][0]['message']['content']
            
            logger.warning(f"OpenRouter returned status {response.status_code}")
            return self._local_response(messages[-1]['content'])
            
        except Exception as e:
            logger.error(f"OpenRouter error: {e}")
            return self._local_response(messages[-1]['content'])
    
    def _format_messages_for_hf(self, messages):
        """Format messages for Hugging Face instruction model"""
        prompt = ""
        for msg in messages:
            if msg['role'] == 'system':
                prompt += f"<s>[INST] {msg['content']} [/INST]</s>\n"
            elif msg['role'] == 'user':
                prompt += f"<s>[INST] {msg['content']} [/INST]</s>\n"
            else:
                prompt += f"{msg['content']}\n"
        return prompt
    
    def _local_response(self, question, context=None):
        """Generate local response when APIs are unavailable"""
        question_lower = question.lower()
        
        # Common trading questions
        if 'stop loss' in question_lower or 'sl' in question_lower:
            return """Stop Loss (SL) is crucial for risk management. In this bot:
- SL is placed at the swing low/high minus ATR buffer
- For longs: Below the leg low or micro low
- For shorts: Above the leg high or micro high
- Trailing stop activates after 1.5R profit using ATR Chandelier
- Always set your SL immediately after entry in Zerodha Kite

Recommended: Risk only 0.5-1% of capital per trade."""
        
        elif 'take profit' in question_lower or 'tp' in question_lower or 'target' in question_lower:
            return """This strategy uses 3 profit targets:
- TP1 (50% position): 1R (1x risk distance) - Lock in profits
- TP2 (30% position): 0.272 Fib extension or 1.618R
- TP3 (20% position): 0.618 Fib extension - Let it run with trailing stop

The runner (remaining position) uses ATR-based trailing stop to capture big moves."""
        
        elif 'smc' in question_lower or 'smart money' in question_lower:
            return """Smart Money Concepts (SMC) used in this bot:
1. **Structure**: Identifies swing highs/lows and CHOCH (Change of Character)
2. **Order Blocks (OB)**: Last opposite candle before impulsive move
3. **Fair Value Gaps (FVG)**: Imbalance zones where price may return
4. **Liquidity Sweeps**: Wick beyond previous swing point, then reversal
5. **Golden Zone**: 0.5 - 0.618 Fibonacci retracement of the active leg

The bot waits for price to return to the golden zone with confluence before entering."""
        
        elif 'risk' in question_lower or 'money management' in question_lower:
            return """Risk Management Rules:
- Max 0.7% risk per trade (configurable)
- Max 4 trades per day
- Daily circuit breaker at 2% loss
- Position size = (Capital × Risk%) / (Entry - SL)
- Brokerage calculated as per Zerodha (0.03% or Rs 20 max)

Example: Rs 1,00,000 capital, 0.7% risk = Rs 700 max loss per trade.
If entry is 100 and SL is 98 (Rs 2 risk), buy 350 shares."""
        
        elif 'brokerage' in question_lower or 'charges' in question_lower or 'fees' in question_lower:
            return """Zerodha-like Brokerage Structure:
- Brokerage: 0.03% per order or Rs 20 (whichever is lower)
- STT: 0.025% on sell side (intraday)
- Exchange charges: 0.00325% (NSE)
- GST: 18% on (brokerage + exchange charges)
- SEBI: Rs 10 per crore
- Stamp duty: ~0.003% (state dependent)

For a Rs 50,000 trade:
- Buy: ~Rs 15-20 total charges
- Sell: ~Rs 20-25 total charges (includes STT)"""
        
        elif 'paper trading' in question_lower:
            return """Paper Trading Mode:
- Simulates real trades with live market prices
- Uses actual Zerodha brokerage calculations
- Tracks P&L, drawdown, and win rate
- Runs 24/7 even when you're offline
- Switch to live trading only after 30+ days of profitable paper trading

To go live: Set PAPER_TRADING=false and LIVE_TRADING=true in .env, and ensure valid Zerodha access tokens."""
        
        elif 'nifty' in question_lower or 'bank nifty' in question_lower:
            return """NIFTY 50 & BANKNIFTY:
- **NIFTY 50**: Top 50 companies, most liquid
- **BANKNIFTY**: Top banking stocks, high volatility
- Lot sizes vary (check current on NSE website)
- Best for intraday due to liquidity and tight spreads
- This bot works best on 5-minute and 15-minute timeframes

Note: For indices, use futures or options as per your risk appetite."""
        
        elif 'when to trade' in question_lower or 'best time' in question_lower:
            return """Best Trading Times (IST):
- **9:15 - 9:30 AM**: Opening volatility - AVOID (gap risk)
- **9:30 - 11:30 AM**: Best for trend setups
- **11:30 AM - 1:30 PM**: Slow, avoid unless strong setup
- **1:30 - 3:00 PM**: Second best session
- **3:00 - 3:30 PM**: Closing moves - AVOID for new entries

The bot can be configured to avoid Monday first hour and Friday last hour."""
        
        elif 'circuit breaker' in question_lower or 'daily loss' in question_lower:
            return """Daily Loss Circuit Breaker:
- Automatically stops trading if daily loss exceeds 2%
- Resets at market open next day
- Protects capital during bad market days
- Can be adjusted in settings (0.5% to 10%)

This is a crucial safety feature - never disable it without experience."""
        
        else:
            return f"""I'm your Indian market trading assistant. I can help with:
- Smart Money Concepts and strategy explanation
- Risk management and position sizing
- Zerodha brokerage and charges
- Market timing and best practices
- Stop loss and take profit strategies
- Paper vs Live trading guidance

Your question: "{question}"

Please ask something specific about trading, and I'll provide detailed guidance!"""
    
    def clear_history(self):
        """Clear conversation history"""
        self.conversation_history = []
        return "Conversation history cleared."
