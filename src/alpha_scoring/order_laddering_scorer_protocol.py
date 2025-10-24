from typing import Protocol, Dict, runtime_checkable, Any
from cancel_window.order_laddering_detection_protocol import OrderLadderingDetectionProtocol

@runtime_checkable
class OrderLadderingScoringProtocol(Protocol):
     detector: OrderLadderingDetectionProtocol
     base_score: float
     decay_half_life: int
     last_time: int
     last_score: Dict[str, float]

     def compute_score(self, current_time: int = None) -> Dict[str, float]:
          """Compute Ladder Score"""
          ...