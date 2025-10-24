from typing import Protocol, Optional, Dict, runtime_checkable
from cancel_window.order_age_distribution_protocol import OrderAgeDistributionProtocol

@runtime_checkable
class OrderAgeDistributionScorerProtocol(Protocol):
    tracker: OrderAgeDistributionProtocol
    distribution_tracker: Optional[OrderAgeDistributionProtocol]
    base_score: float
    short_lived_threshold_ms: int
    burst_ratio_threshold: float
    decay_half_life_ms: int
    enable_volume_weighting: bool
    enable_side_scoring: bool

    order_registration_time: dict
    min_score_by_side: Dict[str, float]
    max_score_by_side: Dict[str, float]

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
        ...

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
        ...

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
        ...

    def compute_score(
        self,
        side: str,
        current_time: Optional[int] = None
    ) -> Dict[str, float]:
        """Returns normalized age-based aggression scores per side (or combined)."""
        ...


    def reset(self) -> None:
        """Clears internal state for a fresh scoring cycle."""
        ...

    def get_debug_view(self) -> Dict[str, Dict]:
        """Returns internal state for debugging purposes."""
        ...