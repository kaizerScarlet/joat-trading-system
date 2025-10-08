import pytest
from Execution_layer.slippage_model import SlippageModel
from Execution_layer.slippage_model_protocol import SlippageModelProtocol

# ------------------ Initialization ------------------

def test_default_initialization():
    model : SlippageModelProtocol = SlippageModel()
    assert model.impact_coeff == 0.5

def test_custom_initialization():
    model : SlippageModelProtocol = SlippageModel(impact_coeff=0.8)
    assert model.impact_coeff == 0.8

# ------------------ Market Order Slippage ------------------

def test_market_slip_basic():
    model : SlippageModelProtocol = SlippageModel(impact_coeff=0.5)
    slip = model.expected_market_slip("BUY", mid=100.0, spread=2.0, qty=5.0, top_liquidity=10.0)
    # half_spread = 1.0, impact = 0.5 * (5/10) * 2 = 0.5
    assert slip == pytest.approx(1.5, rel=1e-6)

def test_market_slip_zero_liquidity():
    model : SlippageModelProtocol = SlippageModel()
    slip = model.expected_market_slip("SELL", mid=100.0, spread=2.0, qty=5.0, top_liquidity=0.0)
    assert slip == pytest.approx(1.0, rel=1e-6)  # only half spread

def test_market_slip_zero_qty():
    model : SlippageModelProtocol = SlippageModel()
    slip = model.expected_market_slip("BUY", mid=100.0, spread=2.0, qty=0.0, top_liquidity=10.0)
    assert slip == pytest.approx(1.0, rel=1e-6)

def test_market_slip_zero_spread():
    model : SlippageModelProtocol = SlippageModel()
    slip = model.expected_market_slip("SELL", mid=100.0, spread=0.0, qty=5.0, top_liquidity=10.0)
    assert slip == 0.0

def test_market_slip_extreme_qty():
    model : SlippageModelProtocol = SlippageModel()
    slip = model.expected_market_slip("BUY", mid=100.0, spread=2.0, qty=1e6, top_liquidity=1.0)
    assert slip > 1e6  # huge impact

# ------------------ Limit Order Price ------------------

def test_limit_price_buy_basic():
    model : SlippageModelProtocol = SlippageModel()
    price = model.expected_limit_price("BUY", base_price=99.0, mid=100.0)
    # k = 0.00005, pull = 0.00005 * (99 - 100) = -0.00005 → price = 99.00005
    assert price == pytest.approx(99.00005, rel=1e-6)

def test_limit_price_sell_basic():
    model: SlippageModelProtocol = SlippageModel()
    price = model.expected_limit_price("SELL", base_price=101.0, mid=100.0)
    assert price == pytest.approx(100.00005, rel=1e-6)


def test_limit_price_zero_reversion():
    model : SlippageModelProtocol = SlippageModel()
    price = model.expected_limit_price("BUY", base_price=99.0, mid=100.0, micro_revert_bps=0.0)
    assert price == 99.0

def test_limit_price_negative_mid():
    model : SlippageModelProtocol = SlippageModel()
    price = model.expected_limit_price("SELL", base_price=101.0, mid=-100.0)
    assert price >= 0.0  # clamped

def test_limit_price_negative_base():
    model : SlippageModelProtocol = SlippageModel()
    price = model.expected_limit_price("BUY", base_price=-99.0, mid=100.0)
    assert price == 0.0  # clamped

def test_limit_price_invalid_side_defaults_to_sell():
    model : SlippageModelProtocol = SlippageModel()
    price = model.expected_limit_price("INVALID", base_price=101.0, mid=100.0)
    # defaults to SELL logic
    assert price < 101.0
