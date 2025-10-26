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
        overlay = self.regime_classifier.get_behavioral_overlay()
        self.events.append({'orderid': orderid, 'timestamp': timestamp, 'event_type': event_type,
                            'price': price, 'size': size, 'side': side, 'overlay': overlay})
        self._prune()

    def _prune(self):
        cutoff = int(time.time() * 1000) - self.retention_ms
        self.events = [e for e in self.events if e['timestamp'] >= cutoff]

    def detect_icebergs(self) -> List[Dict[str, Any]]:
        icebergs = []

        overlay = self.regime_classifier.get_behavioral_overlay()
        regime = self.regime_classifier.get_current_regime()

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
                    'duration': evts[-1]['timestamp'] - evts[0]['timestamp'],
                    'overlay': overlay,
                    'regime': regime.value
                })

                #Optional symbolic trace
                if overlay.startswith("LIQUIDITY_MIRAGE") or overlay.startswith("AGGRESSIVE_SWEEP"):
                    print(f"[Iceberg Detected] {oid} under {overlay} in {regime.value} regime → spoof setup likely")
                
        return icebergs


    def get_iceberg_score(self, side: str = None) -> float:
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
            "LIQUIDITY_VACUUM": 1.5,
            "MOMENTUM_EXHAUSTION": 1.1,
            "CHOPPY_NOISE": 0.8,
            "NORMAL": 1.0,
            "LIQUIDITY_MIRAGE_UP": 1.4,
            "LIQUIDITY_MIRAGE_DOWN": 1.4,
            "AGGRESSIVE_SWEEP_UP": 1.2,
            "AGGRESSIVE_SWEEP_DOWN": 1.2,
            "REVERSION_TRAP_UP": 1.2,
            "REVERSION_TRAP_DOWN": 1.2,
            "PASSIVE_FADE": 1.1,
            "CROSS_SIDE_TENSION": 1.1
        }
        overlay_factor = overlay_boost.get(overlay, 1.0)

        #Optional: amplify if overlay direction matches iceberg side
        if side and overlay.endswith(side.upper()):
            overlay_factor *= 1.1 #Extra boost for directional alignment

        # Raw score: reduction count per iceberg
        raw_score = sum(i['reductions'] for i in icebergs) / 10.0

        # Final score with behavioral modulation
        score = raw_score * regime_weight * overlay_factor
        return min(1.0, score)


    def get_debug_view(self) -> Dict[str, Any]:
        regime = self.regime_classifier.get_current_regime()
        overlay = self.regime_classifier.get_behavioral_overlay()
        if "_" in overlay:
            overlay_type, overlay_direction = overlay.split("_", 1)
        else:
            overlay_type, overlay_direction = overlay, "NEUTRAL"

        icebergs = self.detect_icebergs()
        iceberg_score_bid = self.get_iceberg_score("bid")
        iceberg_score_ask = self.get_iceberg_score("ask")
        raw_score = sum(i['reductions'] for i in icebergs) / 10.0

        return {
            "regime": regime.value,
            "overlay": overlay,
            "overlay_direction": overlay_direction,
            "iceberg_count": len(icebergs),
            "iceberg_score_bid": iceberg_score_bid,
            "iceberg_score_ask": iceberg_score_ask,
            "raw_score": raw_score,
            "recent_icebergs": icebergs[-5:]
        }

