from typing import Protocol, Dict, Any, List, Tuple, Optional, runtime_checkable

@runtime_checkable
class CancelWindowProtocol(Protocol):
    def _next_id(self) -> str:
        """Generates Unique ID for orders"""
        
    def process_l2_update(self, msg: Dict[str, Any]) -> None:
        """Processes L2 depth updates and detects cancel-based spoofing, iceberg, laddering, and density flags."""

    def process_trade(self, trade_msg: Dict[str, Any]) -> None:
        """Processes trade messages and matches them to recent cancels to flag fills and spoof behavior."""

    def register_cancel(self, timestamp: int, price: float, side: str, size: float) -> None:
        """Registers a cancel event and triggers spoof detection features."""

    def flush_flags(self) -> List[Dict[str, Any]]:
        """Returns and clears current flags (destructive). Use in streaming mode."""

    def get_flags(self) -> List[Dict[str, Any]]:
        """Returns current flags without clearing (non-destructive). Use for inspection/debugging."""

    def snapshot_state(self) -> Dict[str, Any]:
        """Returns a snapshot of internal state including flags, cancel cache, and density metrics."""

    def compute_cancel_density(self) -> Dict[Tuple[str, float], int]:
        """Computes cancel density per (side, price) level within the current window."""

    def get_cancel_density(self, side: str) -> Dict[float, int]:
        """Returns cancel density per price for a given side."""

    def get_normalized_cancel_density(self) -> Dict[str, float]:
        """Returns normalized cancel density metrics and composite score."""

    def compute_cancel_impact_score(self, price: float, side: str) -> float:
        """Returns a weighted score for cancel impact at a given price and side."""

    def set_cancel_density_params(self, initial_threshold: int, initial_window_ms: int) -> None:
        """Sets initial cancel density thresholds and evaluation window."""

    def get_window_ms(self) -> int:
        """Returns the current adaptive cancel window in milliseconds."""

    def update_midprice(self, mid_price: Optional[float] = None) -> float:
        """Updates or retrieves midprice for scoring purposes."""

    def flush(self) -> None:
        """Clears cancel and fill event buffers."""
