from typing import TYPE_CHECKING, Protocol, runtime_checkable, Dict, Any
from collections import deque
from datetime import datetime
from enum import Enum
from market_data.orderbook_protocol import OrderBookProtocol
from dynamic_risk_engine.signal_confidence_calibrator_protocol import SignalConfidenceCalibratorProtocol

if TYPE_CHECKING:
    from cancel_window.simple_cancel_window_protocol import CancelWindowProtocol

class MarketRegime(Enum):
    TRENDING = "trending"
    MEAN_REVERTING = "mean_reverting"
    VOLATILE = "volatile"
    ILLIQUID = "illiquid"
    UNKNOWN = "unknown"

@runtime_checkable
class CognitiveMarketRegimeClassifierProtocol(Protocol):
    orderbook: OrderBookProtocol
    signal_calibrator: SignalConfidenceCalibratorProtocol 
    cancel_window: "CancelWindowProtocol"  # <— quoted forward reference
    regime_history: deque[int]
    last_regime: MarketRegime
    last_regime_change: datetime

    def classify_environment(self) -> MarketRegime:
        """Classifies current market regime"""
        ...
        
    def reinforce_regime(self, base_regime: MarketRegime)-> MarketRegime:
        """Reinforces market Regime"""
        ...

    def update_regime(self) -> MarketRegime:
        """Classify and reinforces the current market regime, logs drift and overlays."""
        ...
    
    def get_current_regime(self) -> MarketRegime:
        """Returns the most dominant market regime from recent history."""
        ...

    def get_regime_duration_seconds(self) -> float:
        """Returns how long the current regime has persisted in seconds."""
        ...
    
    def get_regime_stability(self) -> float:
        """Returns a float between 0 and 1 indicating how stable the regime is."""
        ...

    def detect_regime_drift(self) -> bool:
        """Returns True if behavioral mutation is detected within the current regime."""
        ...

    def get_behavioral_overlay(self) -> str:
        """Returns overlay label like 'LIQUIDITY_VACUUM, 'MOMENTUM_EXHAUSTION', or 'NORMAL'."""
        ...

    def get_scoring_weights(self) -> tuple[float, float, float, float]:
        """
        Returns weights for the four components used in cancel impact scoring.
        Adjust these weights based on your strategy's sensitivity to each factor.
        """
        ...

    def get_debug_view(self) -> Dict[str, Any]:
        """Debug view for introspection and debugging"""
        ...

    def get_velocity_thresholds(self) -> tuple[float, float]:
        """
        Dynamically compute velocity thresholds for execution reflex.
        Returns (velocity_fast, velocity_slow) in qty/sec.
        """
        ...