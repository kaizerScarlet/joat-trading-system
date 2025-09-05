import pytest 
from cancel_window.order_age_distribution import OrderAgeDistribution

def test_order_age_distribution():
    tracker = OrderAgeDistribution()

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