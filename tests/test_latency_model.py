import pytest
import random
from Execution_layer.latency_model import LatencyModel

# ------------------ Initialization ------------------

def test_default_initialization():
    model = LatencyModel()
    assert model.base_ms == 20.0
    assert model.jitter_ms == 15.0
    assert model.p_tail == 0.05
    assert model.tail_multiplier == 3.0

def test_custom_initialization():
    model = LatencyModel(base_ms=10.0, jitter_ms=5.0, p_tail=0.1, tail_multiplier=2.0)
    assert model.base_ms == 10.0
    assert model.jitter_ms == 5.0
    assert model.p_tail == 0.1
    assert model.tail_multiplier == 2.0

# ------------------ Sampling Behavior ------------------

def test_sample_ms_within_expected_range():
    model = LatencyModel(base_ms=20.0, jitter_ms=10.0, p_tail=0.0)
    for _ in range(1000):
        latency = model.sample_ms()
        assert 10 <= latency <= 30  # base ± jitter

def test_tail_latency_triggered():
    model = LatencyModel(base_ms=20.0, jitter_ms=0.0, p_tail=1.0, tail_multiplier=3.0)
    # With p_tail=1.0, tail should always trigger
    for _ in range(100):
        latency = model.sample_ms()
        assert latency == 60  # 20 * 3

def test_tail_latency_never_triggered():
    model = LatencyModel(base_ms=20.0, jitter_ms=0.0, p_tail=0.0, tail_multiplier=3.0)
    for _ in range(100):
        latency = model.sample_ms()
        assert latency == 20  # No tail

def test_latency_never_negative():
    model = LatencyModel(base_ms=5.0, jitter_ms=10.0)
    for _ in range(1000):
        latency = model.sample_ms()
        assert latency >= 0

# ------------------ Statistical Behavior ------------------

def test_tail_probability_effect():
    model_low_tail = LatencyModel(base_ms=20.0, jitter_ms=0.0, p_tail=0.01, tail_multiplier=3.0)
    model_high_tail = LatencyModel(base_ms=20.0, jitter_ms=0.0, p_tail=0.5, tail_multiplier=3.0)

    low_tail_count = sum(1 for _ in range(1000) if model_low_tail.sample_ms() == 60)
    high_tail_count = sum(1 for _ in range(1000) if model_high_tail.sample_ms() == 60)

    assert low_tail_count < high_tail_count
    assert low_tail_count > 0  # Confirm tail triggers occasionally
