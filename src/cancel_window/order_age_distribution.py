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
    def __init__(self):
        self.active_orders: Dict[str, Dict] = {}  # Maps order_id to timestamp_created
        self.cancelled_orders: List[Dict]    = []  # List of cancelled orders with their ages
        self.filled_orders: List[Dict]  = []  # List of filled orders with their ages
        self.retention_ms = 300_000
        self.max_events = 10_000

    def _prune(self, current_time: int):
        """Hybrid pruning: keep only recent events within retention window + cap max size"""
        cutoff = current_time - self.retention_ms
        self.cancelled_orders = [o for o in self.cancelled_orders if o['timestamp'] >= cutoff][-self.max_events:]
        self.filled_orders = [o for o in self.filled_orders if o['timestamp'] >= cutoff][-self.max_events:]

    
    def register_event(self, orderid:str, timestamp: int, price: float, size: float, side: str)-> None:
        """
        Place a new order and record its creation time.
        :param order_id: Unique identifier for the order
        :param timestamp: Order timestamp in milliseconds
        :param price: Order price
        :param size: Order size
        :param side: 'a' for ask, 'b' for bid

        :return: None
        """

        """Add a new active order"""
        self.active_orders[orderid] = {
            'orderid': orderid,
            'timestamp': timestamp,
            'price': price,
            'size': size,
            'side': side,
        }


    def cancel_order(self, orderid:str, timestamp: int, event_type:str, price: float, size: float,distance_from_best:float, side: str) -> None:
        """
        Cancel an order and record its age and side/price context.
        :param timestamp: Cancellation timestamp in milliseconds
        :param price:
        
        :return : None
        """
        """Mark order as cancelled and compute its age"""
        order = self.active_orders.pop(orderid, None)
        if order:
            age = timestamp - order['timestamp']
            self.cancelled_orders.append({
                'orderid': orderid,
                'timestamp': timestamp,
                'event_type': event_type,
                'price': price,
                'size': size,
                'distance_from_best': distance_from_best,
                'side': side,
                'age': age,
                })
                
       
    
    def fill_order(self,orderid:str, timestamp: int, event_type:str, price: float, size: float,distance_from_best:int, side: str) -> None:
        """
        Fill an order and record its age and side/price context
        :param order_id: Unique identifier for the order
        :param timestamp: Fill timestamp in milliseconds

        :return : None
        """
        """Mark order as filled and compute its age"""
        order = self.active_orders.pop(orderid, None)
        if order:
            age = timestamp - order['timestamp']
            self.filled_orders.append({
                'orderid': orderid,
                'timestamp': timestamp,
                'event_type': event_type,
                'price': price,
                'size': size,
                'distance_from_best': distance_from_best,
                'side': side,
                'age': age
            })

    def detect_bursts(self, age_threshold_ms: int = 200, burst_window_ms: int = 500):
        """
        
        detects bursts of short-lived orders (potential manipulation or stress).
        (
        Binary event flag- quickly tells you if there is a single burst of short lived orders right now, per side. Useful for real-time 
        alerting

        Use this in the Dynamic Risk Engine
        )

        :param age_threshold_ms: Max age for an order to be considered short-lived
        :param burst_window_ms: Time window to look for bursts
        :return: Dict with burst flags per side

        This allows you to flag:
            *Aggressive cancellation waves just before a spoof/fake move
            *Real-time stress signals (liquidity panic, front running)
            *Highly responsive algo tactics (e.g pinging for fills)

        """
        current_time = max([
            *(o['timestamp'] for o in self.cancelled_orders),
            *(o['timestamp'] for o in self.filled_orders) 
        ], default=0)

        self._prune(current_time)

        recent_cancel_burst = [
            o for o in self.cancelled_orders
            if o['age'] <= age_threshold_ms and (current_time - o['timestamp'] <= burst_window_ms)
        ]

        recent_fill_burst = [
            o for o in self.filled_orders
            if o['age'] <= age_threshold_ms and (current_time - o['timestamp'] <= burst_window_ms)
        ]

        burst_by_side = {'ask': 0, 'bid': 0}
        for o in recent_cancel_burst + recent_fill_burst:
            burst_by_side[o['side']] += 1

        return {
            'burst_detected_bid': burst_by_side['bid'] >= 3, #Tweak threshold if needed
            'burst_detected_ask': burst_by_side['ask'] >= 3
        }
    def detect_short_lived_bursts(self, age_threshold_ms: int = 300, cluster_window_ms: int= 500) -> Dict[str, int]:
        """
        Detect bursts of short-lived orders on each side (ask and bid).
        (
            Useful for:
            * alphaScoring modules
            * Volatility-aware fill thresholds
            * Spoof heatmaps or cancel densities
            * Execution deferral heuristics
        )
        :param age_threshold_ms: Max age to be considered short-lived
        :param cluster_window_ms: Time window to count count orders as a burst
        :return: Dict with number of detected bursts per side
        """
        from collections import defaultdict

        current_time = max([
            *(o['timestamp'] for o in self.cancelled_orders),
            *(o['timestamp'] for o in self.filled_orders)
        ], default=0)

        self._prune(current_time)
        
        bursts = defaultdict(int)
        for side in ['ask', 'bid']:
            #Combine filled and cancelled orders on the same side that were short-lived
            short_lived = [
                o for o in self.cancelled_orders + self.filled_orders
                if o.get('side') == side and o['age'] <= age_threshold_ms
            ]

            short_lived.sort(key=lambda o: o['timestamp'])

            #Sliding window to detect bursts
            i = 0
            while i < len(short_lived):
                burst_count = 1
                j = i + 1
                while j < len(short_lived) and (short_lived[j]['timestamp'] - short_lived[i]['timestamp'] <= cluster_window_ms):
                    burst_count += 1
                    j += 1
                if burst_count >= 3:
                    bursts[side] += 1
                    i = j #Skip ahead after a burst
                else:
                    i += 1
        return dict(bursts)


    def get_statistics(self) -> Dict[str, float]:
        """
        Compute statistics on the ages of cancelled and filled orders.
        :return: Dictionary with mean, std, and quantiles of order ages
        """
        from numpy import mean, std, quantile

        current_time = max([
            *(o['timestamp'] for o in self.cancelled_orders),
            *(o['timestamp'] for o in self.filled_orders)
        ], default = 0)

        self._prune(current_time)

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

        #Now add side-specific stats
        for side in ['bid', 'ask']:
            side_cancelled = [o['age'] for o in self.cancelled_orders if o.get('side') == side]
            side_filled = [o['age'] for o in self.filled_orders if o.get('side') == side]

            stats[f'cancelled_mean_{side}'] = mean(side_cancelled) if side_cancelled else 0.0
            stats[f'cancelled_std_{side}'] = std(side_cancelled) if side_cancelled else 0.0
            stats[f'cancelled_quantiles_{side}'] = quantile(side_cancelled, [0.25, 0.5, 0.75]).tolist() if side_cancelled else []

            stats[f'filled_mean_{side}'] = mean(side_filled) if side_filled else 0.0
            stats[f'filled_std_{side}'] = std(side_filled) if side_filled else 0.0
            stats[f'filled_quantiles_{side}'] = quantile(side_filled, [0.25, 0.5, 0.75]).tolist() if side_filled else []

        return stats
    

    def reset(self):
        """
        Reset the order age distribution tracker.
        """
        self.active_orders.clear()
        self.cancelled_orders.clear()
        self.filled_orders.clear()
     
     