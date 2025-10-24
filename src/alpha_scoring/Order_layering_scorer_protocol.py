from typing import Protocol, Dict, runtime_checkable
from cancel_window.order_layering_detection_protocol import OrderLayeringDetectionProtocol

@runtime_checkable
class LayeringScoringProtocol(Protocol):
    layering_detector: OrderLayeringDetectionProtocol
    reference_size: float
    base_score: float
    decay_half_life: int
    cluster_window_ms: int
    min_orders_in_cluster: int
    min_order_density: float
    max_price_range_bps: float
    skew_threshold: float
    repost_window_ms: int
    repost_price_tolerance: float

    recent_orders: list
    recent_cancels: list

    last_score_by_side: Dict[str, float]
    last_time: int
    min_score_by_side: Dict[str, float]
    max_score_by_side: Dict[str, float]
    score_volatility_by_side: Dict[str, float]
    cluster_density_by_side: Dict[str, float]

    debug: bool

    def register_events(self,orderid: str, timestamp: int, event_type: str, price: float, size: float, side: str) -> None:
        """Unified ingestion of layering-related events (cancels, fills, wipes, laddering)."""
        ...

    def register_cancel(self,orderid: str, timestamp: int, event_type: str, price: float, size: float, side: str) -> None:
        """Tracks cancel events for layering and laddering detection."""
        ...

    def register_fill(self,orderid: str, timestamp: int, event_type: str, price: float, size: float, side: str) -> None:
        """Tracks fill events for layering and laddering scoring."""
        ...

    def compute_score(self, current_time: int) -> Dict[str, float]:
        """Returns normalized behavioral scores per side based on clustering, fill behavior, skew, and decay."""
        ...

    def reset(self) -> None:
        """Clears internal state for a fresh scoring cycle."""
        ...


    def get_debug_view(self) -> Dict[str, Dict]:
        """Returns a debug view of internal state for inspection and troubleshooting."""
        ...
        