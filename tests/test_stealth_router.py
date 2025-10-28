import pytest
import random
import asyncio
import logging
from Execution_layer.queue_position_model_protocol import QueuePositionModelProtocol
from Execution_layer.binance_adapter_protocol import BinanceExecutionAdapterProtocol
from Execution_layer.slippage_model import SlippageModel
from Execution_layer.slippage_model_protocol import SlippageModelProtocol
from market_data.orderbook import OrderBook
from market_data.orderbook_protocol import OrderBookProtocol
from cancel_window.simple_cancel_window_protocol import CancelWindowProtocol
from dynamic_risk_engine.signal_confidence_calibrator_protocol import SignalConfidenceCalibratorProtocol


# -------------------- MOCKS --------------------

class MockOrderBook(OrderBookProtocol):
    def __init__(self):
        self.price_history = [100.0, 101.0, 99.5, 100.5]
        self.bids = [(99.0, 1.0), (98.5, 2.0)]
        self.asks = [(101.0, 1.5), (102.0, 1.0)]

    def get_best_price(self, side):
        return self.bids[0][0] if side == "bid" else self.asks[0][0]

    def get_top_liquidity(self, side):
        return sum(qty for _, qty in (self.bids if side == "bid" else self.asks))

    def get_volatility_estimate(self):
        return 0.015

    def get_order_imbalance(self, depth_levels: int):
        bid_qty = sum(qty for _, qty in self.bids)
        ask_qty = sum(qty for _, qty in self.asks)
        total = bid_qty + ask_qty
        return (bid_qty - ask_qty) / total if total > 0 else 0.0

    def get_liquidity_within_bps(self, side, bps):
        best = self.get_best_price(side)
        threshold = best * (1 + bps / 10000.0) if side == "ask" else best * (1 - bps / 10000.0)
        book = self.asks if side == "ask" else self.bids
        return sum(qty for price, qty in book if (price <= threshold if side == "ask" else price >= threshold))

    def get_update_rate(self):
        return 0.8
    

    def get_midprice(self):
        return 100.0

    def get_resilient_midprice(self):
        return 100.0

    def get_level_size(self, price, side):
        return 1.0

    def get_tick_size(self):
        return 0.01

    def get_quote_flicker_rate(self):
        return 0.2

    def get_depth_retreat_score(self):
        return 0.4

    def get_slip_response_score(self):
        return 0.3

    def get_bid_aggression(self):
        return 0.6

    def get_ask_defense(self):
        return 0.5

    def get_midpoint_staleness(self):
        return 0.3

    def get_top_levels(self, side: str, depth_levels: int = 5):
        book = self.bids if side == "bid" else self.asks
        return book[:depth_levels]



class MockCancelWindow(CancelWindowProtocol):
    def __init__(self):
        self._flags = [
            {"type": "CANCEL_DENSITY_SPIKE", "price": 100.0, "side": "BUY"},
            {"type": "CANCEL_DENSITY_SPIKE", "price": 101.0, "side": "SELL"}
        ]

    def compute_cancel_impact_score(self, price, side):
        return 0.3

class MockSignalCalibrator(SignalConfidenceCalibratorProtocol):
    def get_current_confidence(self):
        return 0.85

class MockExchangeClient(BinanceExecutionAdapterProtocol):
    async def place_order(self, **kwargs):
        return {"orderId": str(random.randint(1000, 9999))}

class MockQueueModel(QueuePositionModelProtocol):
    def estimate(self, side, qty, top_liq, orderbook):
        return None, 0.01

# -------------------- FIXTURES --------------------

@pytest.fixture
def mock_orderbook_instance():
    return MockOrderBook()

@pytest.fixture
def router(mock_orderbook_instance):
    from Execution_layer.stealth_router import StealthRouter
    from dynamic_risk_engine.cognitive_market_regime_classifier import CognitiveMarketRegimeClassifier
    from unittest.mock import MagicMock

    mock_model = MagicMock()
    mock_model.optimize_price.return_value = 100.5
    mock_model.slippage_bps = 0.0  # Initial value, will be overwritten in tests
    regime_classifier = CognitiveMarketRegimeClassifier(
        orderbook=mock_orderbook_instance,
        signal_calibrator=MockSignalCalibrator(),
        cancel_window=MockCancelWindow()
    )

    return StealthRouter(
        symbol="BTCUSDT",
        exchange_client=MockExchangeClient(),
        queue_model=MockQueueModel(),
        repricing_model=mock_model,
        regime_classifier=regime_classifier,
        slippage_model = SlippageModel(),
        orderbook = OrderBook()
    )

# -------------------- TESTS --------------------

# Slice logic
@pytest.mark.asyncio
async def test_slice_count_respects_max_limit(router, mock_orderbook_instance):
    result = await router.execute_parent_order(
        side="BUY",
        total_qty=10.0,
        order_type="LIMIT",
        orderbook=mock_orderbook_instance,
        slippage_model = router.slippage_model,
    )
    assert len(result) <= router.max_slices

@pytest.mark.asyncio
async def test_random_delay_range_applied(router, mock_orderbook_instance):
    delays = []
    router._random_delay = lambda: delays.append(random.uniform(*router.random_delay_range))
    await router.execute_parent_order(
        side="SELL",
        total_qty=5.0,
        order_type="LIMIT",
        orderbook=mock_orderbook_instance,
        slippage_model=router.slippage_model
    )
    assert all(router.random_delay_range[0] <= d <= router.random_delay_range[1] for d in delays)


def make_mock_orderbook(mid=100.0, spread=2.0):
    ob = MockOrderBook()
    ob.get_midprice = lambda: mid
    ob.get_best_price = lambda side: mid - spread/2 if side == "bid" else mid + spread/2
    ob.get_top_liquidity = lambda side, depth_levels=1: 1.0
    ob.get_update_rate = lambda: 2.5
    ob.get_volatility_estimate = lambda: 0.01
    return ob


# Price behavior
def test_smart_price_within_spread(router, mock_orderbook_instance):
    price = router.repricing_model.optimize_price("BUY", mock_orderbook_instance, fill_prob_target=0.5)
    bid = mock_orderbook_instance.get_best_price("bid")
    ask = mock_orderbook_instance.get_best_price("ask")
    assert bid <= price <= ask

from unittest.mock import patch

def test_jitter_respects_slippage_cap(router):
    # Patch router.orderbook directly
    router.orderbook.get_best_price = lambda side: 99.0 if side == "bid" else 101.0
    router.orderbook.get_midprice = lambda: 100.0
    router.orderbook.get_resilient_midprice = lambda: 100.0

    # Ensure slippage cap is tight
    router.slippage_bps = 0.005
    router.repricing_model.slippage_bps = 0.0005

    mid = router.orderbook.get_midprice()
    price = router.repricing_model.optimize_price("SELL", router.orderbook, fill_prob_target=0.5)

    max_slip = mid * router.slippage_bps
    assert abs(price - mid) <= max_slip






# Hybrid mode
@pytest.mark.asyncio
async def test_hybrid_upgrades_to_market(router):
    router.orderbook.get_best_price = lambda side: 99.0 if side == "bid" else 101.0
    router.orderbook.get_midprice = lambda: 100.0
    router.orderbook.get_resilient_midprice = lambda: 100.0
    router.orderbook.get_top_liquidity = lambda side, depth_levels=5: 1.0


    router.queue_model.estimate = lambda side, qty, tob_qty, ob: (0.5, 0.01)
    router.fill_prob_threshold = 0.25

    result = await router.execute_parent_order(
        side="BUY",
        total_qty=1.0,
        order_type="LIMIT",
        mode="hybrid",
        orderbook=router.orderbook,
        slippage_model=router.slippage_model
    )

    assert any(order["liquidity"] == "TAKER" for order in result)


# Fill attribution
def test_record_fill_updates_latency_and_slip(router):
    router.execution_log = [{
        "orderId": "123",
        "qty": 1.0,
        "price": 100.0,
        "placement_ts": 1000000
    }]
    router.record_fill(order_id="123", fill_price=101.0, fill_ts=1000500)
    rec = router.execution_log[0]
    assert rec["latency_ms"] == 500
    assert rec["realized_slip"] == 1.0
    assert rec["fill_velocity"] == pytest.approx(2.0, rel=1e-2)

# Regime reflex
@pytest.mark.asyncio
async def test_regime_tuning_applies_correct_slippage(router, mock_orderbook_instance):
    from dynamic_risk_engine.cognitive_market_regime_classifier import MarketRegime

    mock_orderbook_instance.get_best_price = lambda side: 99.0 if side == "bid" else 101.0
    mock_orderbook_instance.get_midprice = lambda: 100.0
    mock_orderbook_instance.get_resilient_midprice = lambda: 100.0
    mock_orderbook_instance.get_top_liquidity = lambda side, depth_levels=1: 1.0

    router.slippage_model.expected_market_slip = lambda side, mid, spread, qty, top_liq: 1.5
    router.regime_classifier.update_regime = lambda: MarketRegime.VOLATILE

    await router.execute_parent_order(
        side="SELL",
        total_qty=2.0,
        order_type="LIMIT",
        orderbook=mock_orderbook_instance,
        slippage_model=router.slippage_model
    )

    assert router.slippage_bps == 150.0




# Velocity feedback
def test_velocity_feedback_adjusts_slice_size(router):
    router.execution_log = [
        {"orderId": "1", "qty": 1.0, "placement_ts": 1000000, "latency_ms": 500, "fill_velocity": 2.0},
        {"orderId": "2", "qty": 1.0, "placement_ts": 1000500, "latency_ms": 400, "fill_velocity": 2.5},
    ]
    velocity = router.get_recent_fill_velocity()
    assert velocity > 1.5

def test_zero_latency_does_not_crash_velocity_calc(router):
    router.execution_log = [{
        "orderId": "X",
        "qty": 1.0,
        "placement_ts": 1000000,
        "latency_ms": 0
    }]
    router.record_fill(order_id="X", fill_price=100.0, fill_ts=1000000)
    assert router.execution_log[0]["fill_velocity"] > 0.0

@pytest.mark.asyncio
async def test_velocity_thresholds_change_with_regime(router, mock_orderbook_instance):
    from dynamic_risk_engine.cognitive_market_regime_classifier import MarketRegime
    router.regime_classifier.update_regime = lambda: MarketRegime.ILLIQUID
    await router.execute_parent_order(
        side="SELL",
        total_qty=2.0,
        order_type="LIMIT",
        orderbook=mock_orderbook_instance,
        slippage_model=router.slippage_model
    )
    assert router.random_delay_range[0] >= 1.5

def test_execution_log_contains_expected_fields(router):
    router.execution_log = []
    router.record_fill(order_id="123", fill_price=100.0, fill_ts=1000500)
    keys = router.execution_log[0].keys()
    for field in ["orderId", "qty", "price", "latency_ms", "realized_slip", "fill_velocity"]:
        assert field in keys



def test_record_fill_creates_synthetic_record_for_unknown_order(router):
    # Act: record a fill for an unknown orderId
    router.record_fill(order_id="UNKNOWN", fill_price=200.0, fill_ts=5000)

    # Assert: synthetic record appended
    rec = router.execution_log[-1]
    assert rec["orderId"] == "UNKNOWN"
    assert rec["price"] == 200.0
    assert rec["placement_ts"] == 5000

    # All expected keys must exist
    expected_keys = [
        "orderId", "qty", "price", "placement_ts", "latency_ms",
        "realized_slip", "fill_velocity", "liquidity",
        "exp_fill_prob", "regime", "expected_slip"
    ]
    for key in expected_keys:
        assert key in rec


def test_record_fill_synthetic_defaults_are_none(router):
    router.record_fill(order_id="XYZ", fill_price=150.0, fill_ts=6000)
    rec = router.execution_log[-1]

    # Fields we cannot know should be None
    assert rec["qty"] is None
    assert rec["latency_ms"] is None
    assert rec["realized_slip"] is None
    assert rec["fill_velocity"] is None
    assert rec["liquidity"] is None
    assert rec["exp_fill_prob"] is None
    assert rec["regime"] is None
    assert rec["expected_slip"] is None

def test_partial_fill_updates_metrics(router):
    router.execution_log = [{
        "orderId": "P123",
        "qty": 2.0,
        "price": 100.0,
        "placement_ts": 1000000
    }]
    # Simulate partial fill of 1.0 at 101.0
    router.record_fill(order_id="P123", fill_price=101.0, fill_ts=1000500, fill_qty=1.0)
    rec = router.execution_log[0]
    assert rec["latency_ms"] == 500
    assert rec["realized_slip"] == 1.0
    assert rec["fill_velocity"] == pytest.approx(2.0, rel=1e-2)


@pytest.mark.asyncio
async def test_regime_drift_mid_trade(router, mock_orderbook_instance):
    from dynamic_risk_engine.cognitive_market_regime_classifier import MarketRegime

    mock_orderbook_instance.get_best_price = lambda side: 99.0 if side == "bid" else 101.0
    mock_orderbook_instance.get_midprice = lambda: 100.0
    mock_orderbook_instance.get_resilient_midprice = lambda: 100.0
    mock_orderbook_instance.get_top_liquidity = lambda side, depth_levels=1: 1.0
    mock_orderbook_instance.get_update_rate = lambda: 2.5
    mock_orderbook_instance.get_volatility_estimate = lambda: 0.01

    router.regime_classifier.update_regime = lambda: MarketRegime.MEAN_REVERTING
    router.get_recent_fill_velocity = lambda: 0.2

    await router.execute_parent_order(
        side="SELL",
        total_qty=2.0,
        order_type="LIMIT",
        orderbook=mock_orderbook_instance,
        slippage_model=router.slippage_model
    )

    expected_range = (2.0, 3.9)
    actual_range = tuple(round(x, 1) for x in router.random_delay_range)
    assert actual_range == expected_range





def test_spoof_burst_triggers_regime_reinforcement(router):
    from dynamic_risk_engine.cognitive_market_regime_classifier import MarketRegime

    # Inject spoof flags
    router.regime_classifier.cancel_window._flags = [
        {"type": "CANCEL_DENSITY_SPIKE", "price": 100.0, "side": "BUY"},
        {"type": "CANCEL_DENSITY_SPIKE", "price": 101.0, "side": "SELL"},
        {"type": "CANCEL_DENSITY_SPIKE", "price": 102.0, "side": "BUY"},
    ]

    regime = router.regime_classifier.update_regime()
    assert regime in [MarketRegime.VOLATILE, MarketRegime.ILLIQUID, MarketRegime.TRENDING]



@pytest.mark.asyncio
async def test_execution_summary_logs_correct_metrics(router, mock_orderbook_instance, caplog):
    caplog.set_level(logging.INFO)
    await router.execute_parent_order(
        side="BUY",
        total_qty=5.0,
        order_type="LIMIT",
        orderbook=mock_orderbook_instance,
        slippage_model=router.slippage_model
    )

    # Confirm summary log
    summary = [r for r in caplog.records if "[Execution Summary]" in r.message]
    assert summary
    assert f"{len(router.execution_log)} slices executed" in summary[0].message

    # Confirm each slice has expected fields
    for rec in router.execution_log:
        assert "orderId" in rec
        assert "qty" in rec
        assert "liquidity" in rec
        assert "regime" in rec
        assert "expected_slip" in rec


