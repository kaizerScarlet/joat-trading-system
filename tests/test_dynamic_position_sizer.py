import pytest 
from dynamic_risk_engine.dynamic_position_sizer import DynamicPositionSizer

def test_default_initialization():
    sizer = DynamicPositionSizer()
    assert sizer.max_risk_per_trade == 0.01
    assert sizer.account_balance == 100000


def test_position_size_basic_calculation():
    sizer = DynamicPositionSizer(max_risk_per_trade=0.01, account_balance=100000)
    position_size = sizer.calculate_position_size(stop_loss_distance=10, signal_confidence=1.0, win_rate=0.5, rr_ratio=2.0)
    
    expected_risk = 100000 * 0.01  * 1.0 * (0.5 + 0.5)  # 1% risk, confidence 1.0, win rate 0.5
    expected_position_size = expected_risk / 10  # stop loss distance of 10
    assert position_size == round(expected_position_size, 4)
    assert round(position_size, 4) == round(expected_position_size, 4)



def test_zero_stop_loss_returns_zero():
    sizer = DynamicPositionSizer(max_risk_per_trade=0.01, account_balance=100000)
    position_size = sizer.calculate_position_size(stop_loss_distance=0, signal_confidence=1.0, win_rate=0.5, rr_ratio=2.0)
    assert position_size == 0  # Should return 0 to avoid division by zero


def test_low_confidence_reduces_sizer():
    sizer = DynamicPositionSizer(max_risk_per_trade=0.01, account_balance=100000)
    position_size_high_confidence = sizer.calculate_position_size(stop_loss_distance=10, signal_confidence=1.0, win_rate=0.5, rr_ratio=2.0)
    position_size_low_confidence = sizer.calculate_position_size(stop_loss_distance=10, signal_confidence=0.5, win_rate=0.5, rr_ratio=2.0)
    
    assert position_size_low_confidence < position_size_high_confidence


def test_low_win_rate_reduces_sizer():
    sizer = DynamicPositionSizer(max_risk_per_trade=0.01, account_balance=100000)
    position_size_high_win_rate = sizer.calculate_position_size(stop_loss_distance=10, signal_confidence=1.0, win_rate=0.8, rr_ratio=2.0)
    position_size_low_win_rate = sizer.calculate_position_size(stop_loss_distance=10, signal_confidence=1.0, win_rate=0.2, rr_ratio=2.0)
    
    assert position_size_low_win_rate < position_size_high_win_rate



def test_reset_functionality():
    sizer = DynamicPositionSizer(max_risk_per_trade=0.01, account_balance=100000)
    sizer.max_risk_per_trade = 0.02
    sizer.account_balance = 200000
    
    sizer.reset()
    
    assert sizer.max_risk_per_trade == 0.01
    assert sizer.account_balance == 100000


def test_position_size_rounding():
    sizer = DynamicPositionSizer(max_risk_per_trade=0.015, account_balance=123456.78)
    size = sizer.calculate_position_size(7.25, signal_confidence=0.75, win_rate=0.66, rr_ratio=1.5)
    assert isinstance(size, float)
    assert len(str(size).split('.')[-1]) <= 4  # Ensure rounding to 4 decimal places