from typing import Dict, Optional

class AlphaBlender:
    def __init__(self, weights: Dict[str, float],
                 blending_method: str = 'weighted average',
                 adaptive: bool = False):
        """
        :param weights: Initial static weights
        :param blending_method: 'weighted_average', 'min', 'max'
        :param adaptive: If True, enables dynamic weighting based on signal performance
        """
        self.static_weights = weights
        self.blending_method = blending_method
        self.adaptive = adaptive 

        self.latest_signals = {}
        self.signal_performance = {k: {'hits': 0, 'returns': 0.0, 'count': 0} for k in weights}
        self.dynamic_weights = weights.copy()

    def update_signals(self, timestamp: int, signal_scores: Dict[str, float]):
        self.latest_signals = signal_scores

    def compute_alpha_score(self, timestamp: Optional[int] = None) -> float:
        if not self.latest_signals:
            return 0.0
        
        weights = self.dynamic_weights if self.adaptive else self.static_weights

        if self.blending_method == 'weighted_average':
            total_weight = 0.0
            weighted_sum = 0.0
            for signal, score in self.latest_signals.items():
                weight = weights.get(signal, 0.0)
                weighted_sum += score * weight
                total_weight += weight
            return weighted_sum / total_weight if total_weight > 0 else 0.0
        
        elif self.blending_method == 'min':
            return min(self.latest_signals.values())
        
        elif self.blending_method == 'max':
            return max(self.latest_signals.values())
        
        else:
            raise ValueError(f"Unsupported blanding method: {self.blending_method}")
        
    def update_trade_feedback(self, signal_scores: Dict[str, float], pnl: float):
        """
        After a trade completes, call this method to update signal performance.

        :param signal_score: signals used for this trade
        :param pnl: Profit/Loss from trade
        """
        for signal, score in signal_scores.items():
            if signal in self.signal_performance:
                self.signal_performance[signal]['hits'] += int(pnl >0)
                self.signal_performance[signal]['returns'] += pnl
                self.signal_performance[signal]['count'] += 1

        self._recalculate_dynamic_weights()

    def _recalculate_dynamic_weights(self):
        total_return = sum(
            (v['returns'] / v['count']) if v['count'] > 0 else 0.0
            for v in self.signal_performance.values()
        )
        if total_return == 0:
            return #Avoid division by zero
        
        new_weights = {}
        for signal, perf in self.signal_performance.items():
            avg_return = perf['returns'] / perf['count'] if perf['count'] > 0 else 0.0
            new_weights[signal] = max(avg_return / total_return, 0.0)

        #Normalize
        total = sum(new_weights.vlaues())
        self.dynamic_weights = {k: v / total if total > 0 else 0.0 for k, v in new_weights.items()}

    def get_debug_view(self) -> Dict:
        return {
            'method': self.blending_method,
            'adaptive': self.adaptive,
            'weights': self.dynamic_weights if self.adaptive else self.static_weights,
            'signals': self.latest_signals,
            'blended_score': self.compute_alpha_score(),
            'performance': self.signal_performance
        }

    def reset(self):
        self.latest_signals = {}
        self.signal_performance = {k: {'hits': 0, 'returns': 0.0, 'count': 0} for k in self.static_weights}
        self.dynamic_weights = self.static_weights.copy()