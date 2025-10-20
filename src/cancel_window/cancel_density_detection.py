from collections import defaultdict
from typing import List, Dict, Any
import time

class CancelDensityDetection:
    """Detects abnormal cancel concentration (CANCEL_DENSITY_SPIKE, LAYER_WIPE)."""
    def __init__(self, window_ms: int = 1000, threshold: int = 5):
        self.window_ms = window_ms
        self.threshold = threshold
        self.events: List[Dict[str, Any]] = []

    def register_cancel(self, timestamp: int, price: float, side: str):
        self.events.append({'timestamp': timestamp, 'price': price, 'side': side})
        self._prune()

    def _prune(self):
        cutoff = int(time.time() * 1000) - self.window_ms
        self.events = [e for e in self.events if e['timestamp'] >= cutoff]

    def detect_spikes(self) -> List[Dict[str, Any]]:
        by_side = defaultdict(list)
        for e in self.events: by_side[e['side']].append(e)
        spikes = []
        for side, evs in by_side.items():
            prices = [e['price'] for e in evs]
            if len(prices) >= self.threshold:
                spikes.append({'side': side, 'count': len(prices), 'unique_prices': len(set(prices))})
        return spikes

    def get_density_score(self):
        spikes = self.detect_spikes()
        if not spikes: return 0.0
        score = sum(s['count'] for s in spikes) / 50.0
        return min(1.0, score)
