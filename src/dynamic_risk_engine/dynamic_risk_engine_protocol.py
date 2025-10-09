from typing import Protocol, Dict, runtime_checkable
from datetime import datetime

@runtime_checkable
class DynamicRiskEngineProtocol(Protocol):
    async def initialize(self) -> None:
        """Initializes all internal modules and sets account balance and risk parameters."""

    def update_market_regime(self) -> None:
        """Updates the current market regime using the classifier."""

    def can_trade(self) -> bool:
        """Returns True if trading is allowed based on drawdown and cooldown state."""

    def get_risk_for_trade(self) -> float:
        """Returns the current max risk per trade."""

    async def get_position_size(self, stop_loss_distance: float) -> float:
        """Returns the optimal position size based on current risk and regime context."""

    def register_trade(self, pnl: float, risk: float, reward: float, signal_id: str, was_correct: bool, metadata: Dict = None) -> None:
        """Registers a trade and updates all internal trackers and calibrators."""

    def get_risk_curve_value(self) -> float:
        """Returns the current risk curve value based on signal confidence."""

    async def reset(self) -> None:
        """Resets all internal state (e.g., start of day)."""

    async def get_diagnostic(self) -> Dict[str, any]:
        """Returns full diagnostic snapshot of the risk engine state."""

    async def get_debug_view(self) -> dict:
        """Debug view for introspection and debugging"""

    async def get_trade_rationale(self, stop_loss_distance: float) -> dict:
        """This lets you explain every trade with behavioral clarity."""
