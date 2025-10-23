from typing import Protocol, Dict, runtime_checkable
from cancel_window.cancel_denisty_detection_protocol import CancelDensityDetectionProtocol

@runtime_checkable
class CancelDensityScorerProtocol(Protocol):
    detector: CancelDensityDetectionProtocol
    base_score: float
    decay_half_life: int
    last_time: int
    last_score: Dict[str, float]

    def compute_score(self, current_time=None) -> Dict[str, float]:
        """Computes the cancel density score for both ask and bid sides."""
        ...