import time
from typing import Dict
from cancel_window.synthetic_fill_detector import SyntheticFillDetection

class SyntheticFillScorer:
 
    def __init__(self, detector: SyntheticFillDetection, base_score = 1.0, decay_half_life = 5000):
        self.detector = detector
        self.base_score = base_score
        self.decay_half_life = decay_half_life
        self.last_time = None
        self.last_score = {'ask': 0.0, 'bid': 0.0}


    def compute_score(self, current_time = None) -> Dict[str, float]:
        current_time = current_time or int(time.time() * 1000)
        anomalies = self.detector.detect_anomalies()
        score = {'ask': 0.0, 'bid': 0.0}
        for a in anomalies:
            side = a['side']
            ratio = a['weak_fills'] / max(1, a['true'])
            score[side] += self.base_score * ratio

        for s in ['ask', 'bid']:
            decay = 1.0 if not self.last_time else 0.5 ** ((current_time - self.last_time) / self.decay_half_life)
            score[s] = min(1.0, score[s] * decay + self.last_score[s] * (1 -decay))

        self.last_time = current_time
        self.last_score = score
        return score