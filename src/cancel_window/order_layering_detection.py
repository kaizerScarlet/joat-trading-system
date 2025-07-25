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
from typing import List, Dict

class OrderLayeringDetection:
    def __init__(self, time_window_ms= 500, price_tick: float = 0.1, cluster_depth = 3, min_orders =3):
        """
        :param time_window_ms: Time window to consider for clustering orders
        :param price_tick: Minimum price difference to consider as a separate level
        :param cluster_depth: Number of levels to consider for layering detection
        :param min_orders: Minimum number of orders at each level to qualify as layering
        """
        self.time_window_ms = time_window_ms
        self.price_tick = price_tick
        self.cluster_depth = cluster_depth
        self.min_orders = min_orders
        self.orders_log = [] 


    def register_order(self, timestamp: int, price: float, size: float, side: str):
        """
        Register a new order in the system.
        :param timestamp: Order timestamp in milliseconds
        :param price: Order price
        :param size: Order size
        :param side: 'a' for ask, 'b' for bid
        """
        self.orders_log.append({
            'timestamp': timestamp,
            'price': price,
            'size': size,
            'side': side
        })

    def detect_layering(self) -> List[Dict]:
        """
        Detect potential layering patterns in the order log.
        :return: List of detected layering clusters with spoofing characteristics
        """
        suspicious_clusters = []

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
                    if (orders[j]['timestamp'] - orders[i]['timestamp'] > self.time_window_ms):
                        break
                    if abs(orders[j]['price'] - orders[i]['price']) <= self.price_tick * self.cluster_depth:
                        cluster.append(orders[j])

                if len(cluster) >= self.min_orders:
                    # Check if the cluster has enough depth
                    if len(cluster) >= self.cluster_depth:
                        cluster_info = {
                            'side': side,
                            'cluster': cluster,
                            'timestamp': cluster[0]['timestamp'],
                        }
                        suspicious_clusters.append(cluster_info) 
       


        return suspicious_clusters
    

    def reset(self):
        """
        Reset the order log for a new detection cycle.
        """
        self.orders_log.clear()
        
