from typing import TYPE_CHECKING, Protocol, Dict, List, Any, runtime_checkable

if TYPE_CHECKING:
    from cancel_window.simple_cancel_window import CancelWindowTunerForLayering

@runtime_checkable
class OrderLayeringDetectionProtocol(Protocol):
    tuner: "CancelWindowTunerForLayering"  #<- qouted as forward reference
    price_tick: float
    cluster_depth: int
    min_orders: int
    retention_ms: int
    min_size_per_order: float

    _layering_cache: List[Dict[str, Any]]
    _last_cache_time: int
    _cache_interval_ms: int

    orders_log: List[Dict[str, Any]]
    cancel_log: List[Dict[str, Any]]
    fills_log: List[Dict[str, Any]]

    def register_order(self, orderid: str, timestamp: int, price: float, size: float, side: str) -> None:
        """Registers a new limit order with timestamp and side context."""
        ...

    def register_cancel(self, orderid: str, timestamp: int, event_type: str, price: float, size: float, side: str) -> None:
        """Registers a cancellation event and updates latency tuner."""
        ...

    def register_fill(self, orderid: str, timestamp: int, event_type: str, price: float, size: float, side: str) -> None:
        """Registers a fill event and updates order status."""
        ...

    def detect_layering(self) -> List[Dict[str, Any]]:
        """Detects suspicious layering clusters based on price adjacency, timing, and cancel behavior."""
        ...

    def _prune(self):
        """Hybrid pruning: keep only events within retention window """
        ...

    def _normalize_side(self, side: str) -> str:
        """Return normalized side (input: a -> output: ask) or (input: b -> output: bid)"""
        ...
    
    def get_layering_score(self) -> float:
        """Returns a normalized layering score (0.0 to 1.0) based on aggression and recency."""
        ...

    def reset(self) -> None:
        """Resets the detection logs for a new cycle."""
        ...

    def get_debug_view(self) -> Dict[str, Any]:
        """Returns a snapshot of internal state for debugging and inspection."""
        ...

    def refresh_layering_cache(self):
        """
        Refresh the layering cache if enough time has passed since the last update.
        This avoids recomputing layering clusters on every fill.
        """
        ...

    def force_refresh_layering_cache(self):
        """
        Manually refresh layering cache regardless of interval.
        Useful for batch updates or diagnostic snapshots.
        """
        ...

    def get_layering_clusters(self) -> List[Dict[str, Any]]:
        """
        Returns the current cached layering clusters.
        Useful for overlays, dashboards, or symbolic narration.
        """
        ...

    def is_layered_order(self, orderid: str) -> bool:
        """
        Returns True if the given orderid was part of a detected layering cluster.
        Uses cached clusters for performance.
        """
        ...