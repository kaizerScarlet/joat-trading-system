from typing import Protocol, Dict, Any, runtime_checkable
from cancel_window.synthetic_fill_detector_protocol import SyntheticFillDetectorProtocol

@runtime_checkable
class SyntheticFillScorerProtocol(Protocol):
    detector: SyntheticFillDetectorProtocol
    base_score: float
    decay_half_life: int
    last_time: int
    last_score: Dict[str, Any]


    def compute_score(self, current_time = None) -> Dict[str, float]:
        """Compute Synthetic Fill Score"""
        ...
