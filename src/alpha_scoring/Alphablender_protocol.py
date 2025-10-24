from typing import Protocol, Dict, Optional, runtime_checkable

@runtime_checkable
class AlphaBlenderProtocol(Protocol):
    weights: Dict[str, float]
    blending_method: str
    adaptive: bool

    def update_signals(
        self,
        timestamp: int,
        signal_scores: Dict[str, float],
        side: str = 'bid'
    ) -> None:
        """Stores latest signal values per side for blending."""
        ...

    def compute_alpha_score(
        self,
        timestamp: Optional[int] = None
    ) -> Dict[str, float]:
        """Returns blended alpha score per side using selected strategy (weighted, min, max)."""
        ...

    def update_trade_feedback(
        self,
        signal_scores: Dict[str, float],
        pnl: float,
        side: str = 'bid'
    ) -> None:
        """Updates signal performance tracking after a trade and recalculates dynamic weights."""
        ...

    def _recalculate_dynamic_weights(self, side: str) -> None:
        """Recomputes adaptive weights based on historical signal performance for the given side."""
        ...
    
    def get_debug_view(self) -> Dict[str, Dict]:
        """Returns detailed internal state for introspection (weights, signals, scores, performance)."""
        ...

    def reset(self) -> None:
        """Resets all stored signal states and performance history."""
        ...
