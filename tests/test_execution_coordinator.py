import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from Execution_layer.execution_coordinator import ExecutionCoordinator
from Execution_layer.execution_coordinator_protocol import ExecutionCoordinatorProtocol
from Execution_layer.queue_position_model_protocol import QueuePositionModelProtocol
from alpha_scoring.alpha_pipeline_protocol import AlphaSignalPipelineProtocol
from cancel_window.simple_cancel_window_protocol import CancelWindowProtocol
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

from cancel_window.order_spoofing_detection import OrderSpoofingDetection
from cancel_window.synthetic_fill_detector import SyntheticFillDetection
from cancel_window.order_laddering_detection import OrderLadderingDetection
from cancel_window.order_iceberg_detection import OrderIcebergDetection
from cancel_window.cancel_density_detection import CancelDensityDetection



@pytest.fixture
def coordinator():
    c : ExecutionCoordinatorProtocol = ExecutionCoordinator(
            cancel_density_scorer = MagicMock(spec=CancelDensityDetection),
            synthetic_fill_scorer = MagicMock(spec=SyntheticFillDetection),
            iceberg_scorer = MagicMock(spec=OrderIcebergDetection),
            laddering_scorer = MagicMock(spec=OrderLadderingDetection),
            cancel_spoofing_scorer = MagicMock(spec=OrderSpoofingDetection),
            alpha_pipeline = AlphaSignalPipelineProtocol,
            slippage_model = SlippageModelProtocol,
            latency_model = LatencyModelProtocol,
            fee_schedule = FeeScheduleProtocol,
            throttle_manager = ThrottleCooldownManagerProtocol,
            exchange_client = BinanceExecutionAdapterProtocol,
            stealth_router = StealthRouterProtocol,
            performance_tracker = PerformanceTrackerProtocol,
            signal_confidence = SignalConfidenceCalibratorProtocol,
            dynamic_position_sizer = DynamicPositionSizerProtocol,
            cancel_window = CancelWindowProtocol,
            order_book = OrderBookProtocol,
            cancel_activity_scorer = CancelActivityScorerProtocol,
            layering_scorer = LayeringScoringProtocol,
            order_age_scorer = OrderAgeDistributionScorerProtocol,
            queue_position_model = QueuePositionModelProtocol,
            risk_engine = DynamicRiskEngineProtocol,
            drawdown_manager = DailyDrawdownManagerProtocol,
            regime_classifier = MagicMock(spec=CognitiveMarketRegimeClassifierProtocol),
            sl_and_tp = AdaptiveSLTPProtocol,
    )
    # Mock dependencies

    c.alpha_pipeline = MagicMock()
    c.risk_engine = MagicMock()
    c.throttle_manager = MagicMock()
    c.confidence = MagicMock()
    c.dynamic_position_sizer = MagicMock()
    c.performance_tracker = MagicMock()
    c.exchange_client = MagicMock()
    c.orderbook = MagicMock()
    c.sl_and_tp = MagicMock()
    return c

@pytest.mark.asyncio
async def test_reconcile_open_orders_success(coordinator):
    coordinator.exchange_client.get_open_orders = AsyncMock(return_value=[{"id": 1}])
    await coordinator.reconcile_open_orders()
    coordinator.exchange_client.get_open_orders.assert_awaited_once()

@pytest.mark.asyncio
async def test_reconcile_open_orders_exception(coordinator):
    coordinator.exchange_client.get_open_orders = AsyncMock(side_effect=Exception("fail"))
    await coordinator.reconcile_open_orders()  # Should not raise

def test_now_ms_no_offset(coordinator):
    t1 = coordinator.now_ms()
    assert isinstance(t1, int)

def test_now_ms_with_offset(coordinator):
    coordinator.time_offset_ms = 500
    t1 = coordinator.now_ms()
    assert isinstance(t1, int)

