from typing import Protocol, Dict, runtime_checkable
from datetime import datetime
from dynamic_risk_engine.performance_tracker_protocol import PerformanceTrackerProtocol
from dynamic_risk_engine.daily_drawdown_manager_protocol import DailyDrawdownManagerProtocol
from dynamic_risk_engine.signal_confidence_calibrator_protocol import SignalConfidenceCalibratorProtocol
from dynamic_risk_engine.dynamic_position_sizer_protocol import DynamicPositionSizerProtocol
from dynamic_risk_engine.throttle_cooldown_manager_protocol import ThrottleCooldownManagerProtocol
from Execution_layer.binance_adapter_protocol import BinanceExecutionAdapterProtocol
from market_data.orderbook_protocol import OrderBookProtocol
from dynamic_risk_engine.cognitive_market_regime_classifier_protocol import  CognitiveMarketRegimeClassifierProtocol, MarketRegime
from cancel_window.simple_cancel_window_protocol import CancelWindowProtocol

@runtime_checkable
class DynamicRiskEngineProtocol(Protocol):
    performance_tracker: PerformanceTrackerProtocol
    daily_drawdown_manager: DailyDrawdownManagerProtocol
    signal_confidence_calibrator: SignalConfidenceCalibratorProtocol
    dynamic_position_sizer: DynamicPositionSizerProtocol
    throttle_cooldown_manager: ThrottleCooldownManagerProtocol
    binance_adapter: BinanceExecutionAdapterProtocol
    orderbook : OrderBookProtocol
    cancel_window: CancelWindowProtocol
    market_regime_classifier: CognitiveMarketRegimeClassifierProtocol
    current_regime: MarketRegime
    initial_balance: None
    max_risk_per_trade: None

    async def initialize(self) -> None:
        """Initializes all internal modules and sets account balance and risk parameters."""
        ...

    def update_market_regime(self) -> None:
        """Updates the current market regime using the classifier."""
        ...

    def can_trade(self) -> bool:
        """Returns True if trading is allowed based on drawdown and cooldown state."""
        ...

    def get_risk_for_trade(self) -> float:
        """Returns the current max risk per trade."""
        ...

    async def get_position_size(self, stop_loss_distance: float) -> float:
        """Returns the optimal position size based on current risk and regime context."""
        ...

    def register_trade(self, pnl: float, risk: float, reward: float, signal_id: str, was_correct: bool, metadata: Dict = None) -> None:
        """Registers a trade and updates all internal trackers and calibrators."""
        ...

    def get_risk_curve_value(self) -> float:
        """Returns the current risk curve value based on signal confidence."""
        ...

    async def reset(self) -> None:
        """Resets all internal state (e.g., start of day)."""
        ...

    async def get_diagnostic(self) -> Dict[str, any]:
        """Returns full diagnostic snapshot of the risk engine state."""
        ...

    async def get_debug_view(self) -> dict:
        """Debug view for introspection and debugging"""
        ...

    async def get_trade_rationale(self, stop_loss_distance: float) -> dict:
        """This lets you explain every trade with behavioral clarity."""
        ...
