@@
-from config import Config
+from config import Config
@@
-zerodha = ZerodhaClient(config.ZERODHA_API_KEY, config.ZERODHA_ACCESS_TOKEN)
-paper_engine = PaperTradingEngine(config)
-market_data = MarketDataManager(config=config, provider=config.MARKET_PROVIDER, zerodha_client=zerodha)
+zerodha = ZerodhaClient(config.ZERODHA_API_KEY, config.ZERODHA_ACCESS_TOKEN)
+paper_engine = PaperTradingEngine(config)
+# Construct MarketDataManager with matching signature
+market_data = MarketDataManager(zerodha_client=zerodha, provider=config.MARKET_PROVIDER, api_key=config.MARKET_API_KEY)
