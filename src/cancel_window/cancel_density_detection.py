from collections import defaultdict
from typing import List, Dict, Any
from dynamic_risk_engine.cognitive_market_regime_classifier_protocol import CognitiveMarketRegimeClassifierProtocol, MarketRegime
import time

class CancelDensityDetection:
    """Detects abnormal cancel concentration (CANCEL_DENSITY_SPIKE, LAYER_WIPE)."""
    def __init__(self,regime_classifier: CognitiveMarketRegimeClassifierProtocol, window_ms: int = 1000, threshold: int = 5):
        self.regime_classifier = regime_classifier
        self.window_ms = window_ms
        self.threshold = threshold
        self.events: List[Dict[str, Any]] = []

    def register_cancel(self, orderid: str, timestamp: int, event_type, price: float, size:float ,  side: str):
        self.events.append({
            'orderid': orderid,
            'timestamp': timestamp,
            'event_type': event_type,
            'size': size,
            'price': price, 
            'side': side})
        
        self._prune(timestamp)

    def _prune(self, current_time: int | None = None) -> None:
        current_time = current_time or int(time.time() * 1000)
        cutoff = current_time - self.window_ms
        self.events = [e for e in self.events if e['timestamp'] >= cutoff]

    def detect_spikes(self, current_time: int | None = None) -> List[Dict[str, Any]]:
        current_time = current_time or int(time.time() * 1000)
        cutoff = current_time - self.window_ms
        by_side = defaultdict(list)
        for e in self.events:
            if e['timestamp'] >= cutoff: 
                by_side[e['side']].append(e)
        spikes = []
        for side, evs in by_side.items():
            prices = [e['price'] for e in evs]
            if len(prices) >= self.threshold:
                spikes.append({'side': side, 'count': len(prices), 'unique_prices': len(set(prices))})
        return spikes

    def get_density_score(self, side: str | None = None, current_time: int = None) -> float:
        spikes = self.detect_spikes(current_time=current_time)
        if side:
            spikes = [s for s in spikes if s['side'] == side]
        if not spikes:
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
            "LAYER_WIPE": 1.4,
            "CANCEL_DENSITY_SPIKE": 1.3,
            "CHOPPY_NOISE": 0.8,
            "NORMAL": 1.0
        }
        overlay_factor = overlay_boost.get(overlay, 1.0)

        # Raw score: cancel count per side
        raw_score = sum(s['count'] for s in spikes) / 50.0

        # Final score with behavioral modulation
        score = raw_score * regime_weight * overlay_factor
        return min(1.0, score)
