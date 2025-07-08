#src/cancel_window/interface.py
from abc import ABC, abstractmethod
from typing import Dict, List, Any

class CancelWindow(ABC):
    """
    Abstract Base Class for a cancel-window detector.
    Implementation turn raw order-book + trade messages into high quality event flags such as:
    * "CANCEL_SPOOF"
    * "PARTIAL_FILL"
    * "ICEBERG_FILL"
    * TRUE_SWEEP_FILL"

    """
    # ---- public API ---------------------------------------------------------------------------

    @abstractmethod
    def process_l2_update(self, l2_msg: Dict[str, Any]) -> None:
        """
        feed one Level-2 book update into the detector.
        The detector keeps internal state  (shadow book, recent trade, etc.)
        """
        pass

    @abstractmethod
    def process_trade(self, trade_msg: Dict[str, Any]) -> None:
        """
        Feed one Time-&-Sales (public trade) message.
        """
        pass

    @abstractmethod 
    def flush_flags(self) -> List[Dict[str, Any]]:
        """
        Return and clear any flags generated since last call.

        Each flag dict might look like:
        {
            "ts": 1697898979797,        #epoch-ms from exchange
            "symbol": "BTCUSDT",
            "event": "CANCEL_SPOOF",
            "price": 34250.5,
            "qty": 3.8,
            "side": "bid"

        }
        """
        pass


    # ---- optional knobs -------------------
    @abstractmethod
    def set_window_ms(self, window_ms: int) -> None:
        """
        Dynamically adjust +- time window for trade matching.
        """
        pass

    @abstractmethod
    def snapshot_state(self) -> Dict[str, Any]:
        """
        Return a serialisable snapshot of internal order-book state,
        so another process can warm-star (useful for fail-over)
        """
        pass