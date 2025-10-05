import pytest
import time
from cancel_window.order_layering_detection_protocol import OrderLayeringDetectionProtocol
from cancel_window.order_layering_detection import OrderLayeringDetection

def test_minimal_layering_detected():
    detector : OrderLayeringDetectionProtocol = OrderLayeringDetection(
        price_tick=0.1,
        cluster_depth=2,
        min_orders = 2,
        min_size_per_order=0.0
    )
    now = int(time.time() * 1000)
    detector.tuner.max_ms = 1000 # ✅ override default max
    detector.tuner.min_ms = 1000
    detector.tuner.update(1000)  # ✅ override default window
    detector.register_order(orderid='o1', timestamp = now,price=100.0, size= 5, side = 'ask')
    detector.register_order(orderid='o2', timestamp = now + 100,price=100.1, size= 5, side = 'ask')
    detector.register_order(orderid='o3', timestamp= now + 200,price = 100.2, size = 5, side= 'ask')
    clusters = detector.detect_layering()
    assert len(clusters) == 1
    assert clusters[0]['side'] == 'ask'
    assert clusters[0]['cluster_size'] == 3

def test_layering_with_cancels_and_fills():
    detector : OrderLayeringDetectionProtocol = OrderLayeringDetection(price_tick=0.1,
        cluster_depth=2,
        min_orders = 2,
        min_size_per_order=0.0
        )
    now = int(time.time() * 1000)
    detector.tuner.update(1000)  # ✅ override default window
    detector.register_order('o1', now, 100.0, 5, 'ask')
    detector.register_order('o2', now + 20, 100.1, 5, 'ask')
    detector.register_order('o3', now + 40, 100.2, 5, 'ask')
    detector.register_cancel('o1', now + 60, 'CANCEL_SPOOF', 100.0, 5, 'ask')
    detector.register_fill('o2', now + 80, 'TRUE_FILL', 100.1, 5, 'ask')

    clusters = detector.detect_layering()
    assert len(clusters) == 1
    assert clusters[0]['label'] in ['LAYER_TRUE_FILL', 'LAYER_PARTIAL_FILL']
    assert clusters[0]['cluster_size'] == 3

def test_no_layering_due_to_price_gap():
    detector : OrderLayeringDetectionProtocol = OrderLayeringDetection(  price_tick=0.1,
        cluster_depth=2,
        min_orders = 2,
        min_size_per_order=0.0
        )
    now = int(time.time() * 1000)
    detector.register_order('o1', now, 100.0, 5, 'ask')
    detector.register_order('o2', now + 20, 100.5, 5, 'ask')
    detector.register_order('o3', now + 40, 101.0, 5, 'ask')

    clusters = detector.detect_layering()
    assert len(clusters) == 0

def test_no_layering_due_to_time_gap():
    detector : OrderLayeringDetectionProtocol = OrderLayeringDetection(
          price_tick=0.1,
        cluster_depth=2,
        min_orders = 2,
        min_size_per_order=0.0,
        retention_ms=100)
    now = int(time.time() * 1000)
    detector.register_order('o1', now, 100.0, 5, 'ask')
    detector.register_order('o2', now + 200, 100.1, 5, 'ask')
    detector.register_order('o3', now + 400, 100.2, 5, 'ask')

    clusters = detector.detect_layering()
    assert len(clusters) == 0

def test_layering_filtered_by_size():
    now =int(time.time() * 1000)
    detector : OrderLayeringDetectionProtocol = OrderLayeringDetection(min_size_per_order=5.0)
    detector.register_order('o1', now, 100.0, 1.0, 'ask')
    detector.register_order('o2', now + 10, 100.1, 1.0, 'ask')
    detector.register_order('o3', now + 20, 100.2, 1.0, 'ask')

    clusters = detector.detect_layering()
    assert len(clusters) == 0

def test_layering_detected_on_bid_side():
    detector : OrderLayeringDetectionProtocol = OrderLayeringDetection()
    now = int(time.time() * 1000)
    detector.register_order('o1', now, 99.9, 5, 'bid')
    detector.register_order('o2', now + 10, 99.8, 5, 'bid')
    detector.register_order('o3', now + 20, 99.7, 5, 'bid')
    detector.register_cancel('o1', now + 30, 'CANCEL_SPOOF', 99.9, 5, 'bid')

    clusters = detector.detect_layering()
    assert len(clusters) == 1
    assert clusters[0]['side'] == 'bid'
    assert clusters[0]['label'] == 'LAYER_CANCEL_ONLY'

def test_overlapping_clusters_are_not_double_counted():
    detector : OrderLayeringDetectionProtocol = OrderLayeringDetection()
    now = int(time.time() * 1000)
    detector.register_order('o1', now, 100.0, 5, 'ask')
    detector.register_order('o2', now + 10, 100.01, 5, 'ask')
    detector.register_order('o3', now + 20, 100.02, 5, 'ask')
    detector.register_order('o4', now + 30, 100.03, 5, 'ask')
    detector.register_order('o5', now + 40, 100.04, 5, 'ask')

    clusters = detector.detect_layering()
    assert len(clusters) == 1  # Should not double-count overlapping orders

def test_reset_clears_all_logs():
    detector : OrderLayeringDetectionProtocol = OrderLayeringDetection()
    now = int(time.time() * 1000)
    detector.register_order('o1', now, 100.0, 5, 'ask')
    detector.register_cancel('o1', now + 50, 'CANCEL_SPOOF', 100.0, 5, 'ask')
    assert len(detector.orders_log) == 1
    detector.reset()
    assert len(detector.orders_log) == 0
    assert len(detector.cancel_log) == 0
    assert len(detector.fills_log) == 0


def test_layering_all_filled_cluster_labeled_correctly():
    detector: OrderLayeringDetectionProtocol = OrderLayeringDetection()
    now = int(time.time() * 1000)
    detector.register_order('o1', now, 100.0, 5, 'ask')
    detector.register_order('o2', now + 10, 100.1, 5, 'ask')
    detector.register_order('o3', now + 20, 100.2, 5, 'ask')
    detector.register_fill('o1', now + 30, 'TRUE_FILL', 100.0, 5, 'ask')
    detector.register_fill('o2', now + 40, 'TRUE_FILL', 100.1, 5, 'ask')
    detector.register_fill('o3', now + 50, 'TRUE_FILL', 100.2, 5, 'ask')
    clusters = detector.detect_layering()
    assert clusters[0]['label'] == 'LAYER_TRUE_FILL'

def test_layering_score_reflects_aggression_and_recency():
    detector: OrderLayeringDetectionProtocol = OrderLayeringDetection(
        price_tick=0.1,
        cluster_depth=2,
        min_orders=3,
        min_size_per_order=0.0
    )
    now = int(time.time() * 1000)
    detector.tuner.update(1000)

    # Register 3 adjacent orders within time window
    detector.register_order('o1', now, 100.0, 50, 'ask')
    detector.register_order('o2', now + 50, 100.1, 50, 'ask')
    detector.register_order('o3', now + 100, 100.2, 50, 'ask')

    # Cancel one to trigger aggression
    detector.register_cancel('o1', now + 150, 'CANCEL_SPOOF', 100.0, 50, 'ask')

    score = detector.get_layering_score()
    assert 0.0 < score <= 1.0

