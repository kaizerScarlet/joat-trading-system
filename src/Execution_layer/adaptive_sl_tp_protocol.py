from typing import Protocol, Tuple, Optional, Dict, List, Any, runtime_checkable
import numpy as np
import time
from alpha_scoring.Alphablender_protocol import AlphaBlenderProtocol
from market_data.orderbook_protocol import OrderBookProtocol

@runtime_checkable
class AdaptiveSLTPProtocol(Protocol):
    ob: OrderBookProtocol
    alpha_score: Optional[AlphaBlenderProtocol]
    atr_window: int
    base_atr_multiplier: float
    vol_multiplier: float
    min_gap_ticks: float
    max_gap_multiplier: float
    tp_extension_factor: float
    alpha_weights: Optional[dict]

    highs: List[float]
    lows: List[float]
    closes: List[float]

    in_trade: bool
    side: Optional[str]
    entry_price: Optional[float]
    stop_loss: Optional[float]
    take_profit: Optional[float]
    sl_tightening_events: List[Dict[str, Optional[float]]]

    original_risk: Optional[float]

    def update_candlestick(self, high: float, low: float, close: float) -> None:
        """Adds OHLC candle data for ATR calculation."""
        ...

    def start_trade(self, side: str) -> Tuple[Optional[float], Optional[float]]:
        """Initializes SL and TP based on ATR and volatility. Returns (stop_loss, take_profit)."""
        ...

    def stop_trade(self) -> None:
        """Clears current trade state."""
        ...

    def monitor_and_adjust(self) -> None:
        """Adjusts SL and TP dynamically based on price, alpha score, and profit evolution."""
        ...

    def get_trailing_gap(self) -> Optional[float]:
        """Returns the current trailing gap based on composite score and midprice."""
        ...

    def get_sl_tp(self) -> Tuple[Optional[float], Optional[float]]:
        """Returns the current stop loss and take profit levels."""
        ...

    def debug_state(self) -> Dict[str, Any]:
        """Returns a snapshot of internal state for diagnostics and logging."""
        ...

    def get_regime_overlay_modulation(self) -> Tuple[float, float]:
        """
        Returns (sl_modulation, tp_modulation) based on regime and overlay context.
        """
        ...
