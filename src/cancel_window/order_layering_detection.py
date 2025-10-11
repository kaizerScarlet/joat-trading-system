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
from cancel_window.simple_cancel_window import CancelWindowTunerForLayering
from cancel_window.simple_cancel_window import AdaptiveDensityWindow
from cancel_window.simple_cancel_window import AdaptiveThreshold

class OrderLayeringDetection:
    def __init__(self,
                  tuner: CancelWindowTunerForLayering, 
                 price_tick: float = 0.1,
                  cluster_depth: int = 3,
                    min_orders: int =3,
                    retention_ms: int = 300_000,
                    min_size_per_order: float = 0.0,
                   
                    ):
        """
        :param time_window_ms: Time window to consider for clustering orders
        :param price_tick: Minimum price difference to consider as a separate level
        :param cluster_depth: Number of levels to consider for layering detection
        :param min_orders: Minimum number of orders at each level to qualify as layering
        """
        self.tuner = tuner
        self.price_tick = price_tick
        self.cluster_depth = cluster_depth
        self.min_orders = min_orders
        self.retention_ms = retention_ms
        self.min_size_per_order = min_size_per_order



        self.orders_log: List[Dict[str, Any]] = []  #All order placements
        self.cancel_log: List[Dict[str, Any]] = [] #Cancels matching placed orders
        self.fills_log: List[Dict[str, Any]] = [] #Optional: fills for evalution


    def register_order(self, orderid:str, timestamp: int, price: float, size: float, side: str):
        """
        Register a new order in the system.
        :param timestamp: Order timestamp in milliseconds
        :param price: Order price
        :param size: Order size
        :param side: 'a' for ask, 'b' for bid
        """
        self.orders_log.append({
            'orderid': orderid,
            'timestamp': timestamp,
            'price': price,
            'size': size,
            'side': self._normalize_side(side),
            'status': 'active'  # initially active
        })

    def register_cancel(self, orderid: str, timestamp: int, event_type:str, price: float, size: float, side: str):
        """Registers a cancellation event and updates latency tuner."""

        self.cancel_log.append({
            'orderid': orderid,
            'timestamp': timestamp,
            'event_type': event_type,
            'price': price,
            'size': size,
            'side': self._normalize_side(side),
        })

        # Mark Matching order as canceled
        for order in reversed(self.orders_log): # Search from latest
            if order['orderid'] == orderid and order['status'] == 'active':
                latency = timestamp - order['timestamp']
                self.tuner.update(latency)
                order['cancel_time'] = timestamp
                order['status'] = 'canceled'
                break

    def register_fill(self, orderid: str, timestamp: int, event_type: str, price: float,size: float, side: str):
        """Registers a fill event and updates order status."""
        self.fills_log.append({
            'orderid': orderid,
            'timestamp': timestamp,
            'event_type': event_type,
            'price': price,
            'size': size,
            'side': self._normalize_side(side),

        })

        for order in reversed(self.orders_log):
            if order['orderid'] == orderid and order['status'] == 'active':
                order['fill_time'] = timestamp 
                order['status'] = 'filled'
                break

    def detect_layering(self) -> List[Dict[str, Any]]:
        """
        Detect potential layering patterns in the order log.
        :return: List of detected layering clusters with spoofing characteristics
        """
        self._prune()
        

        suspicious_clusters = []
        current_time = int(time.time() * 1000)

        # Group orders into clusters by side and time_window
        orders_by_side = defaultdict(list)
        for order in self.orders_log:
            if order['status'] in ['active', 'canceled', 'filled']:
                orders_by_side[order['side']].append(order)

        for side, orders in orders_by_side.items():
            # Sort orders by price and then by timestamp
            orders.sort(key=lambda x: (x['price'], x['timestamp']))
            used_orders = set()

            for i in range(len(orders)):
                if orders[i]['orderid'] in used_orders:
                    continue

                cluster = [orders[i]]
                price_levels = {orders[i]['price']}
                
                
                for j in range(i + 1, len(orders)):
                    if orders[j]['orderid'] in used_orders:
                        continue
                    

                    time_diff = orders[j]['timestamp'] - orders[i]['timestamp']
                    price_diff = abs(orders[j]['price'] - orders[i]['price'])

             
                
                    if  time_diff > self.tuner.current_window_ms():
                        break

                

                    if price_diff <= (self.price_tick * self.cluster_depth) + 1e-6:
                        cluster.append(orders[j])
                        price_levels.add(orders[j]['price'])
                
 
                if len(cluster) >= self.min_orders and len(price_levels) >= self.cluster_depth:
                    if any(o['size'] < self.min_size_per_order for o in cluster):
                        continue


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
                        'durations': [o.get('cancel_time', current_time) - o['timestamp'] for o in cluster if o['status'] == 'canceled'],
                        'aggression_score': sum(o['size'] for o in cluster) / len(cluster),
                        'orders': cluster,

                    })
                    
                    # Only Mark orders as used after cluster is accepted
                    for o in cluster:
                        used_orders.add(o['orderid'])
       

        return suspicious_clusters
    
    def _prune(self):
        """Hybrid pruning: keep only events within retention window """
        
        current_time = int(time.time() * 1000)
        cutoff = current_time - self.retention_ms

        self.orders_log = [o for o in self.orders_log if o['timestamp'] >= cutoff]
        self.cancel_log = [c for c in self.cancel_log if c['timestamp'] >= cutoff]
        self.fills_log = [f for f in self.fills_log if f['timestamp'] >= cutoff]

    def _normalize_side(self, side: str) -> str:
        """Return normalized side (input: a -> output: ask) or (input: b -> output: bid)"""
        return 'ask' if side in ['a', 'ask'] else 'bid'
    

    def get_layering_score(self) -> float:
        """
        Returns a normalized layering score (0.0 to 1.0) based on recent suspicious clusters.
        Higher score = more aggressive layering activity.
        """
        clusters = self.detect_layering()
        if not clusters:
            return 0.0

        # Weight by aggression and recency
        current_time = int(time.time() * 1000)
        scores = []
        for cluster in clusters:
            age_ms = current_time - cluster['timestamp']
            recency_weight = max(0.0, 1.0 - age_ms / self.retention_ms)
            aggression = cluster.get('aggression_score', 0.0)
            label_weight = 1.0 if cluster['label'] == 'LAYER_CANCEL_ONLY' else 0.5
            scores.append(recency_weight * aggression * label_weight)

        raw_score = sum(scores) / len(scores)
        return min(1.0, raw_score / 100.0)  # Normalize to 0..1



    def reset(self):
        """
        Reset the order log for a new detection cycle.
        """
        self.orders_log.clear()
        self.cancel_log.clear()
        self.fills_log.clear()

    def get_debug_view(self) -> Dict[str, Any]:
        """Returns a snapshot of internal state for debugging and inspection."""
        self._prune()
        clusters = self.detect_layering()
        current_time = int(time.time() * 1000)

        return {
            "active_order_count": sum(1 for o in self.orders_log if o['status'] == 'active'),
            "canceled_order_count": len(self.cancel_log),
            "filled_order_count": len(self.fills_log),
            "recent_clusters": [{
                "timestamp": c["timestamp"],
                "side": c["side"],
                "label": c["label"],
                "cluster_size": c["cluster_size"],
                "aggression_score": c["aggression_score"],
                "depth_range": c["depth_range"],
                "avg_duration": sum(c["durations"]) / len(c["durations"]) if c["durations"] else 0
            } for c in clusters[-3:]],
            "layering_score": self.get_layering_score(),
            "tuner_window_ms": self.tuner.current_window_ms()
        }

        
