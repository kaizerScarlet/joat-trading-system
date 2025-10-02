from typing import Protocol, Dict, Optional

class AlphaBlenderProtocol(Protocol):
    def update_signals(
        self,
        timestamp: int,
        signal_scores: Dict[str, float],
        side: str = 'bid'
    ) -> None:
        """Stores latest signal values per side for blending."""

    def compute_alpha_score(
        self,
        timestamp: Optional[int] = None
    ) -> Dict[str, float]:
        """Returns blended alpha score per side using selected strategy (weighted, min, max)."""

    def update_trade_feedback(
        self,
        signal_scores: Dict[str, float],
        pnl: float,
        side: str = 'bid'
    ) -> None:
        """Updates signal performance tracking after a trade and recalculates dynamic weights."""

    def get_debug_view(self) -> Dict[str, Dict]:
        """Returns detailed internal state for introspection (weights, signals, scores, performance)."""

    def reset(self) -> None:
        """Resets all stored signal states and performance history."""
