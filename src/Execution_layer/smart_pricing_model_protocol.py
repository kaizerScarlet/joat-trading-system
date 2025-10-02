from typing import Protocol
from market_data.orderbook import OrderBook

class SmartRepricingModelProtocol(Protocol):
    def optimize_price(
        self,
        side: str,
        orderbook: OrderBook,
        fill_prob_target: float
    ) -> float:
        """
        Computes an optimized limit price based on spread, fill probability, jitter, and slippage cap.
        Returns a tick-aligned price.
        """
