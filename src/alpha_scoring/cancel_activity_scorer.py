from typing import Dict, List


class CancelActivityScorer:
    """
    Analyzes cancel patterns in a given time window and assigns an alpha score.
    Designed to detect aggressive canceling behaviour (spoofing-like).
    """

    def __init__(self, window_ms: int =  1000, reference_size: float = 5.0, tick_penality: float = 0.1):
        """
        :param window_ms: Time window in milliseconds to consider recent activity
        :param reference_size:
        :param tick_penalty:
        """
        self.window_ms = window_ms
        self.reference_size = reference_size
        self.tick_penalty = tick_penality
        self.order_events: List[Dict] =[]

        #Use Exponential Moving Average(EMA) to dampen alpha volatility
        self.alpha_ema = None
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

    def register_events(self, timestamp: int, event_type: str, size: float, distance_from_best: int):
        """
        Register an order-related event

        :param timestamp: Time of event in ms
        :param event_type: One of 'TRUE_FILL', "CANCEL_SPOOF', 'PARTIAL_FILL', 'ICEBERG_CANCEL'
        :param size: Size of order
        :param distance_from_best: Number of ticks away from best  bid/ask
        """

        self.order_events.append({
            'timestamp': timestamp,
            'type': event_type,
            'size': size,
            'distance': distance_from_best,}
        )

    def compute_score(self, current_time: int) -> float:
        window_start = current_time - self.window_ms
        score = 0.0
        event_count = 0

        for event in self.order_events:
            if event['timestamp'] < window_start:
                continue
            base = self.base_weights.get(event['type'], 0.0)
            size_weight = event['size'] / self.reference_size
            depth_penalty = max(1.0 - event['distance'] * self.tick_penalty, 0.0)

            weighted_score = base * size_weight * depth_penalty
            score += weighted_score
            event_count += 1

        raw_score = score / max(event_count, 1)

        if self.alpha_ema is None:
            self.alpha_ema = raw_score
        
        else:
            self.alpha_ema  = (
                self.ema_decay * raw_score + (1 - self.ema_decay) * self.alpha_ema
            )
        return round(self.alpha_ema, 4)

    def reset(self):
        """Clears all logged events"""
        self.order_events.clear()