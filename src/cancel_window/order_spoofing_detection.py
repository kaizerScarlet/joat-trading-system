from collections import defaultdict
from typing import List, Dict, Any
import time

class OrderSpoofingDetection:
    """
    Detects spoofing behaviors based on short-lived orders and cancel bursts.
    Inputs: events like CANCEL_SPOOF, PING_CANCEL, REPOSTING_BEHAVIOUR, BURST_CANCEL.
    Output: clusters summarizing spoof-like bursts per side.
    """
    def __init__(self, retention_ms: int = 300_000, burst_window_ms: int = 250):
        self.retention_ms = retention_ms
        self.burst_window_ms = burst_window_ms
        self.events: List[Dict[str, Any]] = []

    def register_event(self, orderid: str, timestamp: int, event_type: str, price: float, size: float, side: str):
        self.events.append({
            'orderid': orderid, 'timestamp': timestamp, 'event_type': event_type,
            'price': price, 'size': size, 'side': side
        })
        self._prune()

    def _prune(self):
        cutoff = int(time.time() * 1000) - self.retention_ms
        self.events = [e for e in self.events if e['timestamp'] >= cutoff]

    def detect_spoofing_clusters(self) -> List[Dict[str, Any]]:
        clusters, by_side = [], defaultdict(list)
        for e in self.events: by_side[e['side']].append(e)
        for side, events in by_side.items():
            events.sort(key=lambda x: x['timestamp'])
            burst = [events[0]]
            for e in events[1:]:
                if e['timestamp'] - burst[-1]['timestamp'] <= self.burst_window_ms:
                    burst.append(e)
                else:
                    if len(burst) >= 3: clusters.append(self._summarize_cluster(side, burst))
                    burst = [e]
            if len(burst) >= 3: clusters.append(self._summarize_cluster(side, burst))
        return clusters

    def _summarize_cluster(self, side, cluster):
        avg_price = sum(e['price'] for e in cluster) / len(cluster)
        return {
            'side': side,
            'count': len(cluster),
            'avg_price': avg_price,
            'duration_ms': cluster[-1]['timestamp'] - cluster[0]['timestamp'],
            'types': list({e['event_type'] for e in cluster})
        }

    def get_spoofing_score(self) -> float:
        clusters = self.detect_spoofing_clusters()
        if not clusters: return 0.0
        score = sum(c['count'] / (c['duration_ms'] + 1) for c in clusters)
        return min(1.0, score / 50.0)
