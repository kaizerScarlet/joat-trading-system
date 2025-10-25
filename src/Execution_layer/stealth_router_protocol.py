from typing import Protocol, Optional, List, Dict
import asyncio
import random
from typing import Optional
import time
import logging
from market_data.orderbook_protocol import OrderBookProtocol
from Execution_layer.fee_schedule_protocol import FeeScheduleProtocol
from Execution_layer.slippage_model_protocol import SlippageModelProtocol
from Execution_layer.queue_position_model_protocol import QueuePositionModelProtocol 
from Execution_layer.binance_adapter_protocol import BinanceExecutionAdapterProtocol
from Execution_layer.smart_pricing_model_protocol import SmartRepricingModelProtocol
from dynamic_risk_engine.cognitive_market_regime_classifier_protocol import CognitiveMarketRegimeClassifierProtocol, MarketRegime
from dynamic_risk_engine.signal_confidence_calibrator_protocol import SignalConfidenceCalibratorProtocol
from cancel_window.simple_cancel_window_protocol import CancelWindowProtocol

class StealthRouterProtocol(Protocol):
    exchange_client: BinanceExecutionAdapterProtocol
    symbol: str
    min_slice_usd: float
    max_slice_usd: float
    slippage_bps: float
    queue_model: QueuePositionModelProtocol
    regime_classifier: CognitiveMarketRegimeClassifierProtocol
    execution_log: List[Dict]
    repricing_model: SmartRepricingModelProtocol
    slippage_model: SlippageModelProtocol
    orderbook: OrderBookProtocol

    async def execute_parent_order(
        self,
        side: str,
        total_qty: float,
        order_type: str,
        limit_price: Optional[float] = None,
        fee_schedule = None,
        slippage_model = None,
        orderbook: OrderBookProtocol = None,
        mode: str = "normal",
        hybrid_threshold: float = 0.3,
        hybrid_horizon: int = 5,
        fill_prob_threshold: float = 0.25
    ) -> List[Dict]:
        """Executes a parent order in stealthy slices with optional hybrid upgrades."""
        ...

    def record_fill(
        self,
        order_id: str,
        fill_price: float,
        fill_ts: float,
        fill_qty: Optional[float] = None
    ) -> None:
        """Records fill metrics including latency, slippage, and velocity."""
        ...

    def get_recent_fill_velocity(self, lookback: int = 5) -> float:
        """Returns average fill velocity (qty/sec) over recent slices."""
        ...
