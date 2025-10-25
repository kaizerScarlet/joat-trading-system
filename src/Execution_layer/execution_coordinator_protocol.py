from typing import Protocol, Optional, Dict, Tuple, Any, runtime_checkable
import logging
from alpha_scoring.alpha_pipeline_protocol import AlphaSignalPipelineProtocol
from cancel_window.simple_cancel_window_protocol import CancelWindowProtocol

from cancel_window.order_spoofing_detection_protocol import OrderSpoofingDetectionProtocol
from cancel_window.synthetic_fill_detector_protocol import SyntheticFillDetectorProtocol
from cancel_window.order_laddering_detection_protocol import OrderLadderingDetectionProtocol
from cancel_window.order_iceberg_detection_protocol import OrderIcebergDetectionProtocol
from cancel_window.cancel_denisty_detection_protocol import CancelDensityDetectionProtocol

from dynamic_risk_engine.dynamic_risk_engine_protocol import DynamicRiskEngineProtocol
from dynamic_risk_engine.throttle_cooldown_manager_protocol import ThrottleCooldownManagerProtocol
from dynamic_risk_engine.performance_tracker_protocol import PerformanceTrackerProtocol
from Execution_layer.binance_adapter_protocol import BinanceExecutionAdapterProtocol
from Execution_layer.mock_adapter import MockExchangeAdapter #For testing and dry runs
from dynamic_risk_engine.signal_confidence_calibrator_protocol import SignalConfidenceCalibratorProtocol
from dynamic_risk_engine.dynamic_position_sizer_protocol import DynamicPositionSizerProtocol
from market_data.orderbook_protocol import OrderBookProtocol
from dynamic_risk_engine.daily_drawdown_manager_protocol import DailyDrawdownManagerProtocol
from dynamic_risk_engine.cognitive_market_regime_classifier_protocol import CognitiveMarketRegimeClassifierProtocol, MarketRegime
from Execution_layer.adaptive_sl_tp_protocol import AdaptiveSLTPProtocol
from Execution_layer.stealth_router_protocol import StealthRouterProtocol
from Execution_layer.fee_schedule_protocol import FeeScheduleProtocol
from Execution_layer.slippage_model_protocol import SlippageModelProtocol
from Execution_layer.latency_model_protocol import LatencyModelProtocol
from Execution_layer.queue_position_model_protocol import QueuePositionModelProtocol
from alpha_scoring.order_age_distribution_scorer_protocol import OrderAgeDistributionScorerProtocol
from alpha_scoring.Order_layering_scorer_protocol import LayeringScoringProtocol
from alpha_scoring.cancel_activity_scorer_protocol import CancelActivityScorerProtocol
import asyncio
import time
from datetime import datetime

@runtime_checkable
class ExecutionCoordinatorProtocol(Protocol):
    alpha_pipeline: AlphaSignalPipelineProtocol
    risk_engine: DynamicRiskEngineProtocol
    throttle_manager: ThrottleCooldownManagerProtocol
    drawdown_manager: DailyDrawdownManagerProtocol
    exchange_client: BinanceExecutionAdapterProtocol
    performance_tracker: PerformanceTrackerProtocol
    confidence: SignalConfidenceCalibratorProtocol
    dynamic_position_sizer: DynamicPositionSizerProtocol
    cancel_window: CancelWindowProtocol
    orderbook: OrderBookProtocol

    regime_classifier: CognitiveMarketRegimeClassifierProtocol
    spoofing_detector: CancelActivityScorerProtocol
    layering_scorer: LayeringScoringProtocol
    order_age_scorer: OrderAgeDistributionScorerProtocol
    cancel_density_detector: CancelDensityDetectionProtocol
    order_ladder_tracker: OrderLadderingDetectionProtocol
    iceberg_detector: OrderIcebergDetectionProtocol
    synthetic_fill_detector: SyntheticFillDetectorProtocol
    cancel_spoof_scorer: OrderSpoofingDetectionProtocol

    config: Optional[Dict]
    sl_and_tp: AdaptiveSLTPProtocol


    async def reconcile_open_orders(self) -> None:
        """Fetches open orders from exchange and reconciles with local state."""
        ...

    def now_ms(self) -> int:
        """Returns current time in milliseconds adjusted by server offset."""
        ...

    def on_new_alpha(self, alpha: Dict[str, float], market_snapshot: Dict) -> None:
        """Handles new alpha signal and decides whether to trade."""
        ...

    def on_market_tick(self, high: Optional[float] = None, low: Optional[float] = None, close: Optional[float] = None) -> None:
        """Handles market tick updates, adjusts SL/TP, and syncs with exchange."""
        ...

    def monitor_open_positions(self) -> None:
        """Syncs open positions with exchange and updates SL/TP if needed."""
        ...

    def _reset_position_state(self) -> None:
        """Resets internal position tracking state."""
        ...

    def _check_pre_trade_conditions(self) -> bool:
        """Runs confidence, throttle, and risk checks before trade execution."""
        ...

    def _compute_order_size(self, stop_loss_distance: float) -> float:
        """Computes order size based on stop loss distance and dynamic sizing logic."""
        ...

    def _choose_order_type_and_price(self, side: str, order_size: float) -> Tuple[str, Optional[float]]:
        """Selects order type and price based on spread, slippage, fees, and queue dynamics."""
        ...

    def _execute_order(
        self,
        side: str,
        size: float,
        order_type: str,
        price: Optional[float],
        ts: float,
        base_sl: float,
        base_tp: float,
        side_for_sl: str
    ) -> None:
        """Executes order via StealthRouter with latency, slippage, and behavioral metadata."""
        ...

    async def _on_fill(self, fill: Dict[str, Any]) -> None:
        """Handles fill events, updates SL/TP, and reconciles position state."""
        ...

    def _update_sl_tp_after_slice(self, qty: float, side: str) -> None:
        """Adjusts SL/TP dynamically after stealth slice fills."""
        ...

    def _decide_trade_side(self) -> Optional[str]:
        """Decides trade direction based on alpha, regime, spoofing, and layering scores."""
        ...
