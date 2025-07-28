from typing import List, Dict
from collections import defaultdict 
from cancel_window.order_layering_detection import OrderLayeringDetection

class LayeringScoring:
    def __init__(self, reference_size: float, base_score: float, decay_half_life: int = 500, cluster_window_ms: int = 500,
                 min_orders_in_cluster: int = 3, min_order_density: float = 1.0, max_price_range_bps = 100.0,
                 skew_threshold: float = 1.0, repost_window_ms: int = 500, repost_price_tolerance: float = 1):
        """
        :param reference_size: Normalizing size for order weighting
        :param base_score: Base multiplier per cluster
        :param skew_threshold: side Skew ratio threshold
        :param repost_window_ms: Time window to detect reposting
        :param repost_price_tolerance: Max price difference to consider repost
        """



        self.reference_size = reference_size
        self.base_score = base_score
        self.layering_detector = OrderLayeringDetection()
        self.last_score =  0.0
        self.decay_half_life = decay_half_life
        self.cluster_window_ms = cluster_window_ms
        self.orders = []
        self.cancelled_orders = []

        self.min_orders_in_cluster = min_orders_in_cluster
        self.min_order_density = min_order_density

        self.max_price_range_bps = max_price_range_bps

        self.skew_threshold = skew_threshold
        self.repost_window_ms = repost_window_ms
        self.repost_price_tolerance = repost_price_tolerance


    def register_order(self, timestamp: int, price: float, size: float, side: str):
        #Track new orders and send to detector
        self.layering_detector.register_order(timestamp, price, size, side)
        self.orders.append({
            'timestamp': timestamp,
            'price': price,
            'size': size,
            'side': side,
        })

    def register_cancel(self, timestamp: int, price: float, size: float, side: str):
        #Track Cancelled orders for reposting detection
        self.cancelled_orders.append({
            'timestamp': timestamp,
            'price': price,
            'size': size,
            'side': side,

        })

    def compute_score(self, current_time: int) -> float:
        
        #Step 1: FIlter orders within cluster window
        valid_orders =[
            order for order in self.orders
            if current_time - order['timestamp'] <= self.cluster_window_ms
        ]

        #Step 2: Density Check: Check if the number orders is enough to form a meangingful cluster
        order_count = len(valid_orders)
        if order_count < self.min_orders_in_cluster:
            return 0.0

        #Step 3: Calculate the time duration of the cluster
        cluster_duration = max((current_time - order['timestamp']) for order in valid_orders)
        cluster_duration = max(cluster_duration, 1) #Avoid division by zero

        #Step 4: Calculate the order density (orders per 100ms)
        density_per_100ms = (order_count / cluster_duration) * 100.0

        #Steap 5: if density is low, the cluster is likely not strategic -discard
        if density_per_100ms < self.min_order_density:
            return 0.0

        #Step 6: Fliter Clusters that are too wide in price
        #Rationale: Spoof clusters should be near the book to manipulate perception.
        # We reject clusters with excessive price dispersion (e.g., more than 5 bps)
        prices = [order['price'] for order in valid_orders]
        min_price = min(prices)
        max_price = max(prices)
        mid_price = (min_price + max_price) / 2
        price_range_bps = ((max_price - min_price)/ mid_price) * 10000 # Basis Points

        if price_range_bps > self.max_price_range_bps:
            return 0.0 


        #Step 7: Apply decay and scoring in the valid cluster
        score = 0.0
        for order in valid_orders:
            age = current_time - order['timestamp']
            decay = 0.5 ** (age / self.decay_half_life)
            contribution = self.base_score * (order['size'] / self.reference_size) * decay
            score += contribution

        #Step 8: Side Skew scoring
        side_counts = defaultdict(float)
        for order in valid_orders:
            side_counts[order['side']] += order['size']

        if 'b' in side_counts and 's' in side_counts:
            skew_ratio = max(side_counts['b'], side_counts['s']) / max(side_counts['b'] + side_counts['s'], 1e-6)
            if skew_ratio >= self.base_score:
                score += self.base_score # Reward or flag based on skew

        #Step 9:  Reposting detection
        for new_order in valid_orders:
            for cancel in self.cancelled_orders:
                time_diff = new_order['timestamp'] - cancel['timestamp']
                price_diff = abs(new_order['price'] - cancel['price'])

                if (
                    0 < time_diff  <= self.repost_window_ms
                    and cancel['side'] == new_order['side']
                    and price_diff <= self.repost_price_tolerance
                ): 
                    #Add reposting score bump
                    score += self.base_score * 0.5


        self.last_score = score
        return score
    
    def reset(self):
        self.layering_detector.reset()
        self.last_score = 0.0
        self.orders = []
        self.cancelled_orders = []

