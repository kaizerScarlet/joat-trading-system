from typing import Protocol, Dict
from datetime import datetime
from dynamic_risk_engine.signal_confidence_calibrator_protocol import SignalConfidenceCalibratorProtocol
from dynamic_risk_engine.performance_tracker_protocol import PerformanceTrackerProtocol
from market_data.orderbook_protocol import OrderBookProtocol
from dynamic_risk_engine.daily_drawdown_manager_protocol import DailyDrawdownManagerProtocol
from Execution_layer.binance_adapter_protocol import BinanceExecutionAdapterProtocol


class DynamicPositionSizerProtocol(Protocol):
    account_balance: BinanceExecutionAdapterProtocol
    confidence: SignalConfidenceCalibratorProtocol
    win_rate: PerformanceTrackerProtocol
    volatility: OrderBookProtocol
    drawdown: DailyDrawdownManagerProtocol
    stop_loss: BinanceExecutionAdapterProtocol
    max_risk_per_trade: None

    async def initialize(self) -> None:
        """Initializes the position sizer by computing max risk per trade."""
        ...

    async def calculate_position_size(self, stop_loss_distance: float) -> float:
        """Calculates position size based on volatility, confidence, win rate, and drawdown throttle."""
        ...

    async def get_sizing_diagnostics(self, stop_loss_distance: float) -> Dict[str, float]:
        """Returns detailed diagnostics used in position sizing logic."""
        ...

    async def reset(self) -> None:
        """Resets the position sizer to initial state."""
        ...

    def _compute_max_risk_per_trade(self) -> float:
        """return max risk per trade"""
        ...

    def get_drawdown_throttle(self) -> float:
        """Returns throttle factor based on current drawdown severity."""
        ...

    async def get_debug_view(self, stop_loss_distance: float) -> dict:
        """
        Returns a detailed debug snapshot of the position sizing logic.
        Includes behavioral inputs, risk calibration, and sizing rationale.
        """
        ...
