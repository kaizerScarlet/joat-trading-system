from typing import Optional, Dict
from cancel_window.order_age_distribution import OrderAgeDistribution
import time

class OrderAgeDistributionScorer:
    def __init__(self,
                 tracker: OrderAgeDistribution,
                 distribution_tracker: Optional[OrderAgeDistribution] = None,
                 base_score: float = 1.0,
                 short_lived_threshold_ms: int = 200,
                 burst_ratio_threshold: float = 0.7,
                 decay_half_life_ms: int = 1000,
                 enable_volume_weighting: bool = True,
                 enable_side_scoring: bool = True):
        self.tracker = distribution_tracker or tracker
        self.base_score = base_score
        self.short_lived_threshold = short_lived_threshold_ms
        self.burst_ratio_threshold = burst_ratio_threshold
        self.decay_half_life_ms = decay_half_life_ms
        self.enable_volume_weighting = enable_volume_weighting
        self.enable_side_scoring = enable_side_scoring

        self.order_registration_time = {}
        self.min_score_by_side = {'ask': float('inf'), 'bid': float('inf')}
        self.max_score_by_side = {'ask': float('-inf'), 'bid': float('-inf')}

    def register_events(self, orderid, timestamp, event_type, price, size, distance_from_best, side='ask'):
        if orderid not in self.order_registration_time:
            self.order_registration_time[orderid] = timestamp

        # ✅ Only register if it's a new order (not a fill or cancel)
        if event_type not in ['TRUE_FILL', 'PARTIAL_FILL', 'LAYER_TRUE_FILL', 'LADDER_TRUE_FILL',
                            'CANCEL_SPOOF', 'BURST_CANCEL', 'PING_CANCEL', 'LAYER_CANCEL_ONLY',
                            'LADDER_CANCEL_ONLY', 'MULTILEVEL_LADDERING']:
            self.tracker.register_event(orderid, timestamp, price, size, side)

        if event_type in ['TRUE_FILL', 'PARTIAL_FILL', 'LAYER_TRUE_FILL', 'LADDER_TRUE_FILL']:
            self.fill_order(orderid, timestamp, event_type, price, size, distance_from_best, side)
        elif event_type in ['CANCEL_SPOOF', 'BURST_CANCEL', 'PING_CANCEL', 'LAYER_CANCEL_ONLY',
                        'LADDER_CANCEL_ONLY', 'MULTILEVEL_LADDERING']:
            self.cancel_order(orderid, timestamp, event_type, price, size, distance_from_best, side)


    def cancel_order(self, orderid, timestamp, event_type, price, size, distance_from_best, side):
        self.tracker.cancel_order(orderid, timestamp, event_type, price, size, distance_from_best, side)

    def fill_order(self, orderid, timestamp, event_type, price, size, distance_from_best, side):
        self.tracker.fill_order(orderid, timestamp, event_type, price, size, distance_from_best, side)

    def compute_score(self) -> Dict[str, float]:
        current_time = int(time.time() * 1000)
        scores = {}

        for s in ['ask', 'bid']:
            recent_orders = [o for o in self.tracker.cancelled_orders + self.tracker.filled_orders if o['side'] == s]
            short_lived_contributions = []

            for o in recent_orders:
                placed_ts = self.order_registration_time.get(o['orderid'], o['timestamp'])
                age = o.get('age', max(0, o['timestamp'] - placed_ts))


                if age <= self.short_lived_threshold:
                    decay = 0.5 ** (age / float(self.decay_half_life_ms))
                    weight = o.get('size', 1.0) if self.enable_volume_weighting else 1.0
                    short_lived_contributions.append(weight * decay)

            if short_lived_contributions:
                short_score_sum = sum(short_lived_contributions)
                total_score_sum = sum(o.get('size', 1.0) for o in recent_orders) if self.enable_volume_weighting else len(recent_orders)
                burst_ratio = short_score_sum / max(total_score_sum, 1e-6)

                raw_score = self.base_score * (1.0 + burst_ratio) if burst_ratio >= self.burst_ratio_threshold else self.base_score * burst_ratio * 0.5
            else:
                raw_score = 0.0

            # Initialize min/max if first observation
            if self.min_score_by_side[s] == float('inf'):
                self.min_score_by_side[s] = raw_score
            if self.max_score_by_side[s] == float('-inf'):
                self.max_score_by_side[s] = raw_score

            # Update min/max
            self.min_score_by_side[s] = min(self.min_score_by_side[s], raw_score)
            self.max_score_by_side[s] = max(self.max_score_by_side[s], raw_score)

            # Normalize
            if self.min_score_by_side[s] == self.max_score_by_side[s]:
                scores[s] = raw_score  # First score, no history
            else:
                score_range = self.max_score_by_side[s] - self.min_score_by_side[s]
                norm_score = 0.5 + 0.5 * ((raw_score - self.min_score_by_side[s]) / score_range)
                scores[s] = max(0.0, min(1.0, norm_score))


        return scores if self.enable_side_scoring else {'combined': sum(scores.values()) / 2}
    

    def get_debug_view(self) -> Dict[str, Dict]:
        """
        Returns a diagnostic snapshot of internal state for introspection and behavioral analysis.
        Includes score bounds, order registration, recent fills/cancels, and normalized scores.
        """
        recent_orders = self.tracker.cancelled_orders + self.tracker.filled_orders
        latest_ts = max((o['timestamp'] for o in recent_orders), default=0)

        return {
            'base_score': self.base_score,
            'short_lived_threshold_ms': self.short_lived_threshold,
            'burst_ratio_threshold': self.burst_ratio_threshold,
            'decay_half_life_ms': self.decay_half_life_ms,
            'volume_weighting': self.enable_volume_weighting,
            'side_scoring': self.enable_side_scoring,
            'score_bounds': {
                'min': self.min_score_by_side,
                'max': self.max_score_by_side
            },
            'registered_orders': self.order_registration_time,
            'recent_events': {
                'cancelled': self.tracker.cancelled_orders,
                'filled': self.tracker.filled_orders
            },
            'normalized_scores': {
                'ask': self.compute_score()['ask'],
                'bid': self.compute_score()['bid']
            }
        }

    def reset(self):
        self.tracker.reset()
        self.order_registration_time.clear()
        self.min_score_by_side = {'ask': float('inf'), 'bid': float('inf')}
        self.max_score_by_side = {'ask': float('-inf'), 'bid': float('-inf')}
