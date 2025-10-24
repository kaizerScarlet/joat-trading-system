from typing import Protocol, Dict, runtime_checkable, Any, List
from dynamic_risk_engine.cognitive_market_regime_classifier_protocol import CognitiveMarketRegimeClassifierProtocol, MarketRegime

@runtime_checkable
class OrderLadderingDetectionProtocol(Protocol):
    regime_classifier: CognitiveMarketRegimeClassifierProtocol
    retention_ms: int 
    step_window_ms: int
    events: List[Dict[str, Any]]

    def register_event(self, orderid: str, timestamp: int, event_type: str, price: float, size: float, side: str):
        """Register Events"""
        ...

    def _prune(self):
        """Prune"""
        ...

    def detect_laddering_sequeces(self) -> List[Dict[str, Any]]:
        """
        Detects sequential price-stepping patterns:
        orders placed/canceled in progressive price directions (ladder-like).
        """
        ...

    def _summarize_sequence(self, side, seq):
        """Summarize sequence"""
        ...

    
    def get_laddering_score(self) -> float:
        """get laddering Score"""
        ...