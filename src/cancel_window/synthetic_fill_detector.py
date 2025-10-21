from typing import List, Dict, Any
from dynamic_risk_engine.cognitive_market_regime_classifier import CognitiveMarketRegimeClassifier, MarketRegime
import time

class SyntheticFillDetection:
    """Detects anomalous synthetic behaviour."""
    def __init__(self,regime_classifier:CognitiveMarketRegimeClassifier, retention_ms: int = 300_000):
        self.regime_classifier = regime_classifier
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
        cutoff = int(time.time() * 1000) - self.retention_ms
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


    def get_anomaly_score(self, side: str = None) -> float:
        by_side = {'ask': [], 'bid': []}
        for e in self.events:
            by_side[e['side']].append(e)

        if side not in by_side:
            return 0.0

        evs = by_side[side]
        true_fills = [e for e in evs if 'TRUE_FILL' in e['event_type']]
        weak_fills = [e for e in evs if 'WEAK' in e['event_type'] or 'NO_CANCEL' in e['event_type']]
        total = len(true_fills) + len(weak_fills)
        if total == 0:
            return 0.0

        # Regime and overlay context
        regime = self.regime_classifier.get_current_regime()
        overlay = self.regime_classifier.get_behavioral_overlay()

        # Regime-based weight modulation
        regime_weights = {
            MarketRegime.TRENDING: 1.2,
            MarketRegime.MEAN_REVERTING: 0.8,
            MarketRegime.VOLATILE: 1.5,
            MarketRegime.ILLIQUID: 1.3,
            MarketRegime.UNKNOWN: 1.0
        }
        regime_weight = regime_weights.get(regime, 1.0)

        # Overlay-based amplification
        overlay_boost = {
            "LIQUIDITY_VACUUM": 1.4,
            "MOMENTUM_EXHAUSTION": 1.2,
            "CHOPPY_NOISE": 0.9,
            "NORMAL": 1.0
        }
        overlay_factor = overlay_boost.get(overlay, 1.0)

        # Raw anomaly ratio
        raw_score = len(weak_fills) / total

        # Final score with behavioral modulation
        score = raw_score * regime_weight * overlay_factor
        return min(1.0, score)



