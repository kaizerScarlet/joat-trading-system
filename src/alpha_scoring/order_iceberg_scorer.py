import time
from typing import Dict
from cancel_window.order_iceberg_detection import OrderIcebergDetection

class IcebergScorer:
    def __init__(self, detector: OrderIcebergDetection, base_score: float = 1.0, decay_half_life: int = 10_000):
        self.detector = detector
        self.base_score = base_score
        self.decay_half_life = decay_half_life
        self.last_time = None
        self.last_score = {'ask': 0.0, 'bid': 0.0}

    def compute_score(self, current_time=None) -> Dict[str, float]:
        current_time = current_time or int(time.time() * 1000)
        icebergs = self.detector.detect_icebergs()
        score = {'ask': 0.0, 'bid': 0.0}
        for i in icebergs:
            side = i['side']
            aggression = i['total_size'] / max(1, i['duration'])
            score[side] += self.base_score * aggression
        for s in ['ask', 'bid']:
            decay = 1.0 if not self.last_time else 0.5 ** ((current_time - self.last_time) / self.decay_half_life)
            score[s] = min(1.0, score[s] * decay + self.last_score[s] * (1 - decay))
        self.last_time = current_time
        self.last_score = score
        return score