def test_decide_trade_side_buy(coordinator):
    coordinator.iceberg_detector.get_iceberg_score = MagicMock(return_value=0.7)
    coordinator.alpha_pipeline.get_alpha_signal.return_value = {"bid": 0.6, "ask": 0.4}
    coordinator.config["min_confidence_to_trade"] = 0.55

    coordinator.cancel_spoof_scorer.get_spoofing_score = MagicMock(return_value={"bid": 0.1, "ask": 0.1})
    coordinator.layering_scorer.compute_score = MagicMock(return_value={"bid": 0.6, "ask": 0.4})
    coordinator.order_age_scorer.compute_score = MagicMock(return_value={"bid": 0.5, "ask": 0.5})
    coordinator.iceberg_detector.get_iceberg_score = MagicMock(return_value=0.7)
    coordinator.synthetic_fill_detector.get_anomaly_score = MagicMock(return_value={"bid": 0.7, "ask": 0.5})
    coordinator.cancel_density_detector.get_density_score = MagicMock(return_value={"bid": 0.2, "ask": 0.2})
    coordinator.order_ladder_tracker.get_laddering_score = MagicMock(return_value={"type": None})
    coordinator.regime_classifier.get_current_regime = MagicMock(return_value="TRENDING")

    assert coordinator._decide_trade_side() == "BUY"

def test_decide_trade_side_sell(coordinator):
    coordinator.alpha_pipeline.get_alpha_signal.return_value = {"bid": 0.4, "ask": 0.6}
    coordinator.config["min_confidence_to_trade"] = 0.55

    coordinator.cancel_spoof_scorer.get_spoofing_score = MagicMock(return_value={"bid": 0.1, "ask": 0.1})
    coordinator.layering_scorer.compute_score = MagicMock(return_value={"bid": 0.4, "ask": 0.6})
    coordinator.order_age_scorer.compute_score = MagicMock(return_value={"bid": 0.5, "ask": 0.5})
    coordinator.iceberg_detector.get_iceberg_score = MagicMock(return_value=0.7)  # ✅ This is the fix
    coordinator.synthetic_fill_detector.get_anomaly_score = MagicMock(return_value={"bid": 0.5, "ask": 0.7})
    coordinator.cancel_density_detector.get_density_score = MagicMock(return_value={"bid": 0.2, "ask": 0.2})
    coordinator.order_ladder_tracker.get_laddering_score = MagicMock(return_value={"type": None})
    coordinator.regime_classifier.get_current_regime = MagicMock(return_value="TRENDING")

    assert coordinator._decide_trade_side() == "SELL"

def test_trade_side_fades_bid_due_to_spoofing(coordinator):
    coordinator.alpha_pipeline.get_alpha_signal.return_value = {"bid": 0.7, "ask": 0.4}
    coordinator.config["min_confidence_to_trade"] = 0.55

    coordinator.cancel_spoof_scorer.get_spoofing_score = MagicMock(return_value={"bid": 0.9, "ask": 0.1})
    coordinator.layering_scorer.compute_score = MagicMock(return_value={"bid": 0.6, "ask": 0.4})
    coordinator.order_age_scorer.compute_score = MagicMock(return_value={"bid": 0.5, "ask": 0.5})
    coordinator.iceberg_detector.get_iceberg_score = MagicMock(return_value=0.5)
    coordinator.synthetic_fill_detector.get_anomaly_score = MagicMock(return_value={"bid": 0.7, "ask": 0.5})
    coordinator.cancel_density_detector.get_density_score = MagicMock(return_value={"bid": 0.2, "ask": 0.2})
    coordinator.order_ladder_tracker.get_laddering_score = MagicMock(return_value={"type": None})
    coordinator.regime_classifier.get_current_regime = MagicMock(return_value="MEAN_REVERTING")

    assert coordinator._decide_trade_side() is None

def test_trade_side_sell_due_to_iceberg_and_fill_conf(coordinator):
    coordinator.alpha_pipeline.get_alpha_signal.return_value = {"bid": 0.4, "ask": 0.7}
    coordinator.config["min_confidence_to_trade"] = 0.55

    coordinator.cancel_spoof_scorer.get_spoofing_score = MagicMock(return_value={"bid": 0.1, "ask": 0.1})
    coordinator.layering_scorer.compute_score = MagicMock(return_value={"bid": 0.4, "ask": 0.6})
    coordinator.order_age_scorer.compute_score = MagicMock(return_value={"bid": 0.5, "ask": 0.5})
    coordinator.iceberg_detector.get_iceberg_score = MagicMock(return_value=-0.7)  # ask bias
    coordinator.synthetic_fill_detector.get_anomaly_score = MagicMock(return_value={"bid": 0.5, "ask": 0.7})
    coordinator.cancel_density_detector.get_density_score = MagicMock(return_value={"bid": 0.2, "ask": 0.2})
    coordinator.order_ladder_tracker.get_laddering_score = MagicMock(return_value={"type": None})
    coordinator.regime_classifier.get_current_regime = MagicMock(return_value="TRENDING")

    assert coordinator._decide_trade_side() == "SELL"

def test_trade_side_buy_in_illiquid_regime(coordinator):
    coordinator.alpha_pipeline.get_alpha_signal.return_value = {"bid": 0.65, "ask": 0.4}
    coordinator.config["min_confidence_to_trade"] = 0.55

    coordinator.cancel_spoof_scorer.get_spoofing_score = MagicMock(return_value={"bid": 0.2, "ask": 0.2})
    coordinator.layering_scorer.compute_score = MagicMock(return_value={"bid": 0.5, "ask": 0.3})
    coordinator.order_age_scorer.compute_score = MagicMock(return_value={"bid": 0.5, "ask": 0.5})
    coordinator.iceberg_detector.get_iceberg_score = MagicMock(return_value=0.3)
    coordinator.synthetic_fill_detector.get_anomaly_score = MagicMock(return_value={"bid": 0.6, "ask": 0.4})
    coordinator.cancel_density_detector.get_density_score = MagicMock(return_value={"bid": 0.3, "ask": 0.3})
    coordinator.order_ladder_tracker.get_laddering_score = MagicMock(return_value={"type": None})
    coordinator.regime_classifier.get_current_regime = MagicMock(return_value="ILLIQUID")

    assert coordinator._decide_trade_side() == "BUY"

def test_trade_side_sell_in_volatile_regime(coordinator):
    coordinator.alpha_pipeline.get_alpha_signal.return_value = {"bid": 0.5, "ask": 0.65}
    coordinator.config["min_confidence_to_trade"] = 0.55

    coordinator.cancel_spoof_scorer.get_spoofing_score = MagicMock(return_value={"bid": 0.3, "ask": 0.3})
    coordinator.layering_scorer.compute_score = MagicMock(return_value={"bid": 0.2, "ask": 0.4})
    coordinator.order_age_scorer.compute_score = MagicMock(return_value={"bid": 0.5, "ask": 0.5})
    coordinator.iceberg_detector.get_iceberg_score = MagicMock(return_value=0.2)
    coordinator.synthetic_fill_detector.get_anomaly_score = MagicMock(return_value={"bid": 0.4, "ask": 0.6})
    coordinator.cancel_density_detector.get_density_score = MagicMock(return_value={"bid": 0.3, "ask": 0.3})
    coordinator.order_ladder_tracker.get_laddering_score = MagicMock(return_value={"type": None})
    coordinator.regime_classifier.get_current_regime = MagicMock(return_value="VOLATILE")

    assert coordinator._decide_trade_side() == "SELL"

def test_trade_side_buy_due_to_ladder_fill(coordinator):
    coordinator.alpha_pipeline.get_alpha_signal.return_value = {"bid": 0.3, "ask": 0.3}
    coordinator.config["min_confidence_to_trade"] = 0.55

    coordinator.cancel_spoof_scorer.get_spoofing_score = MagicMock(return_value={"bid": 0.5, "ask": 0.5})
    coordinator.layering_scorer.compute_score = MagicMock(return_value={"bid": 0.2, "ask": 0.2})
    coordinator.order_age_scorer.compute_score = MagicMock(return_value={"bid": 0.0, "ask": 0.0})
    coordinator.iceberg_detector.get_iceberg_score = MagicMock(return_value=0.0)
    coordinator.synthetic_fill_detector.get_anomaly_score = MagicMock(return_value={"bid": 0.3, "ask": 0.3})
    coordinator.cancel_density_detector.get_density_score = MagicMock(return_value={"bid": 0.5, "ask": 0.5})
    coordinator.order_ladder_tracker.get_laddering_score = MagicMock(return_value={"type": "LADDER_FILL", "side": "bid", "filled": True})
    coordinator.regime_classifier.get_current_regime = MagicMock(return_value="TRENDING")

    assert coordinator._decide_trade_side() == "BUY"

def test_generate_decision_context_basic(coordinator):
    coordinator.alpha_pipeline.get_alpha_signal.return_value = {"bid": 0.6, "ask": 0.4}
    coordinator.regime_classifier.get_current_regime.return_value = "TRENDING"
    coordinator.regime_classifier.get_behavioral_overlay.return_value = "NORMAL"
    coordinator.cancel_spoof_scorer.get_spoofing_score.return_value = {"bid": 0.1, "ask": 0.1}
    coordinator.layering_scorer.compute_score.return_value = {"bid": 0.6, "ask": 0.4}
    coordinator.iceberg_detector.get_iceberg_score.return_value = 0.7
    coordinator.synthetic_fill_detector.get_anomaly_score.return_value = {"bid": 0.7, "ask": 0.5}
    coordinator.cancel_density_detector.get_density_score.return_value = {"bid": 0.2, "ask": 0.2}
    coordinator.order_ladder_tracker.get_laddering_score.return_value = {"type": None}
    coordinator.order_age_scorer.compute_score.return_value = {"bid": 0.5, "ask": 0.5}

    context = coordinator.generate_decision_context()

    assert context["alpha_signal"]["selected_side"] == "bid"
    assert context["regime"]["type"] == "TRENDING"
    assert context["modulation_factors"]["iceberg_bias"] == "bid"
    assert context["final_decision"] == "BUY"


def test_decide_trade_side_none(coordinator):
    coordinator.alpha_pipeline.get_alpha_signal.return_value = {"bid": 0.4, "ask": 0.4}
    coordinator.iceberg_detector.get_iceberg_score = MagicMock(return_value=0.0)

    coordinator.config["min_confidence_to_trade"] = 0.55
    assert coordinator._decide_trade_side() is None

def test_check_pre_trade_conditions_all_pass(coordinator):
    coordinator.confidence.get_current_confidence.return_value = 0.6
    coordinator.throttle_manager.is_throttled.return_value = False
    coordinator.risk_engine.can_trade.return_value = True
    assert coordinator._check_pre_trade_conditions() is True

def test_check_pre_trade_conditions_low_confidence(coordinator):
    coordinator.confidence.get_current_confidence.return_value = 0.5
    assert coordinator._check_pre_trade_conditions() is False

def test_compute_order_size_midprice_zero(coordinator):
    coordinator.orderbook.get_midprice.return_value = 0.0
    assert coordinator._compute_order_size(10) == 0.0

def test_compute_order_size_normal(coordinator):
    coordinator.orderbook.get_midprice.return_value = 100
    coordinator.dynamic_position_sizer.calculate_position_size.return_value = 1.5
    assert coordinator._compute_order_size(10) == 1.5

@pytest.mark.parametrize("pref,expected_type", [
    ("market", "MARKET"),
    ("limit", "LIMIT"),
])
def test_choose_order_type_fixed(coordinator, pref, expected_type):
    coordinator.config["order_type_preference"] = pref
    coordinator.orderbook.get_best_price.side_effect = lambda side: 100 if side == "bid" else 102
    otype, price = coordinator._choose_order_type_and_price("BUY", 1.0)
    assert otype == expected_type

def test_choose_order_type_adaptive_market(coordinator):
    coordinator.config["order_type_preference"] = "adaptive"
    coordinator.config["min_fill_prob_for_limit"] = 0.05
    coordinator.config["queue_horizon_sec"] = 10


    coordinator.fees = MagicMock()
    coordinator.fees.taker_rate.return_value = 0.001  # 10 bps
    coordinator.fees.maker_rate.return_value = 0.0008  # 8 bps

    coordinator.orderbook.get_best_price.side_effect = lambda side: 100 if side == "bid" else 100.05
    coordinator.orderbook.get_top_liquidity = MagicMock(return_value=0.5)

    coordinator.slippage_model = MagicMock()
    coordinator.slippage_model.expected_market_slip = MagicMock(return_value=0.01)

    # Override queue model to force low fill probability
    coordinator.queue_model.estimate = lambda *args, **kwargs: (0.5, 0.001)

    # Optional: mock orderbook dynamics if needed
    coordinator.orderbook.get_update_rate = MagicMock(return_value=0.1)
    coordinator.orderbook.get_order_imbalance = MagicMock(return_value=0.5)
    coordinator.orderbook.get_volatility_estimate = MagicMock(return_value=0.01)

    otype, price = coordinator._choose_order_type_and_price("BUY", 1.0)
    assert otype == "MARKET"





@pytest.mark.asyncio
async def test_execute_order_success(coordinator):
    coordinator.exchange_client.place_order.return_value = "OID123"
    coordinator.sl_and_tp.start_trade.return_value = (1, 2)

    coordinator._execute_order("BUY", 1.0, "MARKET", None, 12345, 1.0, 2.0, "bid")
    await asyncio.sleep(0.1)  # allow background task to complete



@pytest.mark.asyncio
async def test_execute_order_fail(coordinator):
    coordinator.exchange_client.place_order.return_value = None
    coordinator._execute_order("BUY", 1.0, "MARKET", None, 12345, 1.0, 2.0, "bid")
    await asyncio.sleep(0.1)  # allow background task to complete

@pytest.mark.asyncio
async def test_on_fill_entry_buy(coordinator):
    fill = {"order_id": "1", "side": "BUY", "qty": 1.0, "price": 100, "symbol": "BTC"}
    coordinator.position_size = 0
    coordinator.sl_and_tp.start_trade.return_value = (90, 110)
    coordinator.fees = MagicMock()
    coordinator.fees.taker_rate.return_value = 0.001  # 10 bps
    coordinator.fees.maker_rate.return_value = 0.0008  # 8 bps

    coordinator.exchange_client.place_stop_loss_order = AsyncMock(return_value={"orderId": "slid"})
    coordinator.exchange_client.place_take_profit_order = AsyncMock(return_value={"orderId": "tpid"})
    await coordinator._on_fill(fill)
    assert coordinator.position_size == 1.0

@pytest.mark.asyncio
async def test_on_fill_sl_hit(coordinator):
    coordinator.fees = MagicMock()
    coordinator.fees.taker_rate.return_value = 0.001  # 10 bps
    coordinator.fees.maker_rate.return_value = 0.0008  # 8 bps


    coordinator.sl_order_id = "SL123"
    coordinator.tp_order_id = "TP123"
    coordinator.exchange_client.cancel_order_by_id = AsyncMock()
    fill = {"order_id": "SL123", "side": "SELL", "qty": 1.0, "price": 90, "symbol": "BTC"}
    await coordinator._on_fill(fill)
    assert coordinator.position_size == 0

@pytest.mark.asyncio
async def test_on_fill_tp_hit(coordinator):
    coordinator.fees = MagicMock()
    coordinator.fees.taker_rate.return_value = 0.001  # 10 bps
    coordinator.fees.maker_rate.return_value = 0.0008  # 8 bps


    coordinator.tp_order_id = "TP123"
    coordinator.sl_order_id = "SL123"
    coordinator.exchange_client.cancel_order_by_id = AsyncMock()
    fill = {"order_id": "TP123", "side": "SELL", "qty": 1.0, "price": 110, "symbol": "BTC"}
    await coordinator._on_fill(fill)
    assert coordinator.position_size == 0

def test_monitor_open_positions_modifies(coordinator):
    coordinator.exchange_client.get_open_positions.return_value = [{"id": 1, "side": "BUY", "stop_loss": 80, "take_profit": 120}]
    coordinator.sl_and_tp.get_sl_tp.return_value = (90, 130)
    coordinator.exchange_client.modify_order_sl_tp = MagicMock()
    coordinator.monitor_open_positions()
    coordinator.exchange_client.modify_order_sl_tp.assert_called_once()

def test_monitor_open_positions_no_change(coordinator):
    coordinator.exchange_client.get_open_positions.return_value = [{"id": 1, "side": "BUY", "stop_loss": 90, "take_profit": 130}]
    coordinator.sl_and_tp.get_sl_tp.return_value = (90, 130)
    coordinator.exchange_client.modify_order_sl_tp = MagicMock()
    coordinator.monitor_open_positions()
    coordinator.exchange_client.modify_order_sl_tp.assert_not_called()

def test_reset_position_state(coordinator):
    coordinator.position_size = 1.0
    coordinator.entry_price = 100
    coordinator.sl_order_id = "sl"
    coordinator.tp_order_id = "tp"
    coordinator._reset_position_state()
    assert coordinator.position_size == 0.0
    assert coordinator.sl_order_id is None


@pytest.mark.asyncio
async def test_on_new_alpha_no_trade_side(coordinator):
    # Setup _decide_trade_side to return None (no trade)
    coordinator._decide_trade_side = MagicMock(return_value=None)
    coordinator._check_pre_trade_conditions = MagicMock()
    coordinator._compute_order_size = MagicMock()
    coordinator._choose_order_type_and_price = MagicMock()
    coordinator._execute_order = MagicMock()

    # Call method
    coordinator.on_new_alpha({"bid": 0.3, "ask": 0.3}, {})

    # Assert no further methods called
    coordinator._check_pre_trade_conditions.assert_not_called()
    coordinator._compute_order_size.assert_not_called()
    coordinator._execute_order.assert_not_called()

@pytest.mark.asyncio
async def test_on_new_alpha_failing_pre_trade_conditions(coordinator):
    coordinator._decide_trade_side = MagicMock(return_value="BUY")
    coordinator._check_pre_trade_conditions = MagicMock(return_value=False)
    coordinator._compute_order_size = MagicMock()
    coordinator._choose_order_type_and_price = MagicMock()
    coordinator._execute_order = MagicMock()

    coordinator.on_new_alpha({"bid": 0.7, "ask": 0.2}, {})

    coordinator._check_pre_trade_conditions.assert_called_once()
    coordinator._compute_order_size.assert_not_called()
    coordinator._choose_order_type_and_price.assert_not_called()
    coordinator._execute_order.assert_not_called()

@pytest.mark.asyncio
async def test_on_new_alpha_order_size_zero(coordinator):
    coordinator._decide_trade_side = MagicMock(return_value="BUY")
    coordinator._check_pre_trade_conditions = MagicMock(return_value=True)
    coordinator.sl_and_tp.start_trade = MagicMock(return_value=(100, 120))
    coordinator.orderbook.get_midprice = MagicMock(return_value=110)
    coordinator._compute_order_size = MagicMock(return_value=0.0)
    coordinator._choose_order_type_and_price = MagicMock()
    coordinator._execute_order = MagicMock()

    coordinator.on_new_alpha({"bid": 0.7, "ask": 0.2}, {})

    coordinator._compute_order_size.assert_called_once()
    coordinator._choose_order_type_and_price.assert_not_called()
    coordinator._execute_order.assert_not_called()

@pytest.mark.asyncio
async def test_on_new_alpha_successful_flow(coordinator):
    coordinator._decide_trade_side = MagicMock(return_value="BUY")
    coordinator._check_pre_trade_conditions = MagicMock(return_value=True)
    coordinator.sl_and_tp.start_trade = MagicMock(return_value=(90, 110))
    coordinator.orderbook.get_midprice = MagicMock(return_value=100)
    coordinator._compute_order_size = MagicMock(return_value=1.0)
    coordinator._choose_order_type_and_price = MagicMock(return_value=("MARKET", None))
    coordinator._execute_order = MagicMock()

    coordinator.on_new_alpha({"bid": 0.7, "ask": 0.2}, {})

    coordinator._compute_order_size.assert_called_once()
    coordinator._choose_order_type_and_price.assert_called_once_with("BUY", 1.0)
    coordinator._execute_order.assert_called_once()


def test_emergency_mode_triggers_aggressive_sl(coordinator):
    coordinator.sl_and_tp._emergency_mode = True
    coordinator.sl_and_tp.monitor_and_adjust = MagicMock()
    coordinator.sl_and_tp.monitor_and_adjust()
    coordinator.sl_and_tp.monitor_and_adjust.assert_called_once()


def test_sl_tp_drift_logging(coordinator):
    coordinator.sl_and_tp.get_sl_tp.return_value = (95, 105)
    coordinator.sl_and_tp.debug_state.return_value = {"composite_score": 0.6}
    coordinator.performance_tracker.record_sl_tp_drift = MagicMock()
    coordinator.monitor_open_positions = MagicMock()

    coordinator.on_market_tick(high=100, low=90, close=95)
    coordinator.performance_tracker.record_sl_tp_drift.assert_called_once_with(95, 105)

import pytest
from unittest.mock import MagicMock
from datetime import datetime

def test_drawdown_triggers_emergency_mode(coordinator, caplog):
    # Fix datetime.now() usage
    coordinator.drawdown_manager.calculate_daily_drawdown = MagicMock(return_value=-1000)
    coordinator.drawdown_manager.get_daily_drawdown_limit = MagicMock(return_value=-500)

    # Fix composite score comparison
    coordinator.get_composite_score = MagicMock(return_value=0.5)

    # Fix SL/TP unpacking
    coordinator.sl_and_tp.get_sl_tp = MagicMock(return_value=(90, 110))
    coordinator.sl_and_tp.monitor_and_adjust = MagicMock()
    coordinator.sl_and_tp.start_trade = MagicMock()

    # Fix exchange client call
    coordinator.exchange_client.get_open_positions = MagicMock(return_value=[
        {"symbol": "XYZ", "qty": 1.0, "side": "BUY"}
    ])

    # Ensure config has symbol
    coordinator.config["symbol"] = "XYZ"

    with caplog.at_level("ERROR"):
        coordinator.on_market_tick()

    # ✅ Assertions
    assert "Drawdown override logic failed" not in caplog.text
    assert "Emergency SL tigthen logic failed" not in caplog.text
    assert "failed to log AdaptiveSLTP debug state" not in caplog.text

    coordinator.drawdown_manager.calculate_daily_drawdown.assert_called_once()
    coordinator.drawdown_manager.get_daily_drawdown_limit.assert_called_once()
    assert coordinator.sl_and_tp.monitor_and_adjust.call_count >= 2
    assert coordinator.sl_and_tp.get_sl_tp.call_count >= 2
    coordinator.exchange_client.get_open_positions.assert_called_once()
    assert coordinator.sl_and_tp._emergency_mode is True
