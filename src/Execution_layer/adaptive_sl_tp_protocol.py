from typing import Protocol, Tuple, Optional, Dict, runtime_checkable

@runtime_checkable
class AdaptiveSLTPProtocol(Protocol):
    def update_candlestick(self, high: float, low: float, close: float) -> None:
        """Adds OHLC candle data for ATR calculation."""

    def start_trade(self, side: str) -> Tuple[Optional[float], Optional[float]]:
        """Initializes SL and TP based on ATR and volatility. Returns (stop_loss, take_profit)."""

    def stop_trade(self) -> None:
        """Clears current trade state."""

    def monitor_and_adjust(self) -> None:
        """Adjusts SL and TP dynamically based on price, alpha score, and profit evolution."""

    def get_trailing_gap(self) -> Optional[float]:
        """Returns the current trailing gap based on composite score and midprice."""

    def get_sl_tp(self) -> Tuple[Optional[float], Optional[float]]:
        """Returns the current stop loss and take profit levels."""

    def debug_state(self) -> Dict[str, any]:
        """Returns a snapshot of internal state for diagnostics and logging."""
