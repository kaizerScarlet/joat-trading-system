from typing import Protocol, Dict, List, Any, runtime_checkable
from dynamic_risk_engine.cognitive_market_regime_classifier_protocol import CognitiveMarketRegimeClassifierProtocol

@runtime_checkable
class OrderIcebergDetectionProtocol(Protocol):
    regime_classifier: CognitiveMarketRegimeClassifierProtocol
    retention_ms: int
    events: List[Dict[str, Any]]

    def register_event(self, orderid: str, timestamp: int, event_type: str, price: float, size: float, side: str)-> None:
        """Registers an order event for iceberg detection."""
        ...

    def _prune(self) -> None:
        """Prunes old events beyond the retention period."""
        ...

    def detect_icebergs(self) -> List[Dict[str, Any]]:
        """Detects and returns a list of identified iceberg orders."""
        ...

    def get_iceberg_score(self, side: str = None) -> float:
        """Computes and returns the iceberg order score """
        ...