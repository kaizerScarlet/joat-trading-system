import pytest
import random
from market_data.orderbook_protocol import OrderBookProtocol
from Execution_layer.smart_pricing_model_protocol import SmartRepricingModelProtocol
from Execution_layer.smart_pricing_model import SmartRepricingModel

# ------------------ Mock OrderBook ------------------

class MockOrderBook(OrderBookProtocol):
    def __init__(self, bid=None, ask=None):
        self.bid = bid
        self.ask = ask

    def get_best_price(self, side: str):
        return self.bid if side == "bid" else self.ask

# ------------------ Initialization ------------------

def test_default_initialization():
    model : SmartRepricingModelProtocol = SmartRepricingModel()
    assert model.tick_size == 0.01
    assert model.max_jitter_ticks == 2
    assert model.slippage_bps == pytest.approx(5.0, rel=1e-6)

def test_custom_initialization():
    model : SmartRepricingModelProtocol = SmartRepricingModel(tick_size=0.005, max_jitter_ticks=3, slippage_bps=10.0)
    assert model.tick_size == 0.005
    assert model.max_jitter_ticks == 3
    assert model.slippage_bps == pytest.approx(10.0, rel=1e-6)

# ------------------ Fallback Behavior ------------------

def test_fallback_missing_bid():
    model : SmartRepricingModelProtocol = SmartRepricingModel()
    ob = MockOrderBook(bid=None, ask=100.0)
    price = model.optimize_price("BUY", ob)
    assert price == 100.0

def test_fallback_missing_ask():
    model : SmartRepricingModelProtocol = SmartRepricingModel()
    ob = MockOrderBook(bid=99.0, ask=None)
    price = model.optimize_price("SELL", ob)
    assert price == 99.0

def test_fallback_missing_mid():
    model : SmartRepricingModelProtocol = SmartRepricingModel()
    ob = MockOrderBook(bid=None, ask=None)
    price = model.optimize_price("BUY", ob)
    assert price is None

# ------------------ Base Price Logic ------------------

def test_base_price_tight_spread():
    model : SmartRepricingModelProtocol = SmartRepricingModel()
    ob = MockOrderBook(bid=99.99, ask=100.00)  # spread = 0.01, mid = 99.995
    price = model.optimize_price("BUY", ob)
    assert price >= 100.00  # snapped tick

def test_base_price_wide_spread_buy():
    model : SmartRepricingModelProtocol = SmartRepricingModel()
    ob = MockOrderBook(bid=98.0, ask=102.0)  # spread = 4.0, mid = 100.0
    price = model.optimize_price("BUY", ob, fill_prob_target=0.5)
    expected_base = 102.0 - (4.0 * 0.5)  # offset = 2.0 → base = 100.0
    assert abs(price - expected_base) <= 0.05  # allow jitter

def test_base_price_wide_spread_sell():
    model : SmartRepricingModelProtocol = SmartRepricingModel()
    ob = MockOrderBook(bid=98.0, ask=102.0)
    price = model.optimize_price("SELL", ob, fill_prob_target=0.25)
    expected_base = 98.0 + (4.0 * 0.75)  # offset = 3.0 → base = 101.0
    assert abs(price - expected_base) <= 0.05

# ------------------ Jitter and Slippage ------------------

def test_jitter_respects_slippage_cap():
    model : SmartRepricingModelProtocol = SmartRepricingModel(tick_size=0.01, max_jitter_ticks=100, slippage_bps=1.0)
    ob = MockOrderBook(bid=99.0, ask=101.0)  # mid = 100.0 → max_slip = 1.0
    for _ in range(100):
        price = model.optimize_price("BUY", ob)
        assert abs(price - 101.0) <= 1.0  # jitter capped

def test_tick_snapping():
    model : SmartRepricingModelProtocol = SmartRepricingModel(tick_size=0.05)
    ob = MockOrderBook(bid=99.0, ask=101.0)
    price = model.optimize_price("SELL", ob)
    assert (price * 100) % 5 == 0  # snapped to 0.05 tick
