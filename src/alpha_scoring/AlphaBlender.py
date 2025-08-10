from typing import Dict, Optional

class AlphaBlender:
    def __init__(self, weights: Dict[str, float],
                 blending_method: str = 'weighted average',
                 adaptive: bool = False):
        """
        :param weights: Initial static weights for each signal
        :param blending_method: 'weighted_average', 'min', 'max'
        :param adaptive: If True, enables feedback-driven dynamic weighting based on signal performance
        """
        self.static_weights = weights
        self.blending_method = blending_method
        self.adaptive = adaptive 

        #Per-side signal buffers
        self.latest_signals_by_side: Dict[str, Dict[str, float]] = {
            'ask': {}, 'bid': {}
        }

        #Adaptive performance tracking
        self.signal_performance_by_side: Dict[str, Dict[str, Dict[str, float]]] = {
            'ask' : {k: {'hits': 0, 'returns': 0.0, 'count': 0} for k in weights},
            'bid' : {k: {'hits': 0, 'returns': 0.0, 'count': 0} for k in weights}
            }
        
        self.dynamic_weights_by_side ={
            'ask': weights.copy(),
            'bid': weights.copy()
        }

    def update_signals(self, timestamp: int, signal_scores: Dict[str, float], side: str = 'bid') -> None:
        """
        Store latest signal values per side.
        Args:
            :param timestamp: int
            :param signal_scores: Dict[str, float]
            :param side: str
        """
        self.latest_signals_by_side[side] = signal_scores

    def compute_alpha_score(self, timestamp: Optional[int] = None) -> Dict[str, float]:
        """
        Compute alpha Score per side using selected blending strategy
        Args:
            :param timestamp: Optional[int]
        :return: Dict[str, float]: {'ask': score, 'bid': score}
        """

        scores = {}

        for side in ['ask', 'bid']:
            signals = self.latest_signals_by_side.get(side, {})
            weights = self.dynamic_weights_by_side[side] if self.adaptive else self.static_weights

            if not signals:
                scores[side] = 0.0
                continue

            if self.blending_method == 'weighted average':
                weighted_sum = sum(signals[s] * weights.get(s, 0.0) for s in signals)
                total_weight = sum(weights.get(s, 0.0) for s in signals)
                scores[side] = weighted_sum / total_weight if total_weight > 0 else 0.0

            elif self.blending_method == 'min':
                scores[side] = min(signals.values())
            
            elif self.blending_method == 'max':
                scores[side] = max(signals.values())
            else:
                raise ValueError(f"Unsupported Blending method: {self.blending_method}")
        return scores
        
    def update_trade_feedback(self, signal_scores: Dict[str, float], pnl: float, side: str='bid'):
        """
        After a trade completes, call this method to update signal performance.

        Args:
            :param signal_score: Dict[str, float] - signals used for this trade Dict
            :param pnl: float - Profit/Loss from trade
        Returns :
            None: Although it does record the performance by sid ()  
        """
        perf = self.signal_performance_by_side[side]

        for signal, score in signal_scores.items():
            if signal in perf:
                perf[signal]['hits'] += int(pnl >0)
                perf[signal]['returns'] += pnl
                perf[signal]['count'] += 1

        self._recalculate_dynamic_weights(side)

    def _recalculate_dynamic_weights(self, side: str):
        """
        Recalculate per-side dynamic weights using average return contribution
        Args:
            :param side:str

            Changes the weight according to profitability
        """
        perf = self.signal_performance_by_side[side]
        total_return = sum(
            (v['returns'] / v['count']) if v['count'] > 0 else 0.0
            for v in perf.values()
        )
        if total_return == 0:
            return #Avoid division by zero
        
        new_weights = {}
        for signal, stats in perf.items():
            avg_return = stats['returns'] / stats['count'] if stats['count'] > 0 else 0.0
            new_weights[signal] = max(avg_return / total_return, 0.0)

        #Normalize weights
        total = sum(new_weights.values())
        self.dynamic_weights_by_side = {
            k: v / total if total > 0 else 0.0 
            for k, v in new_weights.items()
            }

    def get_debug_view(self) -> Dict[str, Dict]:
        """
        Return detailed state per side for introspection
        """
        return {
            'method': self.blending_method,
            'adaptive': self.adaptive,
            'weights': {
                'ask': self.dynamic_weights_by_side['ask'] if self.adaptive else self.static_weights,
                'bid': self.dynamic_weights_by_side['bid'] if self.adaptive else self.static_weights,
                        },
            'signals': self.latest_signals_by_side,
            'blended_score': self.compute_alpha_score(),
            'performance': self.signal_performance_by_side
        }

    def reset(self):
        """
        Reset all stored signal states and performance history.
        """
        self.latest_signals_by_side = {'ask': {}, 'bid': {}}
        self.signal_performance_by_side = {
            'ask': {k: {'hits': 0, 'returns': 0.0, 'count': 0} for k in self.static_weights},
            'bid': {k: {'hits': 0, 'returns': 0.0, 'count': 0} for k in self.static_weights}
            }
        self.dynamic_weights_by_side = {
            'ask': self.static_weights.copy(),
            'bid': self.static_weights.copy()
            }