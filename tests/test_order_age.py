import pytest 
from unittest.mock import MagicMock
from cancel_window.order_age_distribution import OrderAgeDistribution
from cancel_window.order_age_distribution_protocol import OrderAgeDistributionProtocol

def test_order_age_distribution():
    tracker : OrderAgeDistributionProtocol = OrderAgeDistribution(regime_classifier = MagicMock())

    # Register some active orders
    tracker.register_event(orderid="order_1", timestamp=150, price=1000, size=5, side='a')
    tracker.register_event(orderid="order_2", timestamp=150, price=2000, size=10, side='b')

    # Cancel an order
    tracker.cancel_order(orderid="order_1", timestamp=3000, event_type="CANCEL_SPOOF", price=100.1, size=2.0, distance_from_best=0.2, side="bid")
    assert len(tracker.cancelled_orders) == 1
    assert tracker.cancelled_orders[0]['orderid'] == "order_1"
    assert tracker.cancelled_orders[0]['age'] == 2850

    # Fill an order
    tracker.fill_order(orderid="order_2", timestamp=4000, event_type="TRUE_FILL", price=103.3, size=5.0, distance_from_best=0, side="bid")
    assert len(tracker.filled_orders) == 1
    assert tracker.filled_orders[0]['orderid'] == "order_2"
    assert tracker.filled_orders[0]['age'] == 3850

    # Get statistics
    stats = tracker.get_statistics()
    assert stats['cancelled_mean'] == 2850
    assert stats['filled_mean'] == 3850

    # Reset the tracker
    tracker.reset()
    assert len(tracker.active_orders) == 0




import pytest
from cancel_window.order_age_distribution import OrderAgeDistribution

def test_detect_bursts_flags_short_lived_activity():
    tracker : OrderAgeDistributionProtocol = OrderAgeDistribution(regime_classifier = MagicMock())
    now = 1000

    # Register and cancel short-lived orders
    for i in range(3):
        oid = f"order_{i}"
        tracker.register_event(orderid=oid, timestamp=now + i * 10, price=100.0, size=5.0, side='bid')
        tracker.cancel_order(orderid=oid, timestamp=now + i * 10 + 100, event_type="CANCEL", price=100.0, size=5.0, distance_from_best=0.1, side='bid')

    burst_flags = tracker.detect_bursts(age_threshold_ms=200, burst_window_ms=500)
    assert burst_flags['burst_detected_bid'] is True
    assert burst_flags['burst_detected_ask'] is False

def test_detects_single_short_lived_burst():
    tracker: OrderAgeDistributionProtocol = OrderAgeDistribution(regime_classifier = MagicMock())
    tracker.regime_classifier.get_behavioral_overlay = lambda: "NORMAL"

    now = 1000

    # 4 short-lived orders spaced within 400ms → 1 burst
    for i in range(4):
        ts = now + i * 100
        oid = f"burst_order_{i}"
        tracker.register_event(orderid=oid, timestamp=ts, price=101.0, size=5.0, side='ask')
        tracker.cancel_order(orderid=oid, timestamp=ts + 100, event_type="CANCEL", price=101.0, size=5.0, distance_from_best=0.1, side='ask')

    bursts = tracker.detect_short_lived_bursts(age_threshold_ms=300, cluster_window_ms=500)
    assert bursts['ask'] == 1
    assert bursts.get('bid', 0) == 0

def test_detects_two_separate_short_lived_bursts():
    tracker: OrderAgeDistributionProtocol = OrderAgeDistribution(regime_classifier = MagicMock())
    tracker.regime_classifier.get_behavioral_overlay = lambda: "NORMAL"

    now = 1000

    # Burst 1
    for i in range(3):
        ts = now + i * 100
        oid = f"burst1_order_{i}"
        tracker.register_event(orderid=oid, timestamp=ts, price=101.0, size=5.0, side='ask')
        tracker.cancel_order(orderid=oid, timestamp=ts + 100, event_type="CANCEL", price=101.0, size=5.0, distance_from_best=0.1, side='ask')

    # Burst 2 (spaced 1000ms later)
    for i in range(3):
        ts = now + 1000 + i * 100
        oid = f"burst2_order_{i}"
        tracker.register_event(orderid=oid, timestamp=ts, price=101.0, size=5.0, side='ask')
        tracker.cancel_order(orderid=oid, timestamp=ts + 100, event_type="CANCEL", price=101.0, size=5.0, distance_from_best=0.1, side='ask')

    bursts = tracker.detect_short_lived_bursts(age_threshold_ms=300, cluster_window_ms=500)
    assert bursts['ask'] == 2
    assert bursts.get('bid', 0) == 0


def test_get_order_age_bias_returns_normalized_score():
    tracker : OrderAgeDistributionProtocol = OrderAgeDistribution(regime_classifier = MagicMock())
    now = 1000

    # Aggressive short-lived cancels
    for i in range(3):
        oid = f"order_{i}"
        tracker.register_event(orderid=oid, timestamp=now + i * 10, price=100.0, size=5.0, side='bid')
        tracker.cancel_order(orderid=oid, timestamp=now + i * 10 + 100, event_type="CANCEL", price=100.0, size=5.0, distance_from_best=0.1, side='bid')

    bias = tracker.get_order_age_bias()
    assert bias < 0.0  # Indicates aggressive behavior

def test_get_age_distribution_returns_histogram():
    tracker : OrderAgeDistributionProtocol = OrderAgeDistribution(regime_classifier = MagicMock())
    now = 1000

    # Mixed age orders
    tracker.register_event(orderid="o1", timestamp=now, price=100.0, size=5.0, side='bid')
    tracker.cancel_order(orderid="o1", timestamp=now + 250, event_type="CANCEL", price=100.0, size=5.0, distance_from_best=0.1, side='bid')

    tracker.register_event(orderid="o2", timestamp=now + 500, price=100.0, size=5.0, side='bid')
    tracker.fill_order(orderid="o2", timestamp=now + 1500, event_type="FILL", price=100.0, size=5.0, distance_from_best=0.1, side='bid')

    histogram = tracker.get_age_distribution(bucket_ms=500)
    assert histogram[0] == 1  # First order aged 250ms
    assert histogram[2] == 1  # Second order aged 1000ms

def test_get_recent_short_lived_ratio_computes_correctly():
    tracker : OrderAgeDistributionProtocol = OrderAgeDistribution(regime_classifier = MagicMock())
    now = 1000

    # Short-lived
    tracker.register_event(orderid="o1", timestamp=now, price=100.0, size=5.0, side='bid')
    tracker.cancel_order(orderid="o1", timestamp=now + 200, event_type="CANCEL", price=100.0, size=5.0, distance_from_best=0.1, side='bid')

    # Long-lived
    tracker.register_event(orderid="o2", timestamp=now, price=100.0, size=5.0, side='bid')
    tracker.fill_order(orderid="o2", timestamp=now + 2000, event_type="FILL", price=100.0, size=5.0, distance_from_best=0.1, side='bid')

    ratio = tracker.get_recent_short_lived_ratio(threshold_ms=300, window_ms=3000)
    assert 0.4 < ratio < 0.6  # 1 short-lived out of 2 total


def test_get_debug_view_snapshot():
    tracker: OrderAgeDistributionProtocol = OrderAgeDistribution(regime_classifier = MagicMock())
    now = 1000

    # Register and cancel a few orders
    for i in range(3):
        oid = f"o{i}"
        tracker.register_event(orderid=oid, timestamp=now + i * 100, price=100.0, size=5.0, side='ask')
        tracker.cancel_order(orderid=oid, timestamp=now + i * 100 + 200, event_type="CANCEL", price=100.0, size=5.0, distance_from_best=0.1, side='ask')

    debug = tracker.get_debug_view()
    assert debug['active_order_count'] == 0
    assert debug['cancelled_order_count'] == 3
    assert isinstance(debug['recent_cancel_ages'], list)
    assert 'age_bias' in debug
    assert 'burst_flags' in debug
    assert 'short_lived_ratio' in debug


def test_side_specific_statistics():
    tracker: OrderAgeDistributionProtocol = OrderAgeDistribution(regime_classifier = MagicMock())
    now = 1000

    tracker.register_event(orderid="ask1", timestamp=now, price=100.0, size=5.0, side='ask')
    tracker.cancel_order(orderid="ask1", timestamp=now + 500, event_type="CANCEL", price=100.0, size=5.0, distance_from_best=0.1, side='ask')

    tracker.register_event(orderid="bid1", timestamp=now, price=100.0, size=5.0, side='bid')
    tracker.cancel_order(orderid="bid1", timestamp=now + 1000, event_type="CANCEL", price=100.0, size=5.0, distance_from_best=0.1, side='bid')

    stats = tracker.get_statistics()
    assert stats['cancelled_mean_ask'] == 500
    assert stats['cancelled_mean_bid'] == 1000
