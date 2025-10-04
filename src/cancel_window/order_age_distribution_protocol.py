from typing import Protocol, Dict, runtime_checkable

@runtime_checkable
class OrderAgeDistributionProtocol(Protocol):
    def _prune(self, current_time: int):
        """Hybrid pruning: keep only events within retention window + cap max size"""
        
    def register_event(self, orderid: str, timestamp: int, price: float, size: float, side: str) -> None:
        """Registers a new order with its creation timestamp."""

    def cancel_order(self, orderid: str, timestamp: int, event_type: str, price: float, size: float, distance_from_best: float, side: str) -> None:
        """Marks an order as cancelled and records its age and context."""

    def fill_order(self, orderid: str, timestamp: int, event_type: str, price: float, size: float, distance_from_best: float, side: str) -> None:
        """Marks an order as filled and records its age and context."""

    def detect_bursts(self, age_threshold_ms: int, burst_window_ms: int) -> Dict[str, bool]:
        """Detects binary burst flags for short-lived orders per side."""

    def detect_short_lived_bursts(self, age_threshold_ms: int, cluster_window_ms: int) -> Dict[str, int]:
        """Detects number of short-lived bursts per side using sliding window clustering."""

    def get_statistics(self) -> Dict[str, float]:
        """Returns statistical summary of order ages (mean, std, quantiles)."""

    def get_order_age_bias(self) -> float:
        """Returns normalized bias score: <0 = aggressive, >0 = passive, ~0 = neutral."""

    def get_age_distribution(self, bucket_ms: int) -> Dict[int, int]:
        """Returns histogram of order ages in specified millisecond buckets."""

    def get_recent_short_lived_ratio(self, threshold_ms: int, window_ms: int) -> float:
        """Returns ratio of short-lived orders in recent time window."""

    def reset(self) -> None:
        """Resets the order age tracker."""
