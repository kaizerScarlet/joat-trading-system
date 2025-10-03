from typing import Protocol, Dict, runtime_checkable

@runtime_checkable
class ThrottleCooldownManagerProtocol(Protocol):
    def register_trade_result(self, pnl: float) -> None:
        """Registers a trade result and applies cooldown logic if loss streak exceeds threshold."""

    def is_in_cooldown(self) -> bool:
        """Returns True if currently in cooldown period due to loss streak."""

    def can_trade(self) -> bool:
        """Returns True if trading is allowed based on cooldown and trade rate limits."""

    def reset(self) -> None:
        """Resets internal state including cooldown, loss streak, and trade timestamps."""

    def record_order(self, volume: float = 1.0, weight: int = 1) -> None:
        """Logs an order submission and updates volume, weight, and counters."""

    def record_cancel(self) -> None:
        """Logs an order cancel event."""

    def record_fill(self, volume: float) -> None:
        """Logs a trade fill and updates filled volume."""

    def get_conversion_rate(self) -> float:
        """Returns the conversion rate: trades / (orders + cancels)."""

    def get_fill_weight(self) -> float:
        """Returns the fill weight: filled volume / ordered volume."""

    def get_weight_per_minute(self) -> float:
        """Returns the total API request weight over the past 60 seconds."""

    def is_throttled(self) -> bool:
        """Returns True if any throttle condition is violated (behavioral, rate, volume, or weight)."""

    def get_diagnostic(self) -> Dict[str, any]:
        """Returns a snapshot of current system state including limits, overlays, and regime context."""
