"""
Order Age Distribution Module 

Tracks the age of active orders to understand whether orders are passive (long lived) or aggressive(shortlived)
- a feature tied to informed trading or liquidity stress

input:
*Order lifecylce (add, fill, cancel)

Logic:
*For each order, store timestamp_created 
*When the order is cancelled or filled, compute age.
*Use histogram or statiscal summary (e.g mean, std, quantiles)

Output:
*Age Distribution statistics
*Optional: Detection of unusual burst of short-leved orders
"""

from typing import List, Dict

class OrderAgeDistribution:
    def __init(self):
        self.active_orders = {}  # Maps order_id to timestamp_created
        self.cancelled_orders = []  # List of cancelled orders with their ages
        self.filled_orders = []  # List of filled orders with their ages

    def place_order(self, order_id: str, timestamp: int, price: float, size: float, side: str):
        """
        Place a new order and record its creation time.
        :param order_id: Unique identifier for the order
        :param timestamp: Order timestamp in milliseconds
        :param price: Order price
        :param size: Order size
        :param side: 'a' for ask, 'b' for bid
        """
        self.active_orders[order_id] = (timestamp, price, size, side)

    def cancel_order(self, order_id: str, timestamp: int):
        """
        Cancel an order and record its age.
        :param order_id: Unique identifier for the order
        :param timestamp: Cancellation timestamp in milliseconds
        """
        if order_id in self.active_orders:
            entry = self.active_orders.pop(order_id)
            age = timestamp - entry[0]
            self.cancelled_orders.append({
                'order_id': order_id,
                'age': age,
                'timestamp': timestamp
            })

    def fill_order(self, order_id: str, timestamp: int):
        """
        Fill an order and record its age.
        :param order_id: Unique identifier for the order
        :param timestamp: Fill timestamp in milliseconds
        """
        if order_id in self.active_orders:
            entry = self.active_orders.pop(order_id)
            age = timestamp - entry[0]
            self.filled_orders.append({
                'order_id': order_id,
                'age': age,
                'timestamp': timestamp
            })

    def get_statistics(self) -> Dict[str, float]:
        """
        Compute statistics on the ages of cancelled and filled orders.
        :return: Dictionary with mean, std, and quantiles of order ages
        """
        from numpy import mean, std, quantile

        cancelled_ages = [order['age'] for order in self.cancelled_orders]
        filled_ages = [order['age'] for order in self.filled_orders]

        stats = {
            'cancelled_mean': mean(cancelled_ages) if cancelled_ages else 0,
            'cancelled_std': std(cancelled_ages) if cancelled_ages else 0,
            'cancelled_quantiles': quantile(cancelled_ages, [0.25, 0.5, 0.75]) if cancelled_ages else [],
            'filled_mean': mean(filled_ages) if filled_ages else 0,
            'filled_std': std(filled_ages) if filled_ages else 0,
            'filled_quantiles': quantile(filled_ages, [0.25, 0.5, 0.75]) if filled_ages else []
        }

        return stats
    

    def reset(self):
        """
        Reset the order age distribution tracker.
        """
        self.active_orders = {}
        self.cancelled_orders = []
        self.filled_orders = []
     
     