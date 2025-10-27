from typing import Protocol, Dict, Any
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

    def get_debug_view(self, side: str, orderbook: OrderBookProtocol, fill_prob_target: float) -> Dict[str, Any]:
        """Get debug view for introspection"""
        ...
