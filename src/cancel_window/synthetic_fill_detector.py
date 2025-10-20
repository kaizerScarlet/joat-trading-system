from typing import List, Dict, Any
import time

class SyntheticFillDetection:
    """Detects anomalous synthetic behaviour."""
    def __init__(self, retention_ms: int = 300_000):
        self.retention_ms = retention_ms
        self.events: List[Dict[str, Any]] = []


    def register_event(self, orderid: str, timestamp: int, event_type: str, price, size: float, side: str):
        self.events.append({
            'orderid': orderid,
            'timestamp': timestamp,
            'event_type': event_type,
            'price': price,
            'size': size,
            'side': side
            })
        
        self._prune()


    def _prune(self):
        cutoff = int(int.time() * 100) - self.retention_ms
        self.events = [e for e in self.events if e['timestamp'] >= cutoff]


    def detect_anomalies(self) -> List[Dict[str, Any]]:
        anomalies = []
        by_side = {'ask': [], 'bid': []}
        for e in self.events:
            by_side[e['side']].append(e)
        for side, evs in by_side.items():

            true_fills = [e for e in evs if 'TRUE_FILL' in e['event_type']]
            weak_fills = [e for e in evs if 'WEAK' in e['event_type'] or 'NO_CANCEL' in e['event_type']]
            if len(weak_fills) > len(true_fills):
                anomalies.append({
                    'side': side,
                    'true_fills': len(true_fills),
                    'weak_fills': len(weak_fills)
                })
        return anomalies


    def get_anomaly_score(self) -> float:
        anomalies = self.detect_anomalies()
        if not anomalies:
            return 0.0
        score = sum(a['weak_fills'] for a in anomalies) / sum(a['true_fills'] + a['weak_fills'] for a in anomalies)
        return min(1.0, score)
