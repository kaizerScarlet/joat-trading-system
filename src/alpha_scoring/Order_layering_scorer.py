from typing import List, Dict
from collections import defaultdict 
from cancel_window.order_layering_detection import OrderLayeringDetection

class LayeringScoring:
    def __init__(self, reference_size: float = 5.0, base_score: float = 1.0, decay_half_life: int = 500, cluster_window_ms: int = 500,
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
        self.recent_orders = []
        self.recent_cancels = []

        self.min_orders_in_cluster = min_orders_in_cluster
        self.min_order_density = min_order_density

        self.max_price_range_bps = max_price_range_bps

        self.skew_threshold = skew_threshold
        self.repost_window_ms = repost_window_ms
        self.repost_price_tolerance = repost_price_tolerance


    def register_order(self, timestamp: int, price: float, size: float, side: str):
        #Track new orders and send to detector
        self.layering_detector.register_order(timestamp, price, size, side)
        self.recent_orders.append({
            'timestamp': timestamp,
            'price': price,
            'size': size,
            'side': side,
        })

    def register_cancel(self, timestamp: int, price: float, size: float, side: str):
        #Track Cancelled Orders for reposting detection
        self.layering_detector.register_cancel(timestamp, price, size, side)
        self.recent_cancels({
            'timestamp': timestamp,
            'price': price,
            'size': size,
            'side': side,
        })

    def register_fill(self, timestamp: int, price: float, size: float, side: str):
        #Track filled orders
        self.layering_detector.register_fill(timestamp, price, size, side)

    def compute_score(self, current_time: int) -> float:
        """
        Compute the alpha score based on detected layering clusters and side imbalance.
        """
        suspicious_clusters = self.layering_detector.detect_layering()
        score = 0.0
        side_volume = defaultdict(float)

        for cluster in suspicious_clusters:
            label = cluster['label']
            orders = cluster['cluster']
            size_factor = sum(o['size'] for o in orders) / self.reference_size
            duration_penalty = 1.0 

            if 'durations' in cluster and cluster['durations']:
                avg_cancel_time = sum(cluster['durations']) / len(cluster['durations'])
                duration_penalty = max(1.0 - (avg_cancel_time / self.decay_half_life), 0.1)

            if label == 'LAYER_CANCEL_ONLY':
                contribution = self.base_score * size_factor * duration_penalty
            elif label == 'LAYER_PARTIAL_FILL':
                contribution =  (self.base_score * 0.5) * size_factor
            elif label == 'LAYER_TRUE_FILL':
                contribution = (self.base_score * 0.25) * size_factor 
            else:
                contribution = 0.0
            
            score += contribution

            #Track side volume of skew scoring
            for o in orders:
                side_volume[o['side']] += o['size']

        
        #Skew Ratio scoring
        bid_volume = side_volume.get('b', 0.0)
        ask_volume = side_volume.get('a', 0.0)
        total_volume = bid_volume + ask_volume


        if total_volume > 0:
            skew_ratio = max(bid_volume, ask_volume) / total_volume
            if skew_ratio >= self.skew_threshold:
                score += self.base_score * 0.5 #Bonus Score for strong skew

        
        #Decay old score
        decay = 0.5 ** (current_time - getattr(self, 'last_time', current_time)) /self.decay_half_life
        score = score * decay + self.last_score * (1 - decay)

        self.last_score = score 
        self.last_time =current_time
        return score


    def reset(self):
        self.layering_detector.reset()
        self.last_score = 0.0
        self.orders = []
        self.cancelled_orders = []

