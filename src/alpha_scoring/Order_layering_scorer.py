from typing import List, Dict
from collections import defaultdict 
from cancel_window.order_layering_detection import OrderLayeringDetection

class LayeringScoring:
    def __init__(self, reference_size: float = 5.0, base_score: float = 1.0, decay_half_life: int = 500, cluster_window_ms: int = 500,
                 min_orders_in_cluster: int = 3, min_order_density: float = 1.0, max_price_range_bps = 100.0,
                 skew_threshold: float = 1.0, repost_window_ms: int = 500, repost_price_tolerance: float = 1):
        """
        Scoring module for order layering behaviour.

        :param reference_size: Normalizing size for order weighting
        :param base_score: Base multiplier per cluster
        :param skew_threshold: side Skew ratio threshold
        :param repost_window_ms: Time window to detect reposting
        :param repost_price_tolerance: Max price difference to consider repost


        :returns:
            per-side scores based on suspicious clustering, cancellation/fill ratio,
            volume skew, and decay-adjusted weighting
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

        self.last_score_by_side = {'ask': 0.0, 'bid': 0.0}
        self.last_time = None

    def register_events(self, timestamp: int, event_type: str, price: float, size: float,distance_from_best:int, side: str):
        """
        Unified event ingestion for layering-related flags.
        Automatically dispatches based  on event type
        """
        if event_type in ['LAYER_CANCEL_ONLY', 'LADDER_CANCEL_ONLY', 'LAYER_WIPE', 'MULTILEVEL_LADDERING']:
            self.register_cancel(timestamp,event_type, price, size, distance_from_best, side)

        elif event_type in ['LAYER_TRUE_FILL', 'LAYER_PARTIAL_FILL', 'LADDER_TRUE_FILL', 'LADDER_PARTIAL_FILL']:
            self.register_fill(timestamp,event_type, price, size, distance_from_best, side)
        
        else:
            #For now Layering will be scored with Laddering, but phase 2 we need to develop separate scorers
            pass

    def register_cancel(self, timestamp: int,event_type: str, price: float, size: float,distance_from_best:int, side: str):
        #Track Cancelled Orders for reposting detection
        """
        Track LAYERING and LADDERING CANCEL and WIPE ORDERS
        """
        self.layering_detector.register_cancel(timestamp, event_type, price, size, distance_from_best, side)
        self.recent_cancels.append({
            'timestamp': timestamp,
            'event_type': event_type,
            'price': price,
            'size': size,
            'distance_from_best': distance_from_best,
            'side': side,
        })

    def register_fill(self, timestamp: int,event_type: str, price: float, size: float,distance_from_best: int, side: str):
        #Track filled orders
        """
        Track LAYERING and LADDERING  TRUE and PARTIAL FILLS
        """
        self.layering_detector.register_fill(timestamp, event_type, price, size, distance_from_best, side)
        self.recent_orders.append({
            'timestamp': timestamp,
            'event_type': event_type,
            'price': price,
            'size': size,
            'distance_from_best': distance_from_best,
            'side': side
        })

    def compute_score(self, current_time: int) -> Dict[str, float]:
        """
        Compute alpha scores per side based on layering clusters, skew, and decay.
        """
        suspicious_clusters = self.layering_detector.detect_layering()
        score_by_side = {'ask': 0.0, 'bid': 0.0}
        side_volume = defaultdict(float)

        for cluster in suspicious_clusters:
            label = cluster['label']
            orders = cluster['cluster']
            size_factor = sum(o['size'] for o in orders) / self.reference_size
            duration_penalty = 1.0 

            if 'durations' in cluster and cluster['durations']:
                avg_cancel_time = sum(cluster['durations']) / len(cluster['durations'])
                duration_penalty = max(1.0 - (avg_cancel_time / self.decay_half_life), 0.1)

            if label == 'LAYER_CANCEL_ONLY' or 'LADDER_CANCEL_ONLY' or 'LAYER_WIPE' or 'MULTILEVEL_LADDERING':
                base = self.base_score
            elif label == 'LAYER_PARTIAL_FILL' or 'LADDER_PARTIAL_FILL':
                base = self.base_score * 0.5
            elif label == 'LAYER_TRUE_FILL' or 'LADDER_TRUE_FILL':
                base = self.base_score * 0.25 
            else:
                base = 0.0
            
            contribution = base * size_factor * duration_penalty

            #Assign contribution to correct side
            side_in_cluster = {o['side'] for o in orders}
            for side in side_in_cluster:
                score_by_side[side] += contribution
                side_volume[side] += sum(o['size'] for o in orders if o['side'] == side)

        #Skew scoring bonus
        bid_volume = side_volume.get('bid', 0.0)
        ask_volume = side_volume.get('ask', 0.0)
        total_volume = bid_volume + ask_volume

        if total_volume > 0:
            skew_ratio = max(bid_volume, ask_volume) / total_volume
            if skew_ratio >= self.skew_threshold:
                dominant_side = 'bid' if bid_volume > ask_volume else 'ask'
                score_by_side[dominant_side] += self.base_score * 0.5

        #Apply decay to each side
        if self.last_time is None:
            self.last_time = current_time

        decay = 0.5 ** ((current_time - self.last_time)/ self.decay_half_life)

        for side in ['ask', 'bid']:
            score_by_side[side] = score_by_side[side] * decay + self.last_score_by_side[side] * (1 - decay)

        self.last_score_by_side = score_by_side
        self.last_time = current_time
        return score_by_side

    def reset(self):
        self.layering_detector.reset()
        self.last_score_by_side = {'ask': 0.0, 'bid': 0.0}
        self.recent_orders = []
        self.recent_cancels = []
        self.last_time = None

