from typing import Protocol, Optional, Dict, Tuple, Any, runtime_checkable

@runtime_checkable
class ExecutionCoordinatorProtocol(Protocol):
    async def reconcile_open_orders(self) -> None:
        """Fetches open orders from exchange and reconciles with local state."""

    def now_ms(self) -> int:
        """Returns current time in milliseconds adjusted by server offset."""

    def on_new_alpha(self, alpha: Dict[str, float], market_snapshot: Dict) -> None:
        """Handles new alpha signal and decides whether to trade."""

    def on_market_tick(self, high: Optional[float] = None, low: Optional[float] = None, close: Optional[float] = None) -> None:
        """Handles market tick updates, adjusts SL/TP, and syncs with exchange."""

    def monitor_open_positions(self) -> None:
        """Syncs open positions with exchange and updates SL/TP if needed."""

    def _reset_position_state(self) -> None:
        """Resets internal position tracking state."""

    def _check_pre_trade_conditions(self) -> bool:
        """Runs confidence, throttle, and risk checks before trade execution."""

    def _compute_order_size(self, stop_loss_distance: float) -> float:
        """Computes order size based on stop loss distance and dynamic sizing logic."""

    def _choose_order_type_and_price(self, side: str, order_size: float) -> Tuple[str, Optional[float]]:
        """Selects order type and price based on spread, slippage, fees, and queue dynamics."""

    def _execute_order(
        self,
        side: str,
        size: float,
        order_type: str,
        price: Optional[float],
        ts: float,
        base_sl: float,
        base_tp: float,
        side_for_sl: str
    ) -> None:
        """Executes order via StealthRouter with latency, slippage, and behavioral metadata."""

    async def _on_fill(self, fill: Dict[str, Any]) -> None:
        """Handles fill events, updates SL/TP, and reconciles position state."""

    def _update_sl_tp_after_slice(self, qty: float, side: str) -> None:
        """Adjusts SL/TP dynamically after stealth slice fills."""

    def _decide_trade_side(self) -> Optional[str]:
        """Decides trade direction based on alpha, regime, spoofing, and layering scores."""
