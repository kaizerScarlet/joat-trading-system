from collections import defaultdict
from dynamic_risk_engine.cognitive_market_regime_classifier import CognitiveMarketRegimeClassifier, MarketRegime
from typing import List, Dict, Any
import time

class OrderSpoofingDetection:
    """
    Detects spoofing behaviors based on short-lived orders and cancel bursts.
    Inputs: events like CANCEL_SPOOF, PING_CANCEL, REPOSTING_BEHAVIOUR, BURST_CANCEL.
    Output: clusters summarizing spoof-like bursts per side.
    """
    def __init__(self, regime_classifier:CognitiveMarketRegimeClassifier,  retention_ms: int = 300_000, burst_window_ms: int = 250):
        self.regime_classifier = regime_classifier
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

    def _summarize_cluster(self, side: str, cluster: list[Dict[str, any]]) -> Dict[str, Any]:
        avg_price = sum(e['price'] for e in cluster) / len(cluster)
        return {
            'side': side,
            'count': len(cluster),
            'avg_price': avg_price,
            'duration_ms': cluster[-1]['timestamp'] - cluster[0]['timestamp'],
            'types': list({e['event_type'] for e in cluster})
        }

    def get_spoofing_score(self, side: str = None) -> float:
        clusters = self.detect_spoofing_clusters()
        if side:
            clusters = [c for c in clusters if c['side'] == side]
        if not clusters:
            return 0.0

        # Regime and overlay context
        regime = self.regime_classifier.get_current_regime()
        overlay = self.regime_classifier.get_behavioral_overlay()

        # Regime-based weight modulation
        regime_weights = {
            MarketRegime.TRENDING: 0.8,
            MarketRegime.MEAN_REVERTING: 1.2,
            MarketRegime.VOLATILE: 1.5,
            MarketRegime.ILLIQUID: 1.3,
            MarketRegime.UNKNOWN: 1.0
        }
        weight = regime_weights.get(regime, 1.0)

        # Overlay-based amplification
        overlay_boost = {
            "LIQUIDITY_VACUUM": 1.4,
            "MOMENTUM_EXHAUSTION": 1.2,
            "CHOPPY_NOISE": 0.8,
            "NORMAL": 1.0
        }
        overlay_factor = overlay_boost.get(overlay, 1.0)

        # Density scoring
        densities = [c['count'] / (c['duration_ms'] + 1) for c in clusters]
        max_density = max(densities)
        avg_duration = sum(c['duration_ms'] for c in clusters) / len(clusters)

        adjusted_scores = [
            (d / max_density) * (avg_duration / (c['duration_ms'] + 1))
            for d, c in zip(densities, clusters)
        ]

        # Final score with regime and overlay modulation
        score = sum(adjusted_scores) * weight * overlay_factor
        return min(1.0, score)


