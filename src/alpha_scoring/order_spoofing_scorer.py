from typing import Dict
import time
from cancel_window.order_spoofing_detection_protocol import OrderSpoofingDetectionProtocol



class SpoofingScorer:
    def __init__(self, spoof_detector: OrderSpoofingDetectionProtocol, base_score: float = 1.0, decay_half_life: int = 5000):
        self.detector = spoof_detector
        self.base_score = base_score
        self.decay_half_life = decay_half_life
        self.last_time = None
        self.last_score_by_side = {'ask': 0.0, 'bid': 0.0}

    def compute_score(self, current_time: int = None) -> Dict[str, float]:
        current_time = current_time or int(time.time() * 1000)
        clusters = self.detector.detect_spoofing_clusters()
        score_by_side = {'ask': 0.0, 'bid': 0.0}

        for c in clusters:
            side = c['side']
            burst_intensity = c['count'] / max(1, c['duration_ms'])
            aggression = 1.0 if 'CANCEL_SPOOF' in c['types'] else 0.6
            score_by_side[side] += self.base_score * burst_intensity * aggression

        for s in ['ask', 'bid']:
            decay = 1.0 if self.last_time is None else 0.5 ** ((current_time - self.last_time) / self.decay_half_life)
            score_by_side[s] = min(1.0, score_by_side[s] * decay + self.last_score_by_side[s] * (1 - decay))

        self.last_time = current_time
        self.last_score_by_side = score_by_side
        return score_by_side
