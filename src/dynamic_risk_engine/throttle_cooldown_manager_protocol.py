from typing import Protocol, Dict, runtime_checkable
from dynamic_risk_engine.cognitive_market_regime_classifier_protocol import CognitiveMarketRegimeClassifierProtocol, MarketRegime 
from dynamic_risk_engine.signal_confidence_calibrator_protocol import SignalConfidenceCalibratorProtocol
from cancel_window.simple_cancel_window_protocol import CancelWindowProtocol
from market_data.orderbook_protocol import OrderBookProtocol
import time
from collections import deque


@runtime_checkable
class ThrottleCooldownManagerProtocol(Protocol):
    confidence: SignalConfidenceCalibratorProtocol
    cancel_window: CancelWindowProtocol
    orderbook: OrderBookProtocol
    regime_classifier: CognitiveMarketRegimeClassifierProtocol

    last_reset: time
    daily_order_count: int

    volume_traded: float
    order_volume_total: float

    order_timestamps: deque
    cancel_timestamps: deque
    trade_timestamps: deque
    minute_weights: deque

    cooldown_until: int
    loss_streak: int

    max_losses: int
    cooldown_seconds: int
    max_trades_per_minute: int

    max_orders_per_10s: int
    max_orders_per: int
    max_weight_per_minute: int
    min_conversion_rate: float
    min_fill_weight: float

    def register_trade_result(self, pnl: float) -> None:
        """Registers a trade result and applies cooldown logic if loss streak exceeds threshold."""
        ...

    def is_in_cooldown(self) -> bool:
        """Returns True if currently in cooldown period due to loss streak."""
        ...

    def can_trade(self) -> bool:
        """Returns True if trading is allowed based on cooldown and trade rate limits."""
        ...

    def reset(self) -> None:
        """Resets internal state including cooldown, loss streak, and trade timestamps."""
        ...

    def record_order(self, volume: float = 1.0, weight: int = 1) -> None:
        """Logs an order submission and updates volume, weight, and counters."""
        ...

    def record_cancel(self) -> None:
        """Logs an order cancel event."""
        ...

    def record_fill(self, volume: float) -> None:
        """Logs a trade fill and updates filled volume."""
        ...

    def get_conversion_rate(self) -> float:
        """Returns the conversion rate: trades / (orders + cancels)."""
        ...

    def get_fill_weight(self) -> float:
        """Returns the fill weight: filled volume / ordered volume."""
        ...

    def get_weight_per_minute(self) -> float:
        """Returns the total API request weight over the past 60 seconds."""
        ...

    def is_throttled(self) -> bool:
        """Returns True if any throttle condition is violated (behavioral, rate, volume, or weight)."""
        ...

    def get_diagnostic(self) -> Dict[str, any]:
        """Returns a snapshot of current system state including limits, overlays, and regime context."""
        ...

    def get_status(self) -> dict:
        """Unified Diagnostic Snapshot"""
        ...

    def register_order(self, volume: float, weight: int = 1):
        """
        Register a new order event for throttling and volume tracking.
        """
        ...
    def register_cancel(self):
        """
        Register a cancel event for conversion rate tracking.
        """
        ...
    def get_conversion_rate(self) -> float:
        """
        Calculate the conversion rate: trades / (orders + cancels)
        """
        ...

    def get_fill_weight(self) -> float:
        """
        Calculate fill weight: volume traded / volume ordered
        """
        ...