import pytest 
from cancel_window.order_age_distribution import OrderAgeDistribution

def test_order_age_distribution():
    tracker = OrderAgeDistribution()

    # Register some active orders
    tracker.register_event('order1', 150, 1000, 5, 'a')
    tracker.register_event('order2', 150, 2000, 10, 'b')

    # Cancel an order
    tracker.cancel_order('order1', 3000)
    assert len(tracker.cancelled_orders) == 1
    assert tracker.cancelled_orders[0]['order_id'] == 'order1'
    assert tracker.cancelled_orders[0]['age'] == 2850

    # Fill an order
    tracker.fill_order('order2', 4000)
    assert len(tracker.filled_orders) == 1
    assert tracker.filled_orders[0]['order_id'] == 'order2'
    assert tracker.filled_orders[0]['age'] == 3850

    # Get statistics
    stats = tracker.get_statistics()
    assert stats['cancelled_mean'] == 2850
    assert stats['filled_mean'] == 3850

    # Reset the tracker
    tracker.reset()
    assert len(tracker.active_orders) == 0