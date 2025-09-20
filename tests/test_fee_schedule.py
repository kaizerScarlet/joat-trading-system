import pytest
from Execution_layer.fee_schedule import FeeSchedule

# ------------------ Initialization ------------------

def test_default_initialization():
    fee = FeeSchedule()
    assert fee.maker_bps == 10.0
    assert fee.taker_bps == 10.0
    assert fee.maker_rate() == 0.0010
    assert fee.taker_rate() == 0.0010

def test_custom_initialization():
    fee = FeeSchedule(maker_bps=5.5, taker_bps=12.3)
    assert fee.maker_bps == 5.5
    assert fee.taker_bps == 12.3
    assert fee.maker_rate() == pytest.approx(0.00055, rel=1e-6)
    assert fee.taker_rate() == pytest.approx(0.00123, rel=1e-6)

# ------------------ Edge Cases ------------------

def test_zero_fees():
    fee = FeeSchedule(maker_bps=0.0, taker_bps=0.0)
    assert fee.maker_rate() == 0.0
    assert fee.taker_rate() == 0.0

def test_negative_fees():
    fee = FeeSchedule(maker_bps=-5.0, taker_bps=-10.0)
    assert fee.maker_rate() == -0.0005
    assert fee.taker_rate() == -0.0010

def test_high_precision_fees():
    fee = FeeSchedule(maker_bps=7.777, taker_bps=9.999)
    assert fee.maker_rate() == pytest.approx(0.0007777, rel=1e-6)
    assert fee.taker_rate() == pytest.approx(0.0009999, rel=1e-6)
