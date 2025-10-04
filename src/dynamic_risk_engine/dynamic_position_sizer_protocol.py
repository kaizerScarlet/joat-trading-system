from typing import Protocol, Dict
from datetime import datetime

class DynamicPositionSizerProtocol(Protocol):
    async def initialize(self) -> None:
        """Initializes the position sizer by computing max risk per trade."""

    async def calculate_position_size(self, stop_loss_distance: float) -> float:
        """Calculates position size based on volatility, confidence, win rate, and drawdown throttle."""

    async def get_sizing_diagnostics(self, stop_loss_distance: float) -> Dict[str, float]:
        """Returns detailed diagnostics used in position sizing logic."""

    async def reset(self) -> None:
        """Resets the position sizer to initial state."""

    def _compute_max_risk_per_trade(self) -> float:
        """return max risk per trade"""

    def get_drawdown_throttle(self) -> float:
        """Returns throttle factor based on current drawdown severity."""
