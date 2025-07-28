from typing import Optional
from cancel_window.order_age_distribution import OrderAgeDistribution


class OrderAgeDistributionScorer:
    def __init__(self, distribution_tracker: Optional[OrderAgeDistribution] = None,
                 base_score: float = 1.0, short_lived_threshold_ms: int = 200,
                 burst_ratio_threshold: float = 0.7):
        """
        Scording module for order age distribution dynamics

        :param distribution_tracker:  instance of OrderAgeDistribution (external tracker)
        :param base_score: score multiplier
        :param short_lived_threshold_ms: max age to classify an order as 'short-lived'
        :param burst_ratio_threshold: minimum short/total ratio to trigger score
        """

        self.tracker = distribution_tracker or OrderAgeDistribution()
        self.base_score = base_score
        self.short_lived_threshold = short_lived_threshold_ms
        self.burst_ratio_threshold = burst_ratio_threshold

    def compute_score(self) -> float:
        """
        Compute alpha score based on burst of short-lived orders.

        :return: Score between 0 and base_score

        """
        cancelled_ages = [order['age'] for order in self.tracker.cancelled_orders]
        filled_ages = [order['age'] for order in self.tracker.filled_orders]

        all_ages = cancelled_ages + filled_ages

        if not all_ages:
            return 0.0
        
        short_lived_count = sum(1 for age in all_ages if age <= self.short_lived_threshold)
        short_ratio = short_lived_count / len(all_ages)

        if short_ratio >= self.burst_ratio_threshold:
            return self.base_score * short_ratio
        return 0.0