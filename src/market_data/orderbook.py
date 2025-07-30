# Market_data/orderbook.py 

class OrderBook:
    def __init__(self, symbol):
        self.symbol = symbol
        self.bids = {} # price: size 
        self.asks = {}
        self.last_midprice = None
        self.price_history = []

    def update(self, msg):
        """Process Binance depth@1000ms L2 Update"""
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
        best_bid = max(self.bids.keys(), default=None)
        best_ask = min(self.asks.keys(), default=None)
        if best_bid is not None and best_ask is not None:
            mid = (best_bid + best_ask) / 2
            self.price_history.append(mid)
            if len(self.price_history) > 100:
                self.price_history.pop(0)

    def get_midprice(self):
        return self.last_midprice or 0.0
    
    def get_level_size(self, price, side):
        book = self.bids if side == 'bid' else self.asks
        return book.get(price, 0.0)
    

    def get_estimated_volume(self, side):
        book = self.bids if side == 'bid' else self.asks
        return sum(book.values())

    def get_volatility_estimate(self):
        if len(self.price_history) < 2:
            return 0.001
        returns = [
            (self.price_history[i] - self.price_history[i-1]) / self.price_history[i-1]
            for i in range (1, len(self.price_history))
        ]
        variance = sum( r ** 2 for r in returns ) / len(returns)
        return variance ** 0.5