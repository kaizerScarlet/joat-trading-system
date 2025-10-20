from typing import List, Dict, Any
import time

class OrderIcebergDetection:
    """Detects iceberg cancels: multiple partial reductions before full cancel."""
    def __init__(self, retention_ms: int = 300_000):
        self.retention_ms = retention_ms
        self.events: List[Dict[str, Any]] = []

    def register_event(self, orderid: str, timestamp: int, event_type: str, price: float, size: float, side: str):
        self.events.append({'orderid': orderid, 'timestamp': timestamp, 'event_type': event_type,
                            'price': price, 'size': size, 'side': side})
        self._prune()

    def _prune(self):
        cutoff = int(time.time() * 1000) - self.retention_ms
        self.events = [e for e in self.events if e['timestamp'] >= cutoff]

    def detect_icebergs(self) -> List[Dict[str, Any]]:
        icebergs = []
        by_order = {}
        for e in self.events:
            by_order.setdefault(e['orderid'], []).append(e)
        for oid, evts in by_order.items():
            evts.sort(key=lambda x: x['timestamp'])
            reductions = [e for e in evts if e['event_type'] == 'REDUCTION']
            if len(reductions) >= 2 and evts[-1]['event_type'] == 'CANCEL_SPOOF':
                icebergs.append({
                    'orderid': oid,
                    'side': evts[-1]['side'],
                    'reductions': len(reductions),
                    'total_size': sum(e['size'] for e in reductions),
                    'duration': evts[-1]['timestamp'] - evts[0]['timestamp']
                })
        return icebergs

    def get_iceberg_score(self) -> float:
        icebergs = self.detect_icebergs()
        if not icebergs: return 0.0
        score = sum(i['reductions'] for i in icebergs) / 10.0
        return min(1.0, score)
