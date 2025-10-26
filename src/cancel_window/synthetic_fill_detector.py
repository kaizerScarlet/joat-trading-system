from typing import List, Dict, Any
from dynamic_risk_engine.cognitive_market_regime_classifier_protocol import CognitiveMarketRegimeClassifierProtocol, MarketRegime
import time

class SyntheticFillDetection:
    """Detects anomalous synthetic behaviour."""
    def __init__(self,regime_classifier:CognitiveMarketRegimeClassifierProtocol, retention_ms: int = 300_000):
        self.regime_classifier = regime_classifier
        self.retention_ms = retention_ms
        self.events: List[Dict[str, Any]] = []


    def register_event(self, orderid: str, timestamp: int, event_type: str, price, size: float, side: str) -> None:
        self.events.append({
            'orderid': orderid,
            'timestamp': timestamp,
            'event_type': event_type,
            'price': price,
            'size': size,
            'side': side
            })
        
        self._prune()


    def _prune(self) -> None:
        cutoff = int(time.time() * 1000) - self.retention_ms
        self.events = [e for e in self.events if e['timestamp'] >= cutoff]



    def detect_anomalies(self) -> List[Dict[str, Any]]:
        anomalies = []
        overlay = self.regime_classifier.get_behavioral_overlay()
        regime = self.regime_classifier.get_current_regime()
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
                    'weak_fills': len(weak_fills),
                    'overlay': overlay,
                    'regime': regime.value
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
            "AGGRESSIVE_SWEEP_UP": 1.3,
            "AGGRESSIVE_SWEEP_DOWN": 1.3,
            "REVERSION_TRAP_UP": 1.1,
            "REVERSION_TRAP_DOWN": 1.1,
            "PASSIVE_FADE": 1.2,
            "CROSS_SIDE_TENSION": 1.1,
            "LAYER_WIPE": 1.4,
            "CANCEL_DENSITY_SPIKE": 1.3,
            "CHOPPY_NOISE": 0.9,
            "NORMAL": 1.0
        }
        overlay_factor = overlay_boost.get(overlay, 1.0)

        #Directional boost if overlay direction matches side
        if "_" in overlay:
            _, overlay_direction = overlay.split("_", 1)
            if side and side == overlay_direction.lower():
                overlay_factor *= 1.1

        # Raw anomaly ratio
        raw_score = len(weak_fills) / total

        # Final score with behavioral modulation
        score = raw_score * regime_weight * overlay_factor
        return min(1.0, score)
    
    def get_debug_view(self) -> Dict[str, Any]:
        self._prune()
        anomalies = self.detect_anomalies()
        overlay = self.regime_classifier.get_behavioral_overlay()
        regime = self.regime_classifier.get_current_regime()
        if "_" in overlay:
            overlay_type, overlay_direction = overlay.split("_", 1)
        else:
            overlay_type, overlay_direction = overlay, "NEUTRAL"

        return {
            "regime": regime.value,
            "overlay": overlay,
            "overlay_type": overlay_type,
            "overlay_direction": overlay_direction,
            "anomaly_score_bid": self.get_anomaly_score("bid"),
            "anomaly_score_ask": self.get_anomaly_score("ask"),
            "anomaly_count": len(anomalies),
            "recent_anomalies": anomalies[-3:]
        }



