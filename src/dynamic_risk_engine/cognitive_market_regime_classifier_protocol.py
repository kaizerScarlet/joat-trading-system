from typing import Protocol, runtime_checkable
from enum import Enum

class MarketRegime(Enum):
    TRENDING = "trending"
    MEAN_REVERTING = "mean_reverting"
    VOLATILE = "volatile"
    ILLIQUID = "illiquid"
    UNKNOWN = "unknown"

@runtime_checkable
class CognitiveMarketRegimeClassifierProtocol(Protocol):
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
