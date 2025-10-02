from typing import Protocol, Dict, runtime_checkable

@runtime_checkable
class LayeringScoringProtocol(Protocol):
    def register_events(self, timestamp: int, event_type: str, price: float, size: float, side: str) -> None:
        """Unified ingestion of layering-related events (cancels, fills, wipes, laddering)."""

    def register_cancel(self, timestamp: int, event_type: str, price: float, size: float, side: str) -> None:
        """Tracks cancel events for layering and laddering detection."""

    def register_fill(self, timestamp: int, event_type: str, price: float, size: float, side: str) -> None:
        """Tracks fill events for layering and laddering scoring."""

    def compute_score(self, current_time: int) -> Dict[str, float]:
        """Returns normalized behavioral scores per side based on clustering, fill behavior, skew, and decay."""

    def reset(self) -> None:
        """Clears internal state for a fresh scoring cycle."""
