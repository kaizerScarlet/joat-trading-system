from typing import Protocol, Tuple
from market_data.orderbook_protocol import OrderBookProtocol

class QueuePositionModelProtocol(Protocol):
    base_trade_rate: float
    def estimate(
        self,
        side: str,
        our_qty: float,
        tob_qty: float,
        orderbook: OrderBookProtocol
    ) -> Tuple[float, float]:
        """
        Estimates our queue position and fill probability.
        Returns:
            - queue_fraction: our_qty / tob_qty
            - approx_fill_prob_per_second: activity-adjusted fill likelihood
        """
