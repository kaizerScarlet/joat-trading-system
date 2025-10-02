from typing import Protocol, Optional, List, Dict
from market_data.orderbook import OrderBook

class StealthRouterProtocol(Protocol):
    async def execute_parent_order(
        self,
        side: str,
        total_qty: float,
        order_type: str,
        limit_price: Optional[float] = None,
        fee_schedule = None,
        slippage_model = None,
        orderbook: OrderBook = None,
        mode: str = "normal",
        hybrid_threshold: float = 0.3,
        hybrid_horizon: int = 5,
        fill_prob_threshold: float = 0.25
    ) -> List[Dict]:
        """Executes a parent order in stealthy slices with optional hybrid upgrades."""

    def record_fill(
        self,
        order_id: str,
        fill_price: float,
        fill_ts: float,
        fill_qty: Optional[float] = None
    ) -> None:
        """Records fill metrics including latency, slippage, and velocity."""

    def get_recent_fill_velocity(self, lookback: int = 5) -> float:
        """Returns average fill velocity (qty/sec) over recent slices."""
