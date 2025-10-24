from typing import List, Dict
from collections import defaultdict 
from cancel_window.order_layering_detection_protocol import OrderLayeringDetectionProtocol

class LayeringScoring:
    def __init__(self,layering_detector: OrderLayeringDetectionProtocol, reference_size: float = 5.0, base_score: float = 1.0, decay_half_life: int = 500, cluster_window_ms: int = 500,
                 min_orders_in_cluster: int = 3, min_order_density: float = 1.0, max_price_range_bps: float= 100.0,
                 skew_threshold: float = 1.0, repost_window_ms: int = 500, repost_price_tolerance: float = 1):
        """
        Initializes the behavioural scoring enigine for layering detection

        Parameters:

        -reference_size: Normalizing factor for order size
        -base_score: Base multiplier for scoring clusters
        -decay_half_life: Time-based decay for behavioural memory
        -cluster_window_ms: Time window for clustering orders
        -skew_threshold: Volume imbalance threshold for side dominance
        -repost_window_ms: Time window to detect reposting behaviour
        -repost_price_tolerance: Price proximity threshold for repost detection


        :returns:
            per-side scores based on suspicious clustering, cancellation/fill ratio,
            volume skew, and decay-adjusted weighting
        """



        self.reference_size = reference_size
        self.base_score = base_score
        self.layering_detector = layering_detector
        self.decay_half_life = decay_half_life
        self.cluster_window_ms = cluster_window_ms

        #Event buffers for behavioral analysis
        self.recent_orders = []
        self.recent_cancels = []

        #Threshold for cluster filtering
        self.min_orders_in_cluster = min_orders_in_cluster
        self.min_order_density = min_order_density
        self.max_price_range_bps = max_price_range_bps

        #Behavioral skew and repost detection
        self.skew_threshold = skew_threshold
        self.repost_window_ms = repost_window_ms
        self.repost_price_tolerance = repost_price_tolerance

        #Score tracking and normalization
        self.last_score_by_side = {'ask': 0.0, 'bid': 0.0}
        self.last_time = None
        self.min_score_by_side = {'ask': float('inf'), 'bid': float('inf')}
        self.max_score_by_side = {'ask': float('-inf'), 'bid': float('-inf')}
        self.score_volatility_by_side = {'ask': 0.0, 'bid': 0.0}
        self.cluster_density_by_side = {'ask': 0, 'bid': 0}
        self.debug = False # Toggle for diagnostic output
    
    @property
    def adaptive_retention_ms(self) -> int:
        """
        Dynamically adjusts retention window based on market tempo.
        faster tempo -> shorter memory, slower tempo -> longer memory
        """
        latency = self.layering_detector.tuner.ema_latency or 300
        return max(5_000, min(int(latency * 10), 300_000))

    def _prune(self, current_time: int):
        """
        Removes stale orders and cancels outside the adaptive rentention window
        Ensures scoring is based on recent behavioral activity
        """
        cutoff = current_time - self.adaptive_retention_ms
        self.recent_orders = [o for o in self.recent_orders if o['timestamp'] >= cutoff]
        self.recent_cancels = [c for c in self.recent_cancels if c['timestamp'] >= cutoff]


    def register_events(self, orderid: str, timestamp: int, event_type: str, price: float, size: float, side: str) -> None:
        """
        Unified event ingestion for layering-related flags.
        Routes fills and cancels to appropriate handlers.
        -param timestamp:
        -param event_type:
        -param price:
        -param size:
        -param side:
        """
        if event_type in ['LAYER_CANCEL_ONLY', 'LADDER_CANCEL_ONLY', 'LAYER_WIPE', 'MULTILEVEL_LADDERING']:
            self.register_cancel(orderid, timestamp,event_type, price, size, side)

        elif event_type in ['LAYER_TRUE_FILL', 'LAYER_PARTIAL_FILL', 'LADDER_TRUE_FILL', 'LADDER_PARTIAL_FILL']:
            self.register_fill(orderid, timestamp,event_type, price, size, side)
        
        else:
            #For now Layering will be scored with Laddering, but phase 2 we need to develop separate scorers
            pass

    def register_cancel(self, orderid: str, timestamp: int,event_type: str, price: float, size: float, side: str) -> None:
        #Track Cancelled Orders for reposting detection and behavioural scoring
        """
        Track LAYERING and LADDERING CANCEL and WIPE ORDERS
        :param timestamp:
        :param event_type:
        :param price:
        :param size:
        :param distance_from_best:
        :pram side:
        """
        self.layering_detector.register_cancel(orderid, timestamp, event_type, price, size, side)
        self.recent_cancels.append({
            'timestamp': timestamp,
            'orderid': orderid,
            'event_type': event_type,
            'price': price,
            'size': size,
            'side': side,
        })

    def register_fill(self,orderid: str, timestamp: int,event_type: str, price: float, size: float, side: str) -> None:
        #Track filled orders for behavioral scoring and repost correlation
        """
        Track LAYERING and LADDERING  TRUE and PARTIAL FILLS
        :param timestamp:
        :param event_type:
        :param price:
        :param size:
        :param distance_from_best:
        :param side:

        :returns: None
        """
        self.layering_detector.register_fill(orderid, timestamp, event_type, price, size, side)
        self.recent_orders.append({
            'timestamp': timestamp,
            'orderid': orderid,
            'event_type': event_type,
            'price': price,
            'size': size,
            'side': side
        })

    def compute_score(self, current_time: int) -> Dict[str, float]:
        """
        Computes normalized behavioural scores per side based on:
        -Cluster aggression
        -Fill behaviour
        -Temporal decay
        -Volume Skew
        -Volatility and density tracking

        :returns:
                Dict[str, float]
        """
        self._prune(current_time)
        suspicious_clusters = self.layering_detector.detect_layering()
        score_by_side = {'ask': 0.0, 'bid': 0.0}
        side_volume = defaultdict(float)
        self.cluster_density_by_side = {'ask': 0, 'bid': 0}


        #Weight mapping for different spoofing behaviours
        label_weights = {
            'LAYER_CANCEL_ONLY': 1.0,
            'LADDER_CANCEL_ONLY': 1.0,
            'LAYER_WIPE': 1.0,
            'MULTILEVEL_LADDERING': 1.0,
            'LAYER_PARTIAL_FILL': 0.5,
            'LADDER_PARTIAL_FILL': 0.5,
            'LAYER_TRUE_FILL': 0.25,
            'LADDER_TRUE_FILL': 0.25
        }

        #Score each cluster based on aggression, fill behaviour, and cancel latency
        for cluster in suspicious_clusters:
            label = cluster['label']
            orders = cluster['cluster']
            size_factor = sum(o['size'] for o in orders) / self.reference_size
            duration_penalty = 1.0 

            if cluster.get('durations'):
                avg_cancel_time = sum(cluster['durations']) / len(cluster['durations'])
                duration_penalty = max(1.0 - (avg_cancel_time / self.decay_half_life), 0.1)

            base =  self.base_score * label_weights.get(label, 0.0)
            contribution = base * size_factor * duration_penalty

            #Assign contribution to correct side and track cluster density
            for s in ['ask', 'bid']:
                if any(o['side'] == s for o in orders):
                    score_by_side[s] += contribution
                    side_volume[s] += sum(o['size'] for o in orders if o['side'] == s)
                    self.cluster_density_by_side[s] += 1

        #Apply Skew scoring bonus if one side dominates volume
        bid_volume = side_volume['bid']
        ask_volume = side_volume['ask']
        total_volume = bid_volume + ask_volume

        if total_volume > 0:
            skew_ratio = max(bid_volume, ask_volume) / total_volume
            if skew_ratio >= self.skew_threshold:
                dominant_side = 'bid' if bid_volume > ask_volume else 'ask'
                score_by_side[dominant_side] += self.base_score * 0.5

        #Apply decay to each side to smooth score transitions over time
        if self.last_time is None:
            self.last_time = current_time

        decay = 0.5 ** ((current_time - self.last_time)/ self.decay_half_life)

        raw_score_by_side = {}
        for s in ['ask', 'bid']:
            raw_score = score_by_side[s]
            decayed_score = raw_score * decay + self.last_score_by_side[s] * (1 - decay)
            raw_score_by_side[s] = decayed_score #Capture raw score before normalization


            #Track min/max and update for normalization
            self.min_score_by_side[s] = min(self.min_score_by_side[s], decayed_score)
            self.max_score_by_side[s] = max(self.max_score_by_side[s], decayed_score)

            #Normalize to 0-1
            if self.max_score_by_side[s] == self.min_score_by_side[s]:
                norm = 0.5
            else:
                norm = (decayed_score - self.min_score_by_side[s]) / \
                        (self.max_score_by_side[s] - self.min_score_by_side[s])
                
            score_by_side[s] = max(0.0, min(1.0, norm))



            # Track volatility (change in score)
            self.score_volatility_by_side[s] = abs(score_by_side[s] - self.last_score_by_side[s])
        

        #Update state for next tick
        self._raw_score_by_side = raw_score_by_side # expose for testing and debugging
        self.last_score_by_side = score_by_side
        self.last_time = current_time

        # Optional debug output
        if self.debug:
            print(f"[DEBUG] Raw Score: {raw_score_by_side} ")
            print(f"[DEBUG] Noramilzed Score: {score_by_side}")
            print(f"[DEBUG] Volatility: {self.score_volatility_by_side}")
            print(f"[DEBUG] Cluster density: {self.cluster_density_by_side}")
            print(f"[DEBUG] Decay factor: {decay}")

        
        return score_by_side
    

    def get_debug_view(self) -> Dict[str, Dict]:
        return {
            'base_score': self.base_score,
            'reference_size': self.reference_size,
            'decay_half_life': self.decay_half_life,
            'cluster_window_ms': self.cluster_window_ms,
            'skew_threshold': self.skew_threshold,
            'repost_window_ms': self.repost_window_ms,
            'repost_price_tolerance': self.repost_price_tolerance,
            'score_bounds': {
                'min': self.min_score_by_side,
                'max': self.max_score_by_side
            },
            'score_volatility': self.score_volatility_by_side,
            'cluster_density': self.cluster_density_by_side,
            'last_score': self.last_score_by_side,
            'recent_orders': self.recent_orders,
            'recent_cancels': self.recent_cancels
        }


    def reset(self):
        """
        Clears all internal state for fresh scoring cycle.
        """
        self.layering_detector.reset()
        self.last_score_by_side = {'ask': 0.0, 'bid': 0.0}
        self.recent_orders = []
        self.recent_cancels = []
        self.last_time = None
        self.score_volatility_by_side= {'ask': 0.0, 'bid':0.0}
        self.cluster_density_by_side = {'ask': 0, 'bid': 0}
