from typing import Protocol, Dict, Any, List, runtime_checkable
from dynamic_risk_engine.cognitive_market_regime_classifier_protocol import CognitiveMarketRegimeClassifierProtocol, MarketRegime

@runtime_checkable
class SyntheticFillDetectorProtocol(Protocol):
    regime_classifier: CognitiveMarketRegimeClassifierProtocol
    retention_ms: int
    events: List[Dict[str, Any]]

    def register_event(self, orderid: str, timestamp: int, event_type: str, price, size: float, side: str) -> None:
        """Register event"""
        ...

    def _prune(self) -> None:
        """Prune events outside the rentention window"""
        ...

    def detect_anomalies(self) -> List[Dict[str, Any]]:
        """Detect Anomalies"""
        ...

    def get_anomaly_score(self, side: str | None = None) -> float:
        """Get anomaly score"""
        ...

    