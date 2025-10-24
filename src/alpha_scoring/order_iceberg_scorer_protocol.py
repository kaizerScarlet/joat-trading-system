from typing import Protocol, Dict, runtime_checkable
from cancel_window.order_iceberg_detection_protocol import OrderIcebergDetectionProtocol

@runtime_checkable
class IcebergScorerProtocol(Protocol):
     detector: OrderIcebergDetectionProtocol
     base_score: float
     decay_half_life: int
     last_time: int
     last_score: Dict[str, float]

     def compute_score(self, current_time=None) -> Dict[str, float]:
          """Computes and returns the iceberg order score per side."""
          ...