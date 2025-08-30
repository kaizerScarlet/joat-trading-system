import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from Execution_layer.execution_coordinator import ExecutionCoordinator
from Execution_layer.execution_coordinator import FeeSchedule


@pytest.fixture
def coordinator():
    c = ExecutionCoordinator()
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
    coordinator.alpha_pipeline.get_alpha_signal.return_value = {"bid": 0.6, "ask": 0.4}
    coordinator.config["min_confidence_to_trade"] = 0.55
    assert coordinator._decide_trade_side() == "BUY"

def test_decide_trade_side_sell(coordinator):
    coordinator.alpha_pipeline.get_alpha_signal.return_value = {"bid": 0.4, "ask": 0.6}
    coordinator.config["min_confidence_to_trade"] = 0.55
    assert coordinator._decide_trade_side() == "SELL"

def test_decide_trade_side_none(coordinator):
    coordinator.alpha_pipeline.get_alpha_signal.return_value = {"bid": 0.4, "ask": 0.4}
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
    otype, price = coordinator._choose_order_type_and_price("BUY")
    assert otype == expected_type

def test_choose_order_type_adaptive_market(coordinator):
    coordinator.config["order_type_preference"] = "adaptive"
    coordinator.orderbook.get_best_price.side_effect = lambda side: 100 if side == "bid" else 100.01
    otype, price = coordinator._choose_order_type_and_price("BUY")
    assert otype == "MARKET"

def test_choose_order_type_adaptive_limit(coordinator):
    coordinator.config["order_type_preference"] = "adaptive"
    coordinator.orderbook.get_best_price.side_effect = lambda side: 100 if side == "bid" else 102
    otype, price = coordinator._choose_order_type_and_price("SELL")
    assert otype == "LIMIT"

def test_execute_order_success(coordinator):
    coordinator.exchange_client.place_order.return_value = "OID123"
    coordinator.sl_and_tp.start_trade.return_value = (1, 2)
    coordinator._execute_order("BUY", 1.0, "MARKET", None, 12345, 1.0, 2.0, "bid")
    coordinator.performance_tracker.record_trade.assert_called_once()

def test_execute_order_fail(coordinator):
    coordinator.exchange_client.place_order.return_value = None
    coordinator._execute_order("BUY", 1.0, "MARKET", None, 12345, 1.0, 2.0, "bid")

@pytest.mark.asyncio
async def test_on_fill_entry_buy(coordinator):
    fill = {"order_id": "1", "side": "BUY", "qty": 1.0, "price": 100, "symbol": "BTC"}
    coordinator.position_size = 0
    coordinator.sl_and_tp.start_trade.return_value = (90, 110)
    coordinator.exchange_client.place_stop_loss_order = AsyncMock(return_value={"orderId": "slid"})
    coordinator.exchange_client.place_take_profit_order = AsyncMock(return_value={"orderId": "tpid"})
    await coordinator._on_fill(fill)
    assert coordinator.position_size == 1.0

@pytest.mark.asyncio
async def test_on_fill_sl_hit(coordinator):
    coordinator.sl_order_id = "SL123"
    coordinator.tp_order_id = "TP123"
    coordinator.exchange_client.cancel_order_by_id = AsyncMock()
    fill = {"order_id": "SL123", "side": "SELL", "qty": 1.0, "price": 90, "symbol": "BTC"}
    await coordinator._on_fill(fill)
    assert coordinator.position_size == 0

@pytest.mark.asyncio
async def test_on_fill_tp_hit(coordinator):
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
    coordinator._choose_order_type_and_price.assert_called_once_with("BUY")
    coordinator._execute_order.assert_called_once()
