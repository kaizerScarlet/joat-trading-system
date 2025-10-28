import pytest
import random
from market_data.orderbook_protocol import OrderBookProtocol
from Execution_layer.slippage_model_protocol import SlippageModelProtocol
from Execution_layer.smart_pricing_model_protocol import SmartRepricingModelProtocol
from Execution_layer.smart_pricing_model import SmartRepricingModel


class MockSlippageModel(SlippageModelProtocol):
    def __init__(self, market_slip=0.01, limit_price=100.0):
        self.market_slip = market_slip
        self.limit_price = limit_price
        self.last_market_args = None
        self.last_limit_args = None

    def expected_market_slip(self, side: str, mid: float, spread: float, qty: float, top_liquidity: float) -> float:
        self.last_market_args = {
            "side": side,
            "mid": mid,
            "spread": spread,
            "qty": qty,
            "top_liquidity": top_liquidity
        }
        return self.market_slip

    def expected_limit_price(self, side: str, base_price: float, mid: float, micro_revert_bps: float = 0.5) -> float:
        k = micro_revert_bps / 1e4
        if side == "BUY":
            return base_price - k * (base_price - mid)
        else:
            return mid - k * (mid - base_price)




# ------------------ Mock OrderBook ------------------

class MockOrderBook(OrderBookProtocol):
    def __init__(self, bid=None, ask=None, top_liquidity = 100.0):
        self.bid = bid
        self.ask = ask
        self.top_liquidity = top_liquidity

    def get_best_price(self, side: str):
        return self.bid if side == "bid" else self.ask
    
    def get_top_liquidity(self, side: str):
        return self.top_liquidity

# ------------------ Initialization ------------------

def test_default_initialization():
    mock_slippage = MockSlippageModel()
    model : SmartRepricingModelProtocol = SmartRepricingModel(slippage_model = mock_slippage)
    assert model.tick_size == 0.01
    assert model.max_jitter_ticks == 2
    assert model.slippage_bps == pytest.approx(5.0, rel=1e-6)

def test_custom_initialization():
    mock_slippage = MockSlippageModel()
    model : SmartRepricingModelProtocol = SmartRepricingModel(tick_size=0.005, max_jitter_ticks=3, slippage_bps=10.0, slippage_model = mock_slippage)
    assert model.tick_size == 0.005
    assert model.max_jitter_ticks == 3
    assert model.slippage_bps == pytest.approx(10.0, rel=1e-6)

# ------------------ Fallback Behavior ------------------

def test_fallback_missing_bid():
    mock_slippage = MockSlippageModel()
    model : SmartRepricingModelProtocol = SmartRepricingModel(slippage_model = mock_slippage)
    ob = MockOrderBook(bid=None, ask=100.0)
    price = model.optimize_price("BUY", ob)
    assert price == 100.0

def test_fallback_missing_ask():
    mock_slippage = MockSlippageModel()
    model : SmartRepricingModelProtocol = SmartRepricingModel(slippage_model = mock_slippage)
    ob = MockOrderBook(bid=99.0, ask=None)
    price = model.optimize_price("SELL", ob)
    assert price == 99.0

def test_fallback_missing_mid():
    mock_slippage = MockSlippageModel()
    model : SmartRepricingModelProtocol = SmartRepricingModel(slippage_model = mock_slippage)
    ob = MockOrderBook(bid=None, ask=None)
    price = model.optimize_price("BUY", ob)
    assert price is None

# ------------------ Base Price Logic ------------------

def test_base_price_tight_spread():
    mock_slippage = MockSlippageModel()
    model : SmartRepricingModelProtocol = SmartRepricingModel(slippage_model = mock_slippage)
    ob = MockOrderBook(bid=99.99, ask=100.00)  # spread = 0.01, mid = 99.995
    price = model.optimize_price("BUY", ob)
    assert price >= 100.00  # snapped tick

def test_base_price_wide_spread_buy():
    mock_slippage = MockSlippageModel()
    model : SmartRepricingModelProtocol = SmartRepricingModel(slippage_model = mock_slippage)
    ob = MockOrderBook(bid=98.0, ask=102.0)  # spread = 4.0, mid = 100.0
    price = model.optimize_price("BUY", ob, fill_prob_target=0.5)
    expected_base = 102.0 - (4.0 * 0.5)  # offset = 2.0 → base = 100.0
    assert abs(price - expected_base) <= 0.05  # allow jitter

def test_base_price_wide_spread_sell():
    mock_slippage = MockSlippageModel()
    model = SmartRepricingModel(slippage_bps=50, slippage_model = mock_slippage)
    ob = MockOrderBook(bid=98.0, ask=102.0)
    price = model.optimize_price("SELL", ob, fill_prob_target=0.25)
    mid = (98.0 + 102.0) / 2
    max_slip = mid * 0.005
    assert mid - max_slip <= price <= mid + max_slip


# ------------------ Jitter and Slippage ------------------


def test_jitter_respects_slippage_cap():
    random.seed(42)  # ✅ consistent jitter
    mock_slippage = MockSlippageModel()
    model = SmartRepricingModel(
        tick_size=0.01,
        max_jitter_ticks=100,
        slippage_bps=1.0,
        slippage_model=mock_slippage
    )
    ob = MockOrderBook(bid=99.0, ask=101.0)  # mid = 100.0 → max_slip = 1.0
    mid = (ob.bid + ob.ask) / 2
    max_slip = mid * 0.01  # slippage_bps = 1.0 → 1%

    for _ in range(100):
        price = model.optimize_price("BUY", ob)
        assert mid - max_slip <= price <= mid + max_slip  # ✅ clamp respected



def test_tick_snapping():
    mock_slippage = MockSlippageModel()
    model : SmartRepricingModelProtocol = SmartRepricingModel(tick_size=0.05, slippage_model = mock_slippage)
    ob = MockOrderBook(bid=99.0, ask=101.0)
    price = model.optimize_price("SELL", ob)
    assert (price * 100) % 5 == 0  # snapped to 0.05 tick

def test_buy_price_enforced_within_slippage_bounds():
    mock_slippage = MockSlippageModel()
    model = SmartRepricingModel(tick_size=0.01, max_jitter_ticks=100, slippage_bps=0.5, slippage_model = mock_slippage)
    ob = MockOrderBook(bid=99.0, ask=101.0)  # mid = 100.0 → max_slip = 0.5
    for _ in range(50):
        price = model.optimize_price("BUY", ob)
        assert 100.5 >= price >= 100.5 - 1.0  # best_ask ± slippage

def test_sell_price_enforced_within_slippage_bounds():
    mock_slippage = MockSlippageModel()
    model = SmartRepricingModel(tick_size=0.01, max_jitter_ticks=100, slippage_bps=50, slippage_model = mock_slippage)
    ob = MockOrderBook(bid=99.0, ask=101.0)
    mid = (99.0 + 101.0) / 2
    max_slip = mid * 0.005
    for _ in range(50):
        price = model.optimize_price("SELL", ob)
        assert mid - max_slip <= price <= mid + max_slip


def test_fill_prob_target_affects_buy_price():
    mock_slippage = MockSlippageModel()
    model = SmartRepricingModel(slippage_model = mock_slippage)
    ob = MockOrderBook(bid=98.0, ask=102.0)
    low_fill_price = model.optimize_price("BUY", ob, fill_prob_target=0.1)
    high_fill_price = model.optimize_price("BUY", ob, fill_prob_target=0.9)
    assert low_fill_price < high_fill_price  # more aggressive pricing for higher fill target



from decimal import Decimal

def test_tick_snapping_precision():
    mock_slippage = MockSlippageModel()
    model = SmartRepricingModel(tick_size=0.01, slippage_model = mock_slippage)
    ob = MockOrderBook(bid=99.0, ask=101.0)
    tick = Decimal(str(model.tick_size))
    for _ in range(20):
        price = Decimal(str(model.optimize_price("BUY", ob)))
        ticks = price / tick
        assert ticks == ticks.to_integral_value()


