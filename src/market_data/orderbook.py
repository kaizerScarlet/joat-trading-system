# Market_data/orderbook.py 

class OrderBook:
    """
    Lightweight L2 Order Book Binance Symbols.
    Tracks bid/ask level and provides midprice, volatility,
    and liquidity metrics
    """
    def __init__(self, symbol):
        """
        Initialize the OrderBook for a specific trading symbol.
        """
        self.symbol = symbol
        self.bids = {} # Bid side: {price-> size} 
        self.asks = {} # Ask side: {price -> size}
        self.last_midprice = None
        self.price_history = [] #Rolling midpoint buffer for volatility estimate

    def update(self, msg):
        """Process Binance depth@1000ms L2 Update
        Updates bid and ask level accordingly.
        :param msg: L2 depth update from Binance WebSocket stream
        """
        for p, q in msg.get("b",[]):
            price = float(p)
            size = float(q)
            if size > 0 :
                self.bids[price] = size
            elif price in self.bids:
                del self.bids[price]

        for p, q in msg.get('a', []):
            price = float(p)
            size = float(q)
            if size > 0:
                self.asks[price] = size
            elif price in self.asks:
                del self.asks[price]

        self._update_midprice()


    def _update_midprice(self):
        """
        Compute the mid price from best bid and best ask, and store in rolling history
        """
        best_bid = max(self.bids.keys(), default=None)
        best_ask = min(self.asks.keys(), default=None)
        if best_bid is not None and best_ask is not None:
            mid = (best_bid + best_ask) / 2
            self.price_history.append(mid)

            #Keep only recent 100 midprices for volatility calculation
            if len(self.price_history) > 100:
                self.price_history.pop(0)

    def get_midprice(self) -> float:
        """
        Returns the last computed midprice or 0.0 if unavailable.
        """
        return self.last_midprice or 0.0
    
    def get_level_size(self, price, side):
        """
        Returns the size available at a given price level and side.

        :param price: Price level to query
        :param side: 'bid' or 'ask'
        :return: Order size at that price
        """
        book = self.bids if side == 'bid' else self.asks
        return book.get(price, 0.0)
    

    def get_estimated_volume(self, side: str) -> float:
        """
        Estimate total volume on a given side of the book.

        :param side: 'bid' or 'ask'
        :return: sum of all sizes on that side
        """
        book = self.bids if side == 'bid' else self.asks
        return sum(book.values())

    def get_volatility_estimate(self) -> float:
        """
        Estimate market volatility using rolling historical midprices.

        :return: standard deviation of returns over recent midprices
        """
        if len(self.price_history) < 2:
            return 0.001 #Minimal Baseline
        returns = [
            (self.price_history[i] - self.price_history[i-1]) / self.price_history[i-1]
            for i in range (1, len(self.price_history))
        ]
        variance = sum( r ** 2 for r in returns ) / len(returns)
        return variance ** 0.5
    

    def get_best_price(self, side: str) -> float:
        """
        Returns the best bid or ask price.

        :param side: 'bid' or 'ask'
        :return: Best price on that side
        """
        if side == 'bid':
            return max(self.bids.keys(), default= 0.0)
        else:
            return min(self.asks.keys(), default = 0.0)
        
    
    def get_tick_size(self) -> float:
        """
        Returns the smallest tick size used for symbol.
        can be hard coded or dynamically adjusted in the future

        :return: Tick size (default 0.01, for BTCUSDT)
        """
        return 0.01 #Customize or infer dynamically later