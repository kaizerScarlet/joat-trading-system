from typing import Dict, List
import math
from cancel_window.simple_cancel_window_protocol import CancelWindowProtocol


class CancelActivityScorer:
    """
    Analyzes cancel patterns in a given time window and assigns an alpha score.
    Designed to detect aggressive canceling behaviour (spoofing-like) in microstructure
    """

    def __init__(self, window_ms_tuner: CancelWindowProtocol, reference_size: float = 5.0, tick_penality: float = 0.1):
        """
        :param window_ms: Time window in milliseconds to consider recent activity
        :param reference_size: Used to normalize order size
        :param tick_penalty: Reduces weight of orders further from the top of book
        """
        self.window_ms_tuner = window_ms_tuner
        self.window_ms = self.window_ms_tuner.get_window_ms()
        self.reference_size = reference_size
        self.tick_penalty = tick_penality
        self.order_events_by_side: Dict[str, List[Dict]] = {'ask': [], 'bid': []}

        #Use Exponential Moving Average(EMA) to dampen alpha volatility
        self.alpha_ema_by_side = {'ask': None, 'bid': None}
        self.ema_decay = 0.2


        self.base_weights = {
            'TRUE_FILL': -0.25,
            'CANCEL_SPOOF': 1.0,
            'PARTIAL_FILL': -0.5,
            'ICEBERG_CANCEL': 1.5,
            'REPOSTING_BEHAVIOUR': 1.0,
            'BURST_CANCEL': 1.2,
            'LAYER_WIPE' : 1.4,
            'PING_CANCEL': 0.8,
            'HIGH_CANCEL_DENSITY': 1.1,
            'CANCEL_DENSITY_SPIKE': 1.2,
            'FILL_NO_CANCEL_CACHE': 0.3,
            'LADDER_TRUE_FILL': -0.5,
            'LADDER_PARTIAL_FILL': -0.25,
            'LADDER_CANCEL_ONLY': 1.3,
            'MULTILEVEL_LADDERING': 1.0,

        }

        self.min_score_by_side = {'ask': float('inf'), 'bid': float('inf')}
        self.max_score_by_side = {'ask': float('-inf'), 'bid': float('-inf')}

    def register_events(self, timestamp: int, event_type: str, price: float, size: float, side: str, distance_from_best: float):
        """
        Register an order-related event

        :param timestamp: Time of event in ms
        :param event_type: One of 'TRUE_FILL', "CANCEL_SPOOF', 'PARTIAL_FILL', 'ICEBERG_CANCEL'
        :param size: Size of order
        :param distance_from_best: Number of ticks away from best  bid/ask (number of ticks from top of book)
        :param side: 'ask' for ask, 'bid' for bid
        """

        self.order_events_by_side[side].append({
            'timestamp': timestamp,
            'type': event_type,
            'price': price,
            'size': size,
            'distance': distance_from_best,
            })

    def compute_score(self, current_time: int, side: str) -> Dict[str, float]:
        """
         Compute and return alpha score per side based on recent activity.

        :param current_time: current time in ms
        :return: Dict like {'ask': score_a, 'bid': score_b}
        """
        scores = {}

        for side in ['ask', 'bid']:
            events = self.order_events_by_side[side]
            window_start = current_time - self.window_ms

            # prune stale events
            events = [e for e in events if e['timestamp'] >= window_start]
            self.order_events_by_side[side] = events

            score = 0.0
            event_count = 0

            for event in events:
                if event['timestamp'] < window_start:
                    continue
                base = self.base_weights.get(event['type'], 0.0)
                size_weight = event['size'] / math.log1p(self.reference_size) #shrinks abnormally large sizes
                depth_penalty = max(1.0 - event.get('distance', 0) * self.tick_penalty, 0.0)

                weighted_score = base * size_weight * depth_penalty
                score += weighted_score
                event_count += 1

            raw_score = score / max(event_count, 1)

            # --- EMA smoothing ---
            if self.alpha_ema_by_side[side] is None:
                self.alpha_ema_by_side[side] = raw_score
                raw = raw_score
                # initialize min/max properly
                self.min_score_by_side[side] = min(0.0, raw)
                self.max_score_by_side[side] =max(0.0, raw)
            else:
                self.alpha_ema_by_side[side] = (
                    self.ema_decay * raw_score +
                    (1 - self.ema_decay) * self.alpha_ema_by_side[side]
                )
                raw = self.alpha_ema_by_side[side]
                self.min_score_by_side[side] = min(self.min_score_by_side[side], raw)
                self.max_score_by_side[side] = max(self.max_score_by_side[side], raw)

            # --- asymmetric normalization ---
            if raw >= 0:
                # positives map into [0.5, 1.0]
                #denom = max(abs(self.max_score_by_side[side]), 1e-9)
                #scaled = raw / denom
                norm = 0.5 + min(0.5, raw / self.reference_size)
            else:
                # negatives only nudge into [0.5, 0.6]
                #denom = max(abs(self.min_score_by_side[side]), 1e-9)
                #scaled = abs(raw) / denom
                norm = 0.5 + max(-0.1 , raw / (self.reference_size * 2))

            scores[side] = max(0.5, min(1.0, norm))

        return scores
    
    def get_debug_view(self) -> Dict[str, Dict]:
        """
        Returns a detailed snapshot of internal state for diagnostics and introspection.
        Includes event buffers, EMA values, score bounds, and current alpha scores.
        """
        latest_ts = max(
            [e['timestamp'] for side in self.order_events_by_side.values() for e in side],
            default=0
        )


        return {
            'window_ms': self.window_ms,
            'reference_size': self.reference_size,
            'tick_penalty': self.tick_penalty,
            'event_buffers': {
                'ask': self.order_events_by_side['ask'],
                'bid': self.order_events_by_side['bid']
            },
            'ema_scores': {
                'ask': self.alpha_ema_by_side['ask'],
                'bid': self.alpha_ema_by_side['bid']
            },
            'score_bounds': {
                'min': self.min_score_by_side,
                'max': self.max_score_by_side
            },
            'base_weights': self.base_weights,
            'normalized_scores': {
                'ask': self.compute_score(current_time=latest_ts, side='ask')['ask'],
                'bid': self.compute_score(current_time=latest_ts, side='bid')['bid']
            }

        }


    def reset(self):
        """Clears all logged events and resets EMAs"""

        self.order_events_by_side = {'ask': [], 'bid': []}
        self.alpha_ema_by_side = {'ask': None, 'bid': None}