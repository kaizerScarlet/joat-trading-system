from cancel_window.order_laddering_detection_protocol import OrderLadderingDetectionProtocol
from typing import Dict
import time

class LadderingScorer:
    """
    Scores detected laddering sequences based on intensity, direction, and speed.
    """
    def __init__(self, detector: OrderLadderingDetectionProtocol, base_score: float = 1.0, decay_half_life: int = 8000):
        self.detector = detector
        self.base_score = base_score
        self.decay_half_life = decay_half_life
        self.last_time = None
        self.last_score = {'ask': 0.0, 'bid': 0.0}

    def compute_score(self, current_time: int = None) -> Dict[str, float]:
        current_time = current_time or int(time.time() * 1000)
        sequences = self.detector.detect_laddering_sequeces()
        score = {'ask': 0.0, 'bid': 0.0}

        for s in sequences:
            side = s['side']
            direction_bias = 1.2 if s['direction'] == "up" else 1.0
            aggression = 1.0 if 'LADDER_CANCEL_ONLY' in s['types'] else 0.7
            seq_score = self.base_score * direction_bias * aggression * (s['count'] / (s['duration_ms'] + 1))
            score[side] += seq_score

        
        for s in ['ask', 'bid']:
            decay = 1.0 if not self.last_time else 0.5 ** ((current_time - self.last_time) / self.decay_half_life)
            score[s] = min(1.0, score[s] * decay + self.last_score[s] * (1 - decay))

        self.last_time = current_time
        self.last_score = score
        return score