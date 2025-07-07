from typing import Dict, Any, List
from .interface import CancelWindow #samefolder

class SimpleCancelWindow(CancelWindow):
    """
    Minimal stub so test and replay-runner import cleanly.
    Replace with real logic later.
    """
    def __init__(self, window_ms: int = 75):
        self.window_ms = window_ms
        self._flags: List[Dict[str, Any]] = []

    def process_l2_update(self, l2_msg: Dict[str, Any]) -> None:
        # TODO: add real logic
        pass

    def process_trade(self, trade_msg: Dict[str, Any]) -> None:
        # TODO: add real logic
        pass

    def flush_flags(self) -> List[Dict[str, Any]]:
        out, self._flags = self._flags, []
        return out
