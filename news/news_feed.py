import logging
import requests
import feedparser
from datetime import datetime, timedelta
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

class NewsFeed:
    def __init__(self, config):
        self.config = config
        self.news_api_key = config.NEWS_API_KEY
        self.cache = []
        self.last_fetch = None
        self.cache_duration = timedelta(minutes=5)
        
        # RSS feeds for Indian markets
        self.rss_feeds = [
            'https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms',
            'https://www.moneycontrol.com/rss/latestnews.xml',
            'https://www.business-standard.com/rss/markets-106.rss',
            'https://feeds.feedburner.com/nseindia/ann',
        ]
    
    def get_market_news(self, limit=20):
        """Get latest market news"""
        try:
            # Check cache
            if self.last_fetch and datetime.now() - self.last_fetch < self.cache_duration:
                return self.cache[:limit]
            
            news_items = []
            
            # Try NewsAPI first
            if self.news_api_key:
                news_items.extend(self._fetch_newsapi())
            
            # Fallback to RSS feeds
            if not news_items:
                news_items.extend(self._fetch_rss())
            
            # Sort by time and cache
            news_items.sort(key=lambda x: x.get('published', ''), reverse=True)
            self.cache = news_items
            self.last_fetch = datetime.now()
            
            return news_items[:limit]
            
        except Exception as e:
            logger.error(f"Failed to fetch news: {e}")
            return self.cache[:limit] if self.cache else []
    
    def _fetch_newsapi(self):
        """Fetch from NewsAPI"""
        try:
            url = "https://newsapi.org/v2/everything"
            params = {
                'q': 'NSE OR BSE OR Nifty OR Sensex OR Indian stock market',
                'language': 'en',
                'sortBy': 'publishedAt',
                'pageSize': 20,
                'apiKey': self.news_api_key
            }
            
            response = requests.get(url, params=params, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                articles = data.get('articles', [])
                
                return [{
                    'title': article.get('title', ''),
                    'description': article.get('description', ''),
                    'url': article.get('url', ''),
                    'source': article.get('source', {}).get('name', 'Unknown'),
                    'published': article.get('publishedAt', ''),
                    'image': article.get('urlToImage', '')
                } for article in articles]
            
        except Exception as e:
            logger.error(f"NewsAPI error: {e}")
        
        return []
    
    def _fetch_rss(self):
        """Fetch from RSS feeds"""
        news_items = []
        
        for feed_url in self.rss_feeds:
            try:
                feed = feedparser.parse(feed_url)
                
                for entry in feed.entries[:10]:
                    news_items.append({
                        'title': entry.get('title', ''),
                        'description': self._clean_html(entry.get('summary', '')),
                        'url': entry.get('link', ''),
                        'source': feed.feed.get('title', 'RSS'),
                        'published': entry.get('published', ''),
                        'image': ''
                    })
                    
            except Exception as e:
                logger.error(f"RSS fetch error for {feed_url}: {e}")
        
        return news_items
    
    def _clean_html(self, html_text):
        """Remove HTML tags from text"""
        if not html_text:
            return ''
        soup = BeautifulSoup(html_text, 'lxml')
        return soup.get_text(separator=' ', strip=True)[:200] + '...'
    
    def get_sentiment_summary(self):
        """Get market sentiment based on recent news"""
        news = self.get_market_news(limit=10)
        
        if not news:
            return {'sentiment': 'NEUTRAL', 'score': 0, 'headlines': []}
        
        # Simple keyword-based sentiment
        positive_keywords = ['surge', 'rally', 'gain', 'rise', 'up', 'bullish', 'growth', 'profit', 'high']
        negative_keywords = ['fall', 'drop', 'crash', 'decline', 'down', 'bearish', 'loss', 'low', 'sell']
        
        sentiment_score = 0
        headlines = []
        
        for item in news[:5]:
            title_lower = item['title'].lower()
            pos_count = sum(1 for word in positive_keywords if word in title_lower)
            neg_count = sum(1 for word in negative_keywords if word in title_lower)
            
            sentiment_score += (pos_count - neg_count)
            headlines.append(item['title'])
        
        if sentiment_score > 2:
            sentiment = 'POSITIVE'
        elif sentiment_score < -2:
            sentiment = 'NEGATIVE'
        else:
            sentiment = 'NEUTRAL'
        
        return {
            'sentiment': sentiment,
            'score': sentiment_score,
            'headlines': headlines
        }
