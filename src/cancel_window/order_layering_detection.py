"""Order layering Dection module
Detects the strategtic placemeent of multiple orders at different price levels(typically on one side of the book) meant to 
manipulate preice perception.

Inputs:

* Stream of limit_orders (price, size, side, timestamp)
*Configurable layering_distance_threshold and min_layers

Logic:
*Group Orders by side
* Check for multiple levels within a certain price spread
* Check temporal proximit or burst patterns

Output:
*List of detected layering patterns
*Optional: flag aggressive layering activity

Purpose: Detects spoofing patterns based on clustered orders layered near the top of the book

Detection Signals:
*Multiple large orders placed at adjacent price levels 
*On the same side(ask or bid)
*Placed within a short time window.
*Quickly canceled before execution
"""

from collections import defaultdict
from typing import List, Dict, Any 
import time
from cancel_window.simple_cancel_window import CancelWindowTuner
from cancel_window.simple_cancel_window import AdaptiveDensityWindow
from cancel_window.simple_cancel_window import AdaptiveThreshold

class OrderLayeringDetection:
    def __init__(self, price_tick: float = 0.1, cluster_depth = 3, min_orders =3):
        """
        :param time_window_ms: Time window to consider for clustering orders
        :param price_tick: Minimum price difference to consider as a separate level
        :param cluster_depth: Number of levels to consider for layering detection
        :param min_orders: Minimum number of orders at each level to qualify as layering
        """
        self.tuner = CancelWindowTuner()
        self.price_tick = price_tick
        self.cluster_depth = cluster_depth
        self.min_orders = min_orders
        self.cancel_window_ms = self.tuner.current_window_ms()


        self.orders_log = []  #All order placements
        self.cancel_log = [] #Cancels matching placed orders
        self.fills_log = [] #Optional: fills for evalution


    def register_order(self, timestamp: int,event_type:str, price: float, size: float, side: str):
        """
        Register a new order in the system.
        :param timestamp: Order timestamp in milliseconds
        :param price: Order price
        :param size: Order size
        :param side: 'a' for ask, 'b' for bid
        """
        self.orders_log.append({
            'timestamp': timestamp,
            'event_type': event_type,
            'price': price,
            'size': size,
            'side': side,
            'status': 'active'  # initially active
        })

    def register_cancel(self, timestamp: int, event_type:str, price: float, size: float, side: str):
        self.cancel_log.append({
            'timestamp': timestamp,
            'event_type': event_type,
            'price': price,
            'size': size,
            'side': side,
        })

        # Mark Matching order as canceled
        for order in reversed(self.orders_log): # Search from latest
            if order['price'] == price and order['side'] == side and order['status'] == 'active':
                order['cancel_time'] = timestamp
                order['status'] = 'canceled'
                break

    def register_fill(self, timestamp: int, event_type: str, price: float,size: float, side: str):
        self.fills_log.append({
            'timestamp': timestamp,
            'event_type': event_type,
            'price': price,
            'size': size,
            'side': side,

        })

        for order in reversed(self.orders_log):
            if order['price'] == price and order['side'] == side and order['status'] == 'active':
                order['fill_time'] = timestamp 
                order['status'] = 'filled'
                break

    def detect_layering(self) -> List[Dict[str, Any]]:
        """
        Detect potential layering patterns in the order log.
        :return: List of detected layering clusters with spoofing characteristics
        """
        suspicious_clusters = []
        current_time = int(time.time() * 1000)

        # Group orders into clusters by side and time_window
        orders_by_side = defaultdict(list)
        for order in self.orders_log:
            orders_by_side[order['side']].append(order)

        for side, orders in orders_by_side.items():
            # Sort orders by price and then by timestamp
            orders.sort(key=lambda x: (x['price'], x['timestamp']))
            for i in range(len(orders)):
                cluster = [orders[i]]
                for j in range(i + 1, len(orders)):
                    if (orders[j]['timestamp'] - orders[i]['timestamp'] > self.cancel_window_ms):
                        break
                    if abs(orders[j]['price'] - orders[i]['price']) <= self.price_tick * self.cluster_depth:
                        cluster.append(orders[j])

                if len(cluster) >= self.min_orders:
                    status_types = {o['status'] for o in cluster}

                    if 'canceled' in status_types and 'filled' not in status_types:
                        label = 'LAYER_CANCEL_ONLY'
                    elif 'filled' in status_types:
                        filled_ratio = sum(1 for o in cluster if o['status'] == 'filled') / len(cluster)
                        label = 'LAYER_TRUE_FILL' if filled_ratio > 0.5 else 'LAYER_PARTIAL_FILL'
                    else:
                        label = 'LAYER_UNKNOWN'

                    suspicious_clusters.append({
                        'timestamp': orders[i]['timestamp'],
                        'side': side,
                        'cluster_size': len(cluster),
                        'label': label,
                        'depth_range': [min(o['price'] for o in cluster), max(o['price'] for o in cluster)],
                        'durations': [o.get('cancel_time', current_time) - o['timestamp'] for o in cluster if o['status'] == 'canceled']

                    })
       


        return suspicious_clusters
    

    def reset(self):
        """
        Reset the order log for a new detection cycle.
        """
        self.orders_log.clear()
        self.cancel_log.clear()
        self.fills_log.clear()
        
