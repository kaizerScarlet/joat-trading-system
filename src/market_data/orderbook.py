# Market_data/orderbook.py 
from collections import deque
import math
import time
import requests
import logging
from colorama import Fore, Style, init
init(autoreset=True)

logger = logging.getLogger(__name__)

class OrderBook:
    """
    Lightweight L2 Order Book Binance Symbols.
    Tracks bid/ask level and provides midprice, volatility,
    and liquidity metrics
    """
    def __init__(self):
        """
        Initialize the lightweight L2 OrderBook for a specific Binance trading symbol.
        tracks bid/ask levels and provides midprice, volatility,
        depth liquidity, and imbalance metrics
        """
        self.history_len = 100
        self.symbol = "BTCUSDT"
        self.bids = {} # Bid side: {price-> size} 
        self.asks = {} # Ask side: {price -> size}
        self.last_midprice = None
        self.price_history = deque(maxlen=self.history_len) #Rolling midpoint buffer for volatility estimate
        self.last_update_ts = None
        self._tick_size = None  # Cached tick size


    # ------------------------ Updates ------------
    def update(self, msg):
        """Process Binance depth@1000ms L2 Update
        Updates bid and ask level accordingly.
        :param msg: L2 depth update from Binance WebSocket stream
        """
        now = time.time()
        self.last_update_ts = now

        for p, q in msg.get("bid",[]):
            try:
                price = float(p)
                size = float(q)
                if size > 0 :
                    self.bids[price] = size
                elif price in self.bids:
                    del self.bids[price]
            except (ValueError, TypeError):
                continue

        for p, q in msg.get('ask', []):
            try:
                price = float(p)
                size = float(q)
                if size > 0:
                    self.asks[price] = size
                elif price in self.asks:
                    del self.asks[price]
            except (ValueError, TypeError):
                continue

        self._update_midprice()


    def _update_midprice(self):
        """
        Compute the mid price from best bid and best ask, and store in rolling history
        """
        best_bid = max(self.bids.keys(), default=None)
        best_ask = min(self.asks.keys(), default=None)
        if best_bid is not None and best_ask is not None:
            mid = (best_bid + best_ask) / 2
            self.last_midprice = mid
            self.price_history.append(mid)

            #Keep only recent 100 midprices for volatility calculation
            if len(self.price_history) > 100:
                self.price_history.pop(0)

    # ---------------------- Basic Accessors ----------------------------------------
    def get_midprice(self) -> float:
        """
        Returns the last computed midprice or 0.0 if unavailable.
        """
        return self.last_midprice or 0.0
    
    def get_resilient_midprice(self) -> float:
        """
        Returns a safe midprice using fallback hierarchy:
        1. Live midprice
        2. Synthetic from best bid/ask
        3. Last known midprice
        4. Static fallback
        """
        # 1. Live midprice
        mid = self.get_midprice()
        if mid > 0:
            return mid

        # 2. Synthetic from best bid/ask
        bid = self.get_best_price("bid")
        ask = self.get_best_price("ask")
        if bid > 0 and ask > 0:
            return (bid + ask) / 2

        # 3. Last known midprice
        if self.last_midprice and self.last_midprice > 0:
            return self.last_midprice

        # 4. Static fallback for test consistency
        fallback = 27000.0  # Example: BTCUSDT baseline
        logger.warning(f"[OrderBook] Midprice unavailable — using static fallback {fallback}")
        return fallback

    
    def get_level_size(self, price, side) -> float:
        """
        Returns the size available at a given price level and side.

        :param price: Price level to query
        :param side: 'bid' or 'ask'
        :return: Order size at that price
        """
        book = self.bids if side == 'bid' else self.asks
        return book.get(price, 0.0)
    
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
        

    # ------------------------- Liquidity Metrics --------------------------------
    def get_estimated_volume(self, side: str) -> float:
        """
        Estimate total volume on a given side of the book.

        :param side: 'bid' or 'ask'
        :return: sum of all sizes on that side
        """
        book = self.bids if side == 'bid' else self.asks
        return sum(book.values())

    def get_top_liquidity(self, side: str , depth_levels: int = 1) -> float:
        """
        Returns size available in the top N levels.
        """
        book = self.bids if side == "bid" else self.asks
        if not book:
            return 0.0
        levels = sorted(book.items(), key=lambda x: x[0], reverse=(side=="bid"))
        return sum(size for _, size in levels[:depth_levels])
    

    def get_liquidity_within_bps(self, side: str, bps: float) -> float:
        """
        Returns total liquidity within X basis points of midprice
        """
        mid = self.get_midprice()
        if mid <= 0:
            return 0.0
        threshold = mid * (bps / 1e4)

        if side == "bid":
            return sum(size for price, size in self.bids.items() if (mid - price) <= threshold)
        else:
            return sum(size for price, size in self.asks.items() if (price - mid) <= threshold)

    # -------------------- Microstructure metrics ---------------------------------
    def get_order_imbalance(self, side: str) -> float:
        """
        Order book imbalance = bid_vol / (bid_vol + ask_vol).
        Range [0, 1], > 0.5 means more bid-side liquidity.
        """
        bid_vol = self.get_estimated_volume("bid")
        ask_vol = self.get_estimated_volume("ask")
        denom = bid_vol + ask_vol
        if denom == 0:
            return 0.5 # Balanced fallback
        if side == "ask":
            return ask_vol /denom
        elif side == "bid":
            return bid_vol / denom

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
    

    def get_update_rate(self) -> float:
        """
        Rough update frequency (Hz). Useful to calibrate latency model
        """
        if not self.price_history or not self.last_update_ts:
            return 0.0
        return len(self.price_history) / max(1e-9, (time.time() -  self.last_update_ts))
        
    
    def get_tick_size(self) -> float:
        """
        Returns the tick size for the symbol.
        Tries Binance live fetch → cached value → default fallback.
        """
        if self._tick_size is not None:
            return self._tick_size

        tick_size = self._get_tick_size_from_binance(self.symbol)
        if tick_size:
            self._tick_size = tick_size
            return tick_size

        # If fetch failed and no cache, fallback
        print(Fore.RED + f"[WARNING] Using default tick size fallback for {self.symbol}")
        return 0.01


    def _get_tick_size_from_binance(self, symbol: str) -> float:
        """
        Attempts to fetch the tick size for a given symbol from Binance's exchangeInfo endpoint.
        If successful, returns the live tick size and caches it.
        If the request fails (due to network issues, DNS errors, or API downtime), returns None.
        This function is used as part of a layered fallback strategy: live fetch → cached value → default.
        """

        url = f"https://api.binance.com/api/v3/exchangeInfo?symbol={symbol}"
        try:
            response = requests.get(url, timeout=5)
            response.raise_for_status()
            data = response.json()
            filters = data["symbols"][0]["filters"]
            for f in filters:
                if f["filterType"] == "PRICE_FILTER":
                    tick_size = float(f["tickSize"])
                    print(Fore.GREEN + f"[INFO] Tick size for {symbol}: {tick_size}")
                    return tick_size
        except Exception as e:
            print(Fore.MAGENTA + f"[ERROR] Failed to fetch tick size for {symbol}: {e}")
        return None  # Signal failure
    

    def get_midpoint_staleness(self) -> float:
        """
        Measures how long the midpoint has remained unchanged.
        Returns a normalized staleness score [0.0–1.0].
        """
        if not self.price_history or not self.last_update_ts:
            return 0.0
        unchanged = sum(
            1 for i in range(1, len(self.price_history))
            if self.price_history[i] == self.price_history[i-1]
        )
        return unchanged / len(self.price_history)
    


    def get_quote_flicker_rate(self) -> float:
        """
        Estimates how frequently best bid/ask levels change.
        High flicker rate signals instability or algo churn.
        """
        flickers = 0
        prev_bid, prev_ask = None, None
        for i in range(1, len(self.price_history)):
            bid = max(self.bids.keys(), default=0.0)
            ask = min(self.asks.keys(), default=0.0)
            if bid != prev_bid or ask != prev_ask:
                flickers += 1
            prev_bid, prev_ask = bid, ask
        return flickers / max(1, len(self.price_history))
    


    def get_depth_retreat_score(self) -> float:
        """
        Measures how much liquidity retreats as price approaches.
        High score = passive defense or spoof unwind.
        """
        mid = self.get_midprice()
        if mid <= 0:
            return 0.0
        near_bid = sum(size for price, size in self.bids.items() if mid - price < 5)
        far_bid = sum(size for price, size in self.bids.items() if mid - price >= 5)
        near_ask = sum(size for price, size in self.asks.items() if price - mid < 5)
        far_ask = sum(size for price, size in self.asks.items() if price - mid >= 5)
        retreat_ratio = (far_bid + far_ask) / max(1e-6, near_bid + near_ask)
        return min(retreat_ratio, 1.0)
    

    def get_slip_response_score(self) -> float:
        """
        Measures how quickly orders retreat after fills.
        High score = fear, spoof unwind, or reactive defense.
        """
        # Placeholder: simulate slip detection using volatility spike
        vol = self.get_volatility_estimate()
        return min(1.0, vol * 20)

    def get_bid_aggression(self) -> float:
        """
        Measures how aggressively bids are placed near mid.
        High score = breakout pressure or spoof layering.
        """
        mid = self.get_midprice()
        if mid <= 0:
            return 0.0
        near_bids = sum(size for price, size in self.bids.items() if mid - price < 3)
        total_bids = sum(self.bids.values())
        return near_bids / max(1e-6, total_bids)
    
    def get_ask_defense(self) -> float:
        """
        Measures how defensively asks are layered near mid.
        High score = resistance or spoof layering.
        """
        mid = self.get_midprice()
        if mid <= 0:
            return 0.0
        near_asks = sum(size for price, size in self.asks.items() if price - mid < 3)
        total_asks = sum(self.asks.values())
        return near_asks / max(1e-6, total_asks)






