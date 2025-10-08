import pytest
from Execution_layer.queue_position_model_protocol import QueuePositionModelProtocol
from Execution_layer.queue_position_model import QueuePositionModel
from market_data.orderbook import OrderBook
from market_data.orderbook_protocol import OrderBookProtocol

# ------------------ Initialization ------------------

def test_default_initialization():
    model : QueuePositionModelProtocol = QueuePositionModel()
    assert model.base_trade_rate == 1.0

def test_custom_initialization():
    model : QueuePositionModelProtocol = QueuePositionModel(base_trade_rate=2.5)
    assert model.base_trade_rate == 2.5

# ------------------ Fallback Behavior ------------------

def test_zero_tob_qty():
    model : QueuePositionModelProtocol = QueuePositionModel()
    qfrac, prob = model.estimate("BUY", our_qty=1.0, tob_qty=0.0, orderbook=None)
    assert qfrac == 1.0
    assert prob == 0.0

def test_zero_our_qty():
    model : QueuePositionModelProtocol = QueuePositionModel()
    qfrac, prob = model.estimate("SELL", our_qty=0.0, tob_qty=10.0, orderbook=None)
    assert qfrac == 1.0
    assert prob == 0.0

def test_fallback_fill_rate_without_orderbook():
    model : QueuePositionModelProtocol = QueuePositionModel(base_trade_rate=2.0)
    qfrac, prob = model.estimate("BUY", our_qty=5.0, tob_qty=10.0, orderbook=None)
    assert qfrac == pytest.approx(0.5, rel=1e-6)
    assert prob == pytest.approx(1.0, rel=1e-6)  # 0.5 * 2.0

# ------------------ OrderBook Integration ------------------

class MockOrderBook(OrderBookProtocol):
    def get_update_rate(self):
        return 2.0  # updates/sec

    def get_order_imbalance(self):
        return 0.7  # favoring SELL side

    def get_volatility_estimate(self):
        return 0.05  # modest volatility

def test_estimate_with_orderbook_sell_side():
    model : QueuePositionModelProtocol = QueuePositionModel()
    qfrac, prob = model.estimate("SELL", our_qty=5.0, tob_qty=10.0, orderbook=MockOrderBook())
    assert qfrac == pytest.approx(0.5, rel=1e-6)
    # fill_rate = 2.0 * (1 + 5*0.05) * (1 + 0.7) = 2.0 * 1.25 * 1.7 = 4.25
    assert prob == pytest.approx(min(1.0, 0.5 * 4.25), rel=1e-6)

def test_estimate_with_orderbook_buy_side():
    model : QueuePositionModelProtocol = QueuePositionModel()
    qfrac, prob = model.estimate("BUY", our_qty=3.0, tob_qty=6.0, orderbook=MockOrderBook())
    assert qfrac == pytest.approx(0.5, rel=1e-6)
    # side_factor = 1 - 0.7 = 0.3
    # fill_rate = 2.0 * (1 + 5*0.05) * (1 + 0.3) = 2.0 * 1.25 * 1.3 = 3.25
    assert prob == pytest.approx(min(1.0, 0.5 * 3.25), rel=1e-6)

def test_estimate_caps_probability_at_one():
    model : QueuePositionModelProtocol = QueuePositionModel()
    qfrac, prob = model.estimate("SELL", our_qty=100.0, tob_qty=1.0, orderbook=MockOrderBook())
    assert qfrac == pytest.approx(1.0, rel=1e-6)
    assert prob == 1.0  # capped

# ------------------ Edge Cases ------------------

def test_invalid_side_defaults_to_buy_logic():
    model : QueuePositionModelProtocol = QueuePositionModel()
    qfrac, prob = model.estimate("INVALID", our_qty=5.0, tob_qty=10.0, orderbook=MockOrderBook())
    assert qfrac == pytest.approx(0.5, rel=1e-6)
    assert prob == 1.0  # capped at 1.0


def test_extremely_small_tob_qty():
    model : QueuePositionModelProtocol = QueuePositionModel()
    qfrac, prob = model.estimate("BUY", our_qty=1.0, tob_qty=1e-12, orderbook=None)
    assert qfrac == 1.0
    assert prob == pytest.approx(1.0, rel=1e-6)

def test_extremely_large_our_qty():
    model : QueuePositionModelProtocol = QueuePositionModel()
    qfrac, prob = model.estimate("SELL", our_qty=1e6, tob_qty=1.0, orderbook=None)
    assert qfrac == 1.0
    assert prob == pytest.approx(1.0, rel=1e-6)
