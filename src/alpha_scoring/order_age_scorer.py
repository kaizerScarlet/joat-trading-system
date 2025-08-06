from typing import Optional, Dict
from cancel_window.order_age_distribution import OrderAgeDistribution
from collections import defaultdict
import math
import numpy as np
import time


class OrderAgeDistributionScorer:
    def __init__(self, distribution_tracker: Optional[OrderAgeDistribution] = None,
                 base_score: float = 1.0, short_lived_threshold_ms: int = 200,
                 burst_ratio_threshold: float = 0.7,
                 decay_half_life_ms: int = 1000,
                 enable_volume_weighting: bool = True,
                 enable_side_scoring: bool = True,
                 enable_zscore_detection: bool =False,
                 zscore_history_window: int = 20
                 ):
        """
        Scording module for order age distribution dynamics

        :param distribution_tracker:  instance of OrderAgeDistribution (external tracker)
        :param base_score: score multiplier
        :param short_lived_threshold_ms: max age to classify an order as 'short-lived'
        :param burst_ratio_threshold: minimum short/total ratio to trigger score
        :param decay_half_life_ms: Decay factor for older orders
        :param enable_side_scoring: If True, returns per-side scores
        :param enable_volume_weighting: If True, weights by size
        :param enable_zscore_detection: compare burst intensity to historical average
        :param zscore_history_window: Number of windows to keep in z-score baseline
        """

        self.tracker = distribution_tracker or OrderAgeDistribution()
        self.base_score = base_score
        self.short_lived_threshold = short_lived_threshold_ms
        self.burst_ratio_threshold = burst_ratio_threshold
        self.decay_half_life_ms = decay_half_life_ms

        self.enable_side_scoring = enable_side_scoring
        self.enable_volume_weighting = enable_volume_weighting
        self.enable_zscore_detection = enable_zscore_detection
        self.zscore_history_window = zscore_history_window

        self.history_by_side = {'ask': [], 'bid':[]} # For z-score

    def register_events(self, timestamp:int, event_type: str, size: float, distance_from_best: int, side:str='ask'):
        """
        Register all raw order lifecylce time based orders
        """
        if event_type in ['TRUE_FILL', 'PARTIAL_FILL', 'LAYER_TRUE_FILL','LADDER_TRUE_FILL']:
            self.fill_order(timestamp, event_type, size, distance_from_best, side)

        elif event_type in ['CANCEL_SPOOF','BURST_CANCEL', 'PING_CANCEL','LAYER_CANCEL_ONLY', 'LADDER_CANCEL_ONLY','MULTILEVEL_LADDERING']:
            self.cancel_order(timestamp, event_type, size, distance_from_best, side)

        else:
            pass

    def cancel_order(self, timestamp: int, event_type: str, size: float, distance_from_best: int, side: str='ask'):
        self.tracker.cancel_order(timestamp, event_type, size, distance_from_best, side)

    def fill_order(self, timestamp: int, event_type: str, price, size: float, distance_from_best: int, side:str='ask'):
        self.tracker.fill_order(timestamp, event_type, price, size, distance_from_best, side)


    def compute_score(self) -> Dict[str,float]:
        """
        Compute alpha score based on burst of short-lived orders for both ask and bid side (or unified if side score is disabled)

        :return: {'a': score, 'b': score} if enable_side_scoring = True
                {'combine': score} otherwise
        Can handle volume-adjusted, time-decayed, and anomaly-sensitive scoring
        """
        current_time = int(time.time() * 1000)
        scores = {}

        for side in ['ask', 'bid']:
            # Merge Cancelled + filled by side
            recent_orders = [
                o for o in self.tracker.cancelled_orders + self.tracker.filled_orders
                if o.get('side') == side 

            ]

            if not recent_orders:
                scores[side] = 0.0
                continue


            # Identify short-lived orders with optional decay + volume
            short_lived = []
            for o in recent_orders:
                age = o['age']
                if age <= self.short_lived_threshold:
                    #Apply exponential decay
                    decay = 0.5 ** ((current_time - o['timestamp'] / self.decay_half_life_ms))
                    #Size weighting if enabled
                    weight = o.get('size', 1.0) if self.enable_volume_weighting else 1.0
                    adjusted_score = weight * decay 
                    short_lived.append(adjusted_score)
            
            if not short_lived:
                scores[side] = 0.0
                continue

            short_score_sum = sum(short_lived)
            total_score_sum = sum(
                o.get('size', 1.0)
                for o in recent_orders
            )if self.enable_volume_weighting else len(recent_orders)


            burst_ratio = short_score_sum / max(total_score_sum, 1e-6)
            #Optional: Anolmaly detection using z-score
            if self.enable_zscore_detection:
                self.history_by_side[side].append(burst_ratio)
                if len(self.history_by_side[side]) > self.zscore_history_window:
                    self.history_by_side[side] = self.history_by_side[side][-self.zscore_history_window:]
                hist = self.history_by_side['side']
                if len(hist) > 1:
                    z = (burst_ratio - np.mean(hist)) / (np.std(hist) + 1e-6)
                    scores[side] = self.base_score * max(z, 0)
                    continue #Use z-score based score
            
            #Fallback: standard burst ratio logic
            if burst_ratio >= self.burst_ratio_threshold:
                scores[side] = self.base_score * burst_ratio
            else:
                scores[side] = 0.0
        
        # Output foramt
        if self.enable_side_scoring:
            return scores

        else:
            return {'combined': sum(scores.values()) / 2}


    def reset(self):
        """
        Reset the scorer and underlying tracker
        """
        self.tracker.reset()
        self.history_by_side = {'ask': [], 'bid': []}
