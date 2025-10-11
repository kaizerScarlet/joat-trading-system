import pytest 
from dynamic_risk_engine.performance_tracker import PerformanceTracker
from dynamic_risk_engine.performance_tracker_protocol import PerformanceTrackerProtocol

def test_tracker_basic_metrics():
    tracker : PerformanceTrackerProtocol =  PerformanceTracker()

    #Simulate 3 trades: 2 wins and 1 loss
    tracker.record_trade(order_id= 't1',pnl=100, risk=50, reward=150)
    tracker.record_trade(order_id='t2',pnl=-50, risk=50, reward=100)
    tracker.record_trade(order_id='t3',pnl=200, risk=100, reward=300)


    summary = tracker.get_summary()
    assert summary['total_trades'] == 3
    assert summary['win_rate'] == pytest.approx( 2/3, 0.01)
    #assert summary['average_rrr'] == pytest.approx((3+2)/2, 0.01)
    assert summary['profit_factor'] == pytest.approx(300 / 50, 0.01)
    assert summary['final_balance'] == 250.0  # 100 - 50 + 200


def test_track_edge_cases_no_trades():
    tracker : PerformanceTrackerProtocol = PerformanceTracker()

    summary = tracker.get_summary()
    assert summary['total_trades'] == 0
    assert summary['win_rate'] == 0.0
    assert summary['average_rrr'] == 0.0
    assert summary['profit_factor'] == float('inf')  # No losses, so profit factor is undefined
    assert summary['final_balance'] == 0.0

def test_tracker_reset():
    tracker : PerformanceTrackerProtocol = PerformanceTracker()

    # Simulate some trades
    tracker.record_trade(order_id='t1', pnl=100, risk=50, reward=150)
    tracker.record_trade(order_id='t2', pnl=-50, risk=50, reward=100)

    # Check summary before reset
    summary_before = tracker.get_summary()
    assert summary_before['total_trades'] == 2

    # Reset the tracker
    tracker.reset()

    # Check summary after reset
    summary_after = tracker.get_summary()
    assert summary_after['total_trades'] == 0
    assert tracker.get_equity_curve() == []
    assert tracker.balance == 0.0
    assert summary_after['win_rate'] == 0.0
    assert summary_after['final_balance'] == 0.0


def test_sl_tp_drift_recording():
    tracker : PerformanceTrackerProtocol = PerformanceTracker()
    tracker.record_sl_tp_drift(order_id="t1", sl=95.0, tp=120.0)
    assert len(tracker.sl_tp_history) == 1
    drift = tracker.sl_tp_history[0]
    assert drift["order_id"] == "t1"
    assert drift["sl"] == 95.0
    assert drift["tp"] == 120.0


def test_trade_diagnostics_recording():
    tracker : PerformanceTrackerProtocol = PerformanceTracker()
    tracker.record_slippage(order_id="t1", slippage=0.5, side="buy", qty=1.0, price=100.0, symbol="BTCUSDT")
    tracker.record_fee(order_id="t1", fee=0.1, side="buy", qty=1.0, price=100.0, symbol="BTCUSDT")
    tracker.record_latency(order_id="t1", latency_ms=120.0, side="buy", qty=1.0, price=100.0, symbol="BTCUSDT")
    tracker.record_fill_probability(order_id="t1", fill_probability=0.85, side="buy", qty=1.0, price=100.0, symbol="BTCUSDT")

    assert len(tracker.slippage_fee) == 1
    assert len(tracker.fee) == 1
    assert len(tracker.trade_latency) == 1
    assert len(tracker.fill_probability) == 1


def test_get_last_trade():
    tracker : PerformanceTrackerProtocol = PerformanceTracker()
    tracker.record_trade(order_id="t1", pnl=100, risk=50, reward=150)
    last = tracker.get_last_trade()
    assert last["order_id"] == "t1"
    assert last["pnl"] == 100

def test_diagnostics_snapshot():
    tracker : PerformanceTrackerProtocol = PerformanceTracker()
    tracker.record_trade(order_id="t1", pnl=100, risk=50, reward=150)
    tracker.record_slippage(order_id="t1", slippage=0.5, side="buy", qty=1.0, price=100.0, symbol="BTCUSDT")
    diagnostics = tracker.get_diagnostics()
    assert diagnostics["total_trades"] == 1
    assert diagnostics["slippage_events"] == 1
