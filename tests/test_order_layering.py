import pytest 
from cancel_window.order_layering_detection import OrderLayeringDetection


def test_minimal_layering():
    detector = OrderLayeringDetection(time_window_ms=500, price_tick=0.1, cluster_depth=3, min_orders=3)
    detector.register_order(1000, 100.0, 5, 'a')
    detector.register_order(1100, 100.1, 5, 'a')
    detector.register_order(1200, 100.2, 5, 'a')
    clusters = detector.detect_layering()
    assert len(clusters) == 1

def test_order_layering_detection():
    detector = OrderLayeringDetection(time_window_ms=500, price_tick=0.1, cluster_depth=3, min_orders=3)

    # Register some orders
    detector.register_order(1000, 100.0, 5, 'a')  # Ask
    detector.register_order(1020, 100.1, 5, 'a')  # Ask
    detector.register_order(1200, 100.2, 1, 'b')  # Bid
    detector.register_order(1220, 100.2, 0, 'b')  # Cancel bid
    detector.register_order(1400, 100.3, 4, 'a')  # Ask
    detector.register_order(1425, 100.3, 0, 'a')  # Cancel ask

    # Detect layering
    clusters = detector.detect_layering()

    assert len(clusters) == 2
    assert clusters[0]['side'] == 'a'
    assert len(clusters[0]['cluster']) >= 3


def test_no_layering():
    detector = OrderLayeringDetection(time_window_ms=500, price_tick=0.1, cluster_depth=3, min_orders=3)

    # Register some orders that do not form a layering pattern
    detector.register_order(1000, 100.0, 5, 'a')  # Ask
    detector.register_order(1020, 100.5, 5, 'a')  # Ask
    detector.register_order(1200, 100.2, 1, 'b')  # Bid

    # Detect layering
    clusters = detector.detect_layering()

    assert len(clusters) == 0