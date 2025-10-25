from typing import Protocol
from market_data.orderbook_protocol import OrderBookProtocol

class SmartRepricingModelProtocol(Protocol):
    tick_size: float
    max_jitter_ticks: int
    slippage_bps: float

    def optimize_price(
        self,
        side: str,
        orderbook: OrderBookProtocol,
        fill_prob_target: float
    ) -> float:
        """
        Computes an optimized limit price based on spread, fill probability, jitter, and slippage cap.
        Returns a tick-aligned price.
        """
        ...
