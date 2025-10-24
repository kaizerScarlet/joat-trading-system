from typing import List, Dict, Any
from dynamic_risk_engine.cognitive_market_regime_classifier_protocol import CognitiveMarketRegimeClassifierProtocol, MarketRegime
import time

class OrderIcebergDetection:
    """Detects iceberg cancels: multiple partial reductions before full cancel."""
    def __init__(self,regime_classifier: CognitiveMarketRegimeClassifierProtocol   , retention_ms: int = 300_000):
        self.regime_classifier = regime_classifier
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


    def get_iceberg_score(self, side: str | None = None) -> float:
        icebergs = self.detect_icebergs()
        if side:
            icebergs = [i for i in icebergs if i['side'] == side]
        if not icebergs:
            return 0.0

        # Regime and overlay context
        regime = self.regime_classifier.get_current_regime()
        overlay = self.regime_classifier.get_behavioral_overlay()

        # Regime-based weight modulation
        regime_weights = {
            MarketRegime.TRENDING: 1.2,
            MarketRegime.MEAN_REVERTING: 0.9,
            MarketRegime.VOLATILE: 1.5,
            MarketRegime.ILLIQUID: 1.3,
            MarketRegime.UNKNOWN: 1.0
        }
        regime_weight = regime_weights.get(regime, 1.0)

        # Overlay-based amplification
        overlay_boost = {
            "LIQUIDITY_VACUUM": 1.4,
            "MOMENTUM_EXHAUSTION": 1.2,
            "CHOPPY_NOISE": 0.8,
            "NORMAL": 1.0
        }
        overlay_factor = overlay_boost.get(overlay, 1.0)

        # Raw score: reduction count per iceberg
        raw_score = sum(i['reductions'] for i in icebergs) / 10.0

        # Final score with behavioral modulation
        score = raw_score * regime_weight * overlay_factor
        return min(1.0, score)
