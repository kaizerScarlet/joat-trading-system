import pytest
from unittest.mock import Mock 
from Execution_layer.adaptive_sl_tp import AdaptiveSLTP
from Execution_layer.adaptive_sl_tp_protocol import AdaptiveSLTPProtocol
from market_data.orderbook_protocol import OrderBookProtocol
from alpha_scoring.Alphablender_protocol import AlphaBlenderProtocol


# -----------------------------
# Mocks for OrderBook & AlphaBlender
# -----------------------------
class MockOrderBook(OrderBookProtocol):
    def __init__(self, midprice=100.0, volatility=0.01):
        self._mid = midprice
        self._vol = volatility
    def get_midprice(self): return self._mid
    def get_volatility_estimate(self): return self._vol
    def get_order_age_score(self): return 0.5
    def get_cancel_activity_score(self): return 0.5
    def get_layering_score(self): return 0.5


class MockAlphaBlender(AlphaBlenderProtocol):
    def __init__(self, bid_score=0.8, ask_score=0.2):
        self._bid_score = bid_score
        self._ask_score = ask_score
    def compute_alpha_score(self):
        return {"bid": self._bid_score, "ask": self._ask_score}


def make_sltp(mid=100.0, vol=0.01, alpha_bid=0.8, alpha_ask=0.2):
    sltp : AdaptiveSLTPProtocol = AdaptiveSLTP(
        regime_classifier = Mock(),
        orderbook = MockOrderBook(),
        alpha_score = MockAlphaBlender(),
        alpha_weights={
        "order_age": 0.1,
        "cancel_activity": 0.2,
        "layering": 0.15,
        "iceberg_score": 0.1,
        "cancel_density_score": 0.1,
        "order_laddering_score": 0.1,
        "order_spoofing_score": 0.15,
        "synthetic_fill_score": 0.1
    })
    sltp.ob = MockOrderBook(mid, vol)
    sltp.alpha_score = MockAlphaBlender(alpha_bid, alpha_ask)
    return sltp


# -----------------------------
# ATR Calculation
# -----------------------------
def test_atr_insufficient_data():
    sltp = make_sltp()
    sltp.update_candlestick(101, 99, 100)
    assert sltp._calculate_atr() == 0.0

def test_atr_correctness():
    sltp = make_sltp()
    data = [(102, 98, 100), (103, 99, 101), (104, 100, 102)]
    for h, l, c in data:
        sltp.update_candlestick(h, l, c)
    manual_trs = [max(102-98, abs(102-0), abs(98-0)),  # first TR nonsense with zero close prev
                  max(103-99, abs(103-100), abs(99-100)),
                  max(104-100, abs(104-101), abs(100-101))]
    manual_atr = sum(manual_trs[1:]) / len(manual_trs[1:])
    assert pytest.approx(sltp._calculate_atr(), rel=1e-6) == manual_atr


# -----------------------------
# Start Trade
# -----------------------------
def test_start_trade_bid():
    sltp = make_sltp()
    for _ in range(15):
        sltp.update_candlestick(101, 99, 100)
    sl, tp = sltp.start_trade("bid")
    assert sl < sltp.entry_price < tp
    assert sltp.original_risk > 0

def test_start_trade_ask():
    sltp = make_sltp()
    for _ in range(15):
        sltp.update_candlestick(101, 99, 100)
    sl, tp = sltp.start_trade("ask")
    assert sl > sltp.entry_price > tp
    assert sltp.original_risk > 0

def test_start_trade_midprice_zero():
    sltp = make_sltp(mid=0.0)
    with pytest.raises(ValueError):
        sltp.start_trade("bid")

def test_start_trade_invalid_side():
    sltp = make_sltp()
    for _ in range(15):
        sltp.update_candlestick(101, 99, 100)
    with pytest.raises(ValueError):
        sltp.start_trade("long")


# -----------------------------
# Break-even & SL tightening
# -----------------------------
def test_break_even_bid():
    sltp = make_sltp()
    for _ in range(15):
        sltp.update_candlestick(105, 95, 100)
    sltp.start_trade("bid")
    sltp.original_risk = 1.0
    sltp.entry_price = 100
    sltp.ob._mid = 101  # >= entry + risk
    sltp.monitor_and_adjust()
    assert sltp.stop_loss == 100  # moved to break-even

def test_break_even_ask():
    sltp = make_sltp()
    for _ in range(15):
        sltp.update_candlestick(105, 95, 100)
    sltp.start_trade("ask")
    sltp.original_risk = 1.0
    sltp.entry_price = 100
    sltp.ob._mid = 99  # <= entry - risk
    sltp.monitor_and_adjust()
    assert sltp.stop_loss == 100  # moved to break-even


# -----------------------------
# SL tightening only
# -----------------------------
def test_sl_tighten_only_bid():
    sltp = make_sltp()
    for _ in range(15):
        sltp.update_candlestick(105, 95, 100)
    sltp.start_trade("bid")
    sltp.stop_loss = 95
    sltp.ob._mid = 102
    sltp.monitor_and_adjust()
    assert sltp.stop_loss >= 95  # never loosens

def test_sl_tighten_only_ask():
    sltp = make_sltp()
    for _ in range(15):
        sltp.update_candlestick(105, 95, 100)
    sltp.start_trade("ask")
    sltp.stop_loss = 105
    sltp.ob._mid = 98
    sltp.monitor_and_adjust()
    assert sltp.stop_loss <= 105  # never loosens for short


# -----------------------------
# TP extension only
# -----------------------------
def test_tp_extension_only_bid():
    sltp = make_sltp()
    for _ in range(15):
        sltp.update_candlestick(105, 95, 100)
    sltp.start_trade("bid")
    old_tp = sltp.take_profit
    sltp.ob._mid = 110
    sltp.monitor_and_adjust()
    assert sltp.take_profit >= old_tp

def test_tp_extension_only_ask():
    sltp = make_sltp()
    for _ in range(15):
        sltp.update_candlestick(105, 95, 100)
    sltp.start_trade("ask")
    old_tp = sltp.take_profit
    sltp.ob._mid = 90
    sltp.monitor_and_adjust()
    assert sltp.take_profit <= old_tp


# -----------------------------
# Proximity to TP tightening
# -----------------------------
def test_proximity_tightening_bid():
    sltp = make_sltp()
    for _ in range(15):
        sltp.update_candlestick(105, 95, 100)
    sltp.start_trade("bid")
    sltp.take_profit = sltp.entry_price + 0.05
    sltp.ob._mid = sltp.take_profit - 0.01
    gap_close = sltp._compute_trailing_gap(1.0, sltp.ob.get_midprice())
    assert gap_close <= (sltp._calculate_atr() * sltp.base_atr_multiplier * 1.5)

def test_proximity_tightening_ask():
    sltp = make_sltp()
    for _ in range(15):
        sltp.update_candlestick(105, 95, 100)
    sltp.start_trade("ask")
    sltp.take_profit = sltp.entry_price - 0.05
    sltp.ob._mid = sltp.take_profit + 0.01
    gap_close = sltp._compute_trailing_gap(1.0, sltp.ob.get_midprice())
    assert gap_close <= (sltp._calculate_atr() * sltp.base_atr_multiplier * 1.5)


# -----------------------------
# stop_trade() resets state
# -----------------------------
def test_stop_trade_resets_state():
    sltp = make_sltp()
    for _ in range(15):
        sltp.update_candlestick(105, 95, 100)
    sltp.start_trade("bid")
    sltp.stop_trade()
    assert not sltp.in_trade
    assert all(v is None for k, v in sltp.debug_state().items() if k in ["side", "entry_price", "stop_loss", "take_profit", "original_risk"])



# -----------------------------
# Stress: Zero volatility
# -----------------------------
def test_zero_volatility_bid():
    sltp = make_sltp(vol=0.0)  # volatility = 0
    for _ in range(15):
        sltp.update_candlestick(100, 100, 100)  # ATR will also be ~0
    sl, tp = sltp.start_trade("bid")
    assert sl < sltp.entry_price < tp  # still valid
    assert sltp.original_risk > 0  # even with zero vol, ATR fallback must work

def test_zero_volatility_ask():
    sltp = make_sltp(vol=0.0)
    for _ in range(15):
        sltp.update_candlestick(100, 100, 100)
    sl, tp = sltp.start_trade("ask")
    assert sl > sltp.entry_price > tp
    assert sltp.original_risk > 0


# -----------------------------
# Stress: Extremely high volatility
# -----------------------------
def test_extreme_volatility_bid():
    sltp = make_sltp(vol=5.0)  # 500% volatility
    for _ in range(15):
        sltp.update_candlestick(200, 50, 100)
    sl, tp = sltp.start_trade("bid")
    # Should create a *very wide* SL/TP but still logical
    assert tp - sltp.entry_price > 1.0
    assert sltp.entry_price - sl > 1.0

def test_extreme_volatility_ask():
    sltp = make_sltp(vol=5.0)
    for _ in range(15):
        sltp.update_candlestick(200, 50, 100)
    sl, tp = sltp.start_trade("ask")
    assert sl - sltp.entry_price > 1.0
    assert sltp.entry_price - tp > 1.0


# -----------------------------
# Stress: Tiny ATR but nonzero volatility
# -----------------------------
def test_tiny_atr_bid():
    sltp = make_sltp(vol=0.05)
    # Almost flat prices -> ATR very small
    for _ in range(15):
        sltp.update_candlestick(100.001, 99.999, 100.0)
    sl, tp = sltp.start_trade("bid")
    assert sltp.original_risk > 0
    assert tp - sltp.entry_price > 0

def test_tiny_atr_ask():
    sltp = make_sltp(vol=0.05)
    for _ in range(15):
        sltp.update_candlestick(100.001, 99.999, 100.0)
    sl, tp = sltp.start_trade("ask")
    assert sltp.original_risk > 0
    assert sltp.entry_price - tp > 0


# -----------------------------
# Stress: Huge ATR compared to volatility
# -----------------------------
def test_huge_atr_vs_volatility_bid():
    sltp = make_sltp(vol=0.01)
    for _ in range(15):
        sltp.update_candlestick(150, 50, 100)  # ATR large
    sl, tp = sltp.start_trade("bid")
    assert sl < sltp.entry_price < tp
    assert sltp.original_risk > 0

def test_huge_atr_vs_volatility_ask():
    sltp = make_sltp(vol=0.01)
    for _ in range(15):
        sltp.update_candlestick(150, 50, 100)
    sl, tp = sltp.start_trade("ask")
    assert sl > sltp.entry_price > tp
    assert sltp.original_risk > 0

def test_sl_tightening_event_logged_bid():
    sltp = make_sltp()
    for _ in range(15):
        sltp.update_candlestick(105, 95, 100)
    sltp.start_trade("bid")

    # Simulate a midprice that will trigger tightening
    mid = 102
    sltp.ob._mid = mid

    # Compute the expected tightening level
    composite_score = sltp._compute_composite_score()
    gap = sltp._compute_trailing_gap(composite_score, mid)
    proposed_sl = round(mid - gap, 8)

    # Set stop_loss just below proposed_sl to guarantee tightening
    sltp.stop_loss = proposed_sl - 0.01
    sltp.monitor_and_adjust()

    # Assert that a tightening event was logged
    assert len(sltp.sl_tightening_events) > 0
    event = sltp.sl_tightening_events[-1]
    assert event["old_sl"] < event["new_sl"]





def test_debug_state_snapshot():
    sltp = make_sltp()
    for _ in range(15):
        sltp.update_candlestick(105, 95, 100)
    sltp.start_trade("bid")
    sltp.ob._mid = 102
    sltp.monitor_and_adjust()
    state = sltp.debug_state()
    assert state["in_trade"] is True
    assert state["composite_score"] > 0
    assert state["stop_loss"] is not None
