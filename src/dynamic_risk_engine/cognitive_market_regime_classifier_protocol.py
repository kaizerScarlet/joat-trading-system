from typing import Protocol, runtime_checkable, Dict, Any
from enum import Enum

class MarketRegime(Enum):
    TRENDING = "trending"
    MEAN_REVERTING = "mean_reverting"
    VOLATILE = "volatile"
    ILLIQUID = "illiquid"
    UNKNOWN = "unknown"

@runtime_checkable
class CognitiveMarketRegimeClassifierProtocol(Protocol):
    def classify_environment(self) -> MarketRegime:
        """Classifies current market regime"""
        
    def reinforce_regime(self, base_regime: MarketRegime)-> MarketRegime:
        """Reinforces market Regime"""

    def update_regime(self) -> MarketRegime:
        """Classify and reinforces the current market regime, logs drift and overlays."""
    
    def get_current_regime(self) -> MarketRegime:
        """Returns the most dominant market regime from recent history."""

    def get_regime_duration_seconds(self) -> float:
        """Returns how long the current regime has persisted in seconds."""
    
    def get_regime_stability(self) -> float:
        """Returns a float between 0 and 1 indicating how stable the regime is."""

    def detect_regime_drift(self) -> bool:
        """Returns True if behavioral mutation is detected within the current regime."""

    def get_behavioral_overlay(self) -> str:
        """Returns overlay label like 'LIQUIDITY_VACUUM, 'MOMENTUM_EXHAUSTION', or 'NORMAL'."""

    def get_scoring_weights(self) -> tuple[float, float, float, float]:
        """
        Returns weights for the four components used in cancel impact scoring.
        Adjust these weights based on your strategy's sensitivity to each factor.
        """

    def get_debug_view(self) -> Dict[str, Any]:
        """Debug view for introspection and debugging"""
