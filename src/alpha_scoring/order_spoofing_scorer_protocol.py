from typing import Protocol, Dict, Any, runtime_checkable
from cancel_window.order_spoofing_detection_protocol import OrderSpoofingDetectionProtocol

@runtime_checkable
class OrderSpoofingScorerProtocol(Protocol):
    detector: OrderSpoofingDetectionProtocol
    base_score: float
    decay_half_life: int
    last_time: int
    last_score_by_side: Dict[str, float]

    def compute_score(self, current_time: int = None) -> Dict[str, float]:
        """Computes the order spoofing score for both ask and bid sides."""
        ...
