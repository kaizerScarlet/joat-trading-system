from collections  import defaultdict
from typing import List, Dict, Any
import time

class OrderLadderingDetection:
    """
    Detects laddering behaviour:
        - Sequential order placements and cancels up or down the book
        - Distinct from layering (simultaneous multi-level placements)
        - Common indicators: MULTILEVEL_LADDERING, LADDER_CANCEL, LADDER_CANCEL_ONLY, LADDER_TRUE_FILL

    """

    def __init__(self, retention_ms: int = 300_000, step_window_ms: int = 500):
        self.retention_ms = retention_ms
        self.step_window_ms = step_window_ms
        self.events: List[Dict[str, Any]] = []

    def register_event(self, orderid: str, timestamp: int, event_type: str, price: float, size: float, side: str):
        self.events.append({
            "orderid": orderid,
            "timestamp": timestamp,
            "price": price,
            "size": size,
            "side": side
        })
        self._prune()

    
    def _prune(self):
        cutoff = int(time.time() * 1000) - self.retention_ms
        self.events = [e for e in self.events if e["timestamp"] >= cutoff]

    
    def detect_laddering_sequeces(self) -> List[Dict[str, Any]]:
        """
        Detects sequential price-stepping patterns:
        orders placed/canceled in progressive price directions (ladder-like).
        """

        sequences = []
        by_side = defaultdict(list)
        for e in self.events:
            if "LADDER" in e["event_type"]:
                by_side[e["side"]].append(e)

        for side, events in by_side.items():
            events.sort(key=lambda x: x['timestamp'])
            seq = [events[0]]
            for e in events[1:]:
                prev = seq[-1]
                time_diff = e['timestamp'] - prev['timestamp']
                price_diff = abs(e['price'] - prev['price'])


                #Price step movement in one direction, within short time window
                same_direction = (e['price'] > prev['price'] == (side == "bid"))
                if time_diff <= self.step_window_ms and price_diff > 0 and same_direction:
                    seq.append(e)
                else:
                    if len(seq) >= 3:
                        sequences.append(self._summarize_sequence(side, seq))
        return sequences
    

    def _summarize_sequence(self, side, seq):
        direction = "up" if seq[-1]['price'] > seq[0]['price'] else "down"
        avg_size = sum(e['size'] for e in seq) / len(seq)
        return {
            "side": side,
            "count": len(seq),
            "duration_ms": seq[-1]['timestamp'] - seq[0]['timestamp'],
            "direction": direction,
            "avg_size": avg_size,
            "types": list({e['event_type'] for e in seq})
        }
    
    def get_laddering_score(self) -> float:
        sequences = self.detect_laddering_sequeces()
        if not sequences:
            return 0.0
        score = sum(s['count'] * s['avg_size'] / (s['duration_ms'] + 1) for s in sequences)
        return min(1.0, score / 10.0)