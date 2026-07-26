from typing import Protocol, Dict, runtime_checkable, Optional
from collections import deque


@runtime_checkable
class OrderBookProtocol(Protocol):
    history_len: int
    symbol: str
    bids: Dict[float, float]
    asks: Dict[float, float]
    last_midprice: None
    price_history: deque
    last_update_ts: None
    _tick_size: None

    def update(self, msg):
        """Process Binance depth@1000ms L2 Update
        Updates bid and ask level accordingly.
        :param msg: L2 depth update from Binance WebSocket stream
        """
        ...
    def get_midprice(self) -> float:
        """Returns the last computed midprice or 0.0 if unavailable."""
        ...

    def get_level_size(self, price: float, side: str) -> float:
        """Returns the size available at a given price level and side."""
        ...

    def get_best_price(self, side: str) -> float:
        """Returns the best bid or ask price."""
        ...

    def get_estimated_volume(self, side: str) -> float:
        """Returns total volume on a given side of the book."""
        ...

    def get_top_liquidity(self, side: str, depth_levels: int = 1) -> float:
        """Returns size available in the top N levels."""
        ...

    def get_mark_price(self) -> float:
        """
        Returns the latest mark price.
        Priority: WS mark price stream → live L2 mid → REST fallback.
        """
        ...

    def get_liquidity_within_bps(self, side: str, depth_bps: float) -> float:
        """Returns total liquidity within X basis points of midprice."""
        ...

    def get_order_imbalance(self, side: str, depth_levels: int = 5) -> float:
        """Returns order book imbalance score (0.0 to 1.0)."""
        ...

    def get_volatility_estimate(self) -> float:
        """Returns short-term volatility estimate based on midprice history."""
        ...

    def get_update_rate(self) -> float:
        """Returns update frequency (ticks/sec)."""
        ...

    def get_tick_size(self) -> float:
        """Returns the smallest tick size used for the symbol."""
        ...

    def get_resilient_midprice(self) -> float:
        """
        Returns a safe midprice using fallback hierarchy:
        1. Live midprice
        2. Synthetic from best bid/ask
        3. Last known midprice
        4. Static fallback
        """
        ...

    def get_midpoint_staleness(self) -> float:
        """
        Measures how long the midpoint has remained unchanged.
        Returns a normalized staleness score [0.0–1.0].
        """
        ...

    def get_quote_flicker_rate(self) -> float:
        """
        Estimates how frequently best bid/ask levels change.
        High flicker rate signals instability or algo churn.
        """
        ...
    def get_depth_retreat_score(self) -> float:
        """
        Measures how much liquidity retreats as price approaches.
        High score = passive defense or spoof unwind.
        """
        ...

    def get_slip_response_score(self) -> float:
        """
        Measures how quickly orders retreat after fills.
        High score = fear, spoof unwind, or reactive defense.
        """
        ...

    def get_bid_aggression(self) -> float:
        """
        Measures how aggressively bids are placed near mid.
        High score = breakout pressure or spoof layering.
        """
        ...

    def get_ask_defense(self, depth_bps: float = 5.0) -> float:
        """
        Measures how defensively asks are layered near mid.
        High score = resistance or spoof layering.
        """
        ...

    def get_bid_defense(self, depth_bps: float = 5.0) -> float:
        """
        Measures how defensively bids are layered near mid.
        High score = resistance or spoof layering.
        """
        ...


    def get_nearest_support_resistance(self, side: str) -> Optional[float]:
        """
        Returns nearest support (for 'bid') or resistance (for 'ask') level based on top liquidity.
        """
        ...

    def get_vamp(self, depth_bps: float = 5.0) -> float:
        """
        Calculates Volume-Weighted Average Mid-Price (VAMP).
        Protects against 'shallow' book noise by weighting the price 
        based on volume within a specific % distance from mid.
        """
        
        ...
    
    def get_bps_imbalance(self, depth_bps: float = 10.0) -> float:
        """
        A more realistic version of level-based imbalance.
        Uses a percentage of price to capture actual 'walls'.
        """
        ...

    def get_layered_imbalance(self, base_layers: list = [5.0, 15.0, 40.0]) -> float:
        """
        Calculates a weighted imbalance across multiple depth layers.
        Protects against top-of-book spoofing by looking at deeper 'walls'.
        Returns a score from 0 (heavy ask pressure) to 1 (heavy bid pressure).
        """
        ...

    def get_imbalance_momentum(self, lookback_periods: int = 10) -> float:
        """
        Robust Imbalance Momentum:
        Measures the velocity and acceleration of book pressure changes.
        
        Returns:
            float: Range [-1.0, 1.0]. 
                Positive (>0.05): Bid pressure is accelerating (Bullish/Spoofing Bid).
                Negative (<-0.05): Ask pressure is accelerating (Bearish/Spoofing Ask).
        """
        ...