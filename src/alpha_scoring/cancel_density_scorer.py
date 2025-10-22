import time
from typing import Dict

class CancelDensityScorer:
    def __init__(self, detector, base_score=1.0, decay_half_life=5000):
        self.detector = detector
        self.base_score = base_score
        self.decay_half_life = decay_half_life
        self.last_time = None
        self.last_score = {'ask': 0.0, 'bid': 0.0}

    def compute_score(self, current_time=None) -> Dict[str, float]:
        current_time = current_time or int(time.time() * 1000)
        spikes = self.detector.detect_spikes(current_time=current_time)
        
        # If no spikes are detected, decay the last score and return it
        if not spikes:
            decay = 1.0 if not self.last_time else 0.5 ** ((current_time - self.last_time) / self.decay_half_life)
            score = {
                'ask': self.last_score['ask'] * decay,
                'bid': self.last_score['bid'] * decay
            }
            self.last_time = current_time
            self.last_score = score
            return score

        # Other wise compute fresh
        score = {'ask': 0.0, 'bid': 0.0}
        for s in spikes:
            side = s['side']
            intensity = s['count'] / max(1, s['unique_prices'])
            score[side] += self.base_score * intensity
        for s in ['ask', 'bid']:
            decay = 1.0 if not self.last_time else 0.5 ** ((current_time - self.last_time) / self.decay_half_life)
            score[s] = min(1.0, score[s] + self.last_score[s] * (1.0 - decay))

        self.last_time = current_time
        self.last_score = score
        return score
