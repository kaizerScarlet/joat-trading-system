from typing import Protocol, Dict, List, runtime_checkable, Any
from dynamic_risk_engine.cognitive_market_regime_classifier_protocol import CognitiveMarketRegimeClassifierProtocol

@runtime_checkable
class CancelDensityDetectionProtocol(Protocol):
    regime_classifier: CognitiveMarketRegimeClassifierProtocol
    window_ms: int
    threshold: int
    events: List[Dict[str, Any]]

    def register_cancel(self, orderid: str, timestamp: int, event_type, price: float, size:float ,  side: str):
        """Registers a cancel event."""
        ...

    def _prune(self, current_time: int = None) -> None:
        """Prunes old events outside the detection window."""
        ...

    def detect_spikes(self, current_time: int = None) -> List[Dict[str, Any]]:
        """Detects cancel density spikes within the current window."""
        ...

    def get_density_score(self, side: str = None, current_time: int = None) -> float:
        """Calculates a density score based on detected spikes and market regime."""
        ...
    
    

    