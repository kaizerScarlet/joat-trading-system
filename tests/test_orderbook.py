import pytest
import time
from market_data.orderbook import OrderBook

@pytest.fixture
def orderbook():
    return OrderBook()

# ------------------ Basic Update & Accessors ------------------

def test_bid_ask_update(orderbook):
    msg = {"bid": [["100.0", "1.5"]], "ask": [["101.0", "2.0"]]}
    orderbook.update(msg)
    assert orderbook.bids[100.0] == 1.5
    assert orderbook.asks[101.0] == 2.0

def test_bid_removal(orderbook):
    orderbook.update({"bid": [["100.0", "1.0"]]})
    orderbook.update({"bid": [["100.0", "0.0"]]})
    assert 100.0 not in orderbook.bids

def test_ask_removal(orderbook):
    orderbook.update({"ask": [["101.0", "1.0"]]})
    orderbook.update({"ask": [["101.0", "0.0"]]})
    assert 101.0 not in orderbook.asks

def test_midprice_calculation(orderbook):
    orderbook.update({"bid": [["99.0", "1.0"]], "ask": [["101.0", "1.0"]]})
    assert orderbook.get_midprice() == 100.0

def test_midprice_with_only_bid(orderbook):
    orderbook.update({"bid": [["100.0", "1.0"]]})
    assert orderbook.get_midprice() == 0.0

def test_midprice_with_only_ask(orderbook):
    orderbook.update({"ask": [["101.0", "1.0"]]})
    assert orderbook.get_midprice() == 0.0

def test_get_level_size(orderbook):
    orderbook.update({"bid": [["100.0", "1.0"]]})
    assert orderbook.get_level_size(100.0, "bid") == 1.0
    assert orderbook.get_level_size(101.0, "ask") == 0.0

def test_get_best_price(orderbook):
    orderbook.update({
        "bid": [["99.0", "1.0"], ["100.0", "1.0"]],
        "ask": [["101.0", "1.0"], ["102.0", "1.0"]]
    })
    assert orderbook.get_best_price("bid") == 100.0
    assert orderbook.get_best_price("ask") == 101.0

# ------------------ Liquidity Metrics ------------------

def test_estimated_volume(orderbook):
    orderbook.update({"bid": [["100.0", "1.0"], ["99.0", "2.0"]]})
    assert orderbook.get_estimated_volume("bid") == 3.0

def test_top_liquidity(orderbook):
    orderbook.update({"ask": [["101.0", "1.0"], ["102.0", "2.0"], ["103.0", "3.0"]]})
    assert orderbook.get_top_liquidity("ask", depth_levels=2) == 3.0

def test_liquidity_within_bps(orderbook):
    orderbook.update({
        "bid": [["99.0", "1.0"], ["98.5", "1.0"]],
        "ask": [["101.0", "1.0"], ["101.5", "1.0"]]
    })
    assert orderbook.get_liquidity_within_bps("bid", bps=100) == 1.0
    assert orderbook.get_liquidity_within_bps("ask", bps=100) == 1.0

def test_liquidity_within_bps_edge(orderbook):
    orderbook.update({
        "bid": [["100.004", "1.0"]],
        "ask": [["100.006", "1.0"]]
    })
    assert orderbook.get_midprice() == pytest.approx(100.005, rel=1e-6)
    assert orderbook.get_liquidity_within_bps("bid", bps=1) == 1.0  # 1 bps = 0.01



def test_liquidity_empty_book(orderbook):
    assert orderbook.get_estimated_volume("bid") == 0.0
    assert orderbook.get_top_liquidity("ask", depth_levels=5) == 0.0
    assert orderbook.get_liquidity_within_bps("bid", bps=50) == 0.0

# ------------------ Microstructure Metrics ------------------

def test_order_imbalance(orderbook):
    orderbook.update({"bid": [["100.0", "3.0"]], "ask": [["101.0", "1.0"]]})
    imbalance = orderbook.get_order_imbalance()
    assert 0.74 < imbalance < 0.76

def test_order_imbalance_balanced(orderbook):
    orderbook.update({"bid": [["100.0", "1.0"]], "ask": [["101.0", "1.0"]]})
    assert orderbook.get_order_imbalance() == 0.5

def test_order_imbalance_empty(orderbook):
    assert orderbook.get_order_imbalance() == 0.5

def test_volatility_estimate(orderbook):
    for i in range(10):
        orderbook.update({
            "bid": [[str(99 + i), "1.0"]],
            "ask": [[str(101 + i), "1.0"]]
        })
    assert orderbook.get_volatility_estimate() > 0.0

import random

import random
from market_data.orderbook import OrderBook

def test_volatility_under_noise():
    orderbook = OrderBook()
    base = 100.0
    bid = base

    # Simulate compounding drift + noise
    for i in range(100):
        drift = 1.0 if i % 10 < 5 else -1.0
        noise = random.uniform(-0.5, 0.5)
        bid += drift + noise
        ask = bid + random.uniform(0.5, 1.5)
        orderbook.update({
            "bid": [[str(round(bid, 2)), "1.0"]],
            "ask": [[str(round(ask, 2)), "1.0"]]
        })

    # Adaptive threshold based on baseline volatility
    baseline = OrderBook().get_volatility_estimate()
    measured = orderbook.get_volatility_estimate()

    # Use a realistic multiplier for production-grade reflex
    assert measured > baseline * 1.1, f"Volatility too low: {measured} (baseline: {baseline})"






def test_volatility_minimal_baseline(orderbook):
    assert orderbook.get_volatility_estimate() == 0.001

# ------------------ Timing & Tick ------------------

def test_update_rate(orderbook):
    orderbook.update({"bid": [["100.0", "1.0"]], "ask": [["101.0", "1.0"]]})
    time.sleep(0.01)
    assert orderbook.get_update_rate() > 0.0

def test_update_rate_no_updates(orderbook):
    assert orderbook.get_update_rate() == 0.0

def test_tick_size(orderbook):
    assert orderbook.get_tick_size() == 0.01

# ------------------ Defensive & Edge ------------------

def test_empty_update_message(orderbook):
    orderbook.update({})
    assert orderbook.get_midprice() == 0.0

def test_malformed_update_message(orderbook):
    orderbook.update({"bid": [["bad_price", "1.0"]]})  # Should not crash
    assert isinstance(orderbook.get_midprice(), float)

def test_large_depth_update(orderbook):
    msg = {"bid": [[str(100 - i), "1.0"] for i in range(150)],
           "ask": [[str(101 + i), "1.0"] for i in range(150)]}
    orderbook.update(msg)
    assert len(orderbook.bids) <= 150
    assert len(orderbook.asks) <= 150
    assert len(orderbook.price_history) <= 100
