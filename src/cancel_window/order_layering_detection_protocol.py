from typing import Protocol, Dict, List, Any, runtime_checkable

@runtime_checkable
class OrderLayeringDetectionProtocol(Protocol):
    def register_order(self, orderid: str, timestamp: int, price: float, size: float, side: str) -> None:
        """Registers a new limit order with timestamp and side context."""

    def register_cancel(self, orderid: str, timestamp: int, event_type: str, price: float, size: float, side: str) -> None:
        """Registers a cancellation event and updates latency tuner."""

    def register_fill(self, orderid: str, timestamp: int, event_type: str, price: float, size: float, side: str) -> None:
        """Registers a fill event and updates order status."""

    def detect_layering(self) -> List[Dict[str, Any]]:
        """Detects suspicious layering clusters based on price adjacency, timing, and cancel behavior."""

    def _prune(self):
        """Hybrid pruning: keep only events within retention window """

    def _normalize_side(self, side: str) -> str:
        """Return normalized side (input: a -> output: ask) or (input: b -> output: bid)"""
    
    def get_layering_score(self) -> float:
        """Returns a normalized layering score (0.0 to 1.0) based on aggression and recency."""

    def reset(self) -> None:
        """Resets the detection logs for a new cycle."""
