from typing import Protocol, Dict, Any, runtime_checkable

@runtime_checkable
class AlphaSignalPipelineProtocol(Protocol):
    def update_market(self, timestamp: int, market_snapshot: Dict[str, Any]) -> None:
        """Feeds market snapshot into scorers and updates signal values per side."""
        ...

    def get_alpha_signal(self) -> Dict[str, float]:
        """Returns the current blended alpha signal per side."""
        ...

    def trade_feedback(self, signal_dict: Dict[str, float], pnl: float, side: str) -> None:
        """Updates signal performance tracking based on trade outcome and adjusts weights if adaptive."""
        ...

    def get_debug(self) -> Dict[str, Any]:
        """Returns internal diagnostics including weights, signals, scores, and performance history."""
        ...

    def reset(self) -> None:
        """Resets all scorers and blender state for a fresh scoring cycle."""
        ...
