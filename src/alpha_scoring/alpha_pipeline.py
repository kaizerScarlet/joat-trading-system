from alpha_scoring.cancel_activity_scorer import CancelActivityScorer
from alpha_scoring.order_age_scorer import OrderAgeDistributionScorer
from alpha_scoring.Order_layering_scorer import LayeringScoring
from alpha_scoring.AlphaBlender import AlphaBlender

from typing import Dict, Any

class AlphaSignalPipeline:
    """
    AlphaSignalPipeline orchestrates signal generation and fusin for alpha decisioning.
    It computes score from various signal modules(cancel activity, layering, order age),
    and blends them using the AlphaBlender into a unified alpha signal. It also supports
    adapative feedback to refine signal weights over time based on pnl outcomes
    """
    def __init__(self):
        """
        Initializes the AlphaSignalPipeline with all scorers and the AlphaBlender.
        """
        self.cancel_scorer = CancelActivityScorer()
        self.layering_scorer = LayeringScoring()
        self.age_scorer = OrderAgeDistributionScorer()

        # AlphaBlender combines signals using specified weights and blending  method
        self.blender = AlphaBlender(
            weights = {'cancel_activity': 0.4, 'layering': 0.3, 'order_age': 0.3},
            blending_method = 'weighted_average', #Options: 'weighted_average', 'max_score', 'min_score'
            adaptive = True #Enables adaptive reweighting from trade feedback

        )

    def update_market(self, timestamp: int, market_snapshot: Dict[str, Any]) -> None:
        """
        update internal scorers with the latest market snapshot and compute raw signal scores.
        Args:
            timestamp (int): Timestamp in milliseconds.
            market_snapshot (Dict[str, Any]): The current market state (book, trades, etc.).
        """
        cancel_score = self.cancel_scorer.compute_score(market_snapshot)
        layering_score = self.layering_scorer.compute_score(market_snapshot)
        age_score = self.age_scorer.compute_score(market_snapshot)

        # Push scores into blender for this timestamp
        self.blender.update_signals(timestamp, {
            'cancel_activity': cancel_score,
            'layering': layering_score,
            'order_age': age_score
        })


    def get_alpha_signal(self, timestamp: int) -> float:
        """
        Compute and return the blended alpha signal at the given timestamp.
        Args:
            float: 
        """
        return self.blender.compute_alpha_score(timestamp)
    

    def trade_feedback(self, signal_dict, pnl):
        self.blender.update_trade_feedback(signal_dict, pnl)

    
    def get_debug(self):
        return self.blender.get_debug_view()

