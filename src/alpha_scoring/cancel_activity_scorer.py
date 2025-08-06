from typing import Dict, List


class CancelActivityScorer:
    """
    Analyzes cancel patterns in a given time window and assigns an alpha score.
    Designed to detect aggressive canceling behaviour (spoofing-like) in microstructure
    """

    def __init__(self, window_ms: int =  1000, reference_size: float = 5.0, tick_penality: float = 0.1):
        """
        :param window_ms: Time window in milliseconds to consider recent activity
        :param reference_size: Used to normalize order size
        :param tick_penalty: Reduces weight of orders further from the top of book
        """
        self.window_ms = window_ms
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

    def register_events(self, timestamp: int, event_type: str, price: float, size: float, distance_from_best: int, side: str = 'ask'):
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

    def compute_score(self, current_time: int) -> Dict[str, float]:
        """
        Compute and return alpha score per side based on recent activity.

        :param current_time: current time in ms
        :return: Dict like {'ask': score_a, 'bid': score_b}
        """
        scores = {}

        for side in ['ask', 'bid']:
            events = self.order_events_by_side[side]    
            window_start = current_time - self.window_ms

            #Prune Stale events
            events = [e for e in events if e['timestamp'] >= window_start]
            self.order_events_by_side[side] = events

            score = 0.0
            event_count = 0

            for event in events:
                if event['timestamp'] < window_start:
                    continue
                base = self.base_weights.get(event['type'], 0.0)
                size_weight = event['size'] / self.reference_size
                depth_penalty = max(1.0 - event['distance'] * self.tick_penalty, 0.0)

                weighted_score = base * size_weight * depth_penalty
                score += weighted_score
                event_count += 1

            raw_score = score / max(event_count, 1)

            if self.alpha_ema_by_side[side] is None:
                self.alpha_ema_by_side[side] = raw_score
        
            else:
                self.alpha_ema_by_side[side]  = (
                    self.ema_decay * raw_score + (1 - self.ema_decay) * self.alpha_ema_by_side[side]
            )
                
            scores[side] = round(self.alpha_ema_by_side[side], 4)
        return scores

    def reset(self):
        """Clears all logged events and resets EMAs"""

        self.order_events_by_side = {'ask': [], 'bid': []}
        self.alpha_ema_by_side = {'ask': None, 'bid': None}