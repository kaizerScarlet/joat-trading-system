from typing import Protocol, Optional, Dict

class OrderAgeDistributionScorerProtocol(Protocol):
    def register_events(
        self,
        orderid: str,
        timestamp: int,
        event_type: str,
        price: float,
        size: float,
        distance_from_best: float,
        side: str = 'ask'
    ) -> None:
        """Unified ingestion of age-related events (fills, cancels, spoof flags)."""

    def cancel_order(
        self,
        orderid: str,
        timestamp: int,
        event_type: str,
        price: float,
        size: float,
        distance_from_best: float,
        side: str
    ) -> None:
        """Registers a cancel event for age scoring."""

    def fill_order(
        self,
        orderid: str,
        timestamp: int,
        event_type: str,
        price: float,
        size: float,
        distance_from_best: float,
        side: str
    ) -> None:
        """Registers a fill event for age scoring."""

    def compute_score(
        self,
        side: str,
        current_time: Optional[int] = None
    ) -> Dict[str, float]:
        """Returns normalized age-based aggression scores per side (or combined)."""

    def reset(self) -> None:
        """Clears internal state for a fresh scoring cycle."""
