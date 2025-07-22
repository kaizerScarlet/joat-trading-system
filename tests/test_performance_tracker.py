import pytest 
from dynamic_risk_engine.performance_tracker import PerformanceTracker

def test_tracker_basic_metrics():
    tracker =  PerformanceTracker()

    #Simulate 3 trades: 2 wins and 1 loss
    tracker.record_trade(pnl=100, risk=50, reward=150)
    tracker.record_trade(pnl=-50, risk=50, reward=100)
    tracker.record_trade(pnl=200, risk=100, reward=300)


    summary = tracker.get_summary()
    assert summary['total_trades'] == 3
    assert summary['win_rate'] == pytest.approx( 2/3, 0.01)
    #assert summary['average_rrr'] == pytest.approx((3+2)/2, 0.01)
    assert summary['profit_factor'] == pytest.approx(300 / 50, 0.01)
    assert summary['final_balance'] == 250.0  # 100 - 50 + 200


def test_track_edge_cases_no_trades():
    tracker = PerformanceTracker()

    summary = tracker.get_summary()
    assert summary['total_trades'] == 0
    assert summary['win_rate'] == 0.0
    assert summary['average_rrr'] == 0.0
    assert summary['profit_factor'] == float('inf')  # No losses, so profit factor is undefined
    assert summary['final_balance'] == 0.0

def test_tracker_reset():
    tracker = PerformanceTracker()

    # Simulate some trades
    tracker.record_trade(pnl=100, risk=50, reward=150)
    tracker.record_trade(pnl=-50, risk=50, reward=100)

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