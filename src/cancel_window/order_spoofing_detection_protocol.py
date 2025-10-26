from typing import Protocol, Dict, runtime_checkable
from dynamic_risk_engine.cognitive_market_regime_classifier_protocol import CognitiveMarketRegimeClassifierProtocol, MarketRegime


@runtime_checkable
class OrderSpoofingDetectionProtocol(Protocol):
    regime_classifier: CognitiveMarketRegimeClassifierProtocol
    retention_ms: int
    burst_window_ms: int
    events: list[Dict[str, any]]

    def register_event(self, orderid: str, timestamp: int, event_type: str, price: float, size: float, side: str) -> None:
        """Registers an order spoofing related event."""
        ...

    def _prune(self) -> None:
        """Prunes old events outside the retention window."""
        ...

    def _summarize_cluster(self, side: str, cluster: list[Dict[str, any]]) -> Dict[str, any]:
        """Summarizes a cluster of spoofing events into a single cluster dictionary."""
        ...

    def detect_spoofing_clusters(self) -> list[Dict[str, any]]:
        """Detects clusters of spoofing behavior based on registered events."""
        ...

    def get_spoofing_score(self, side: str = None) -> float:
        """Calculates a spoofing score based on detected clusters and market regime."""
        ...