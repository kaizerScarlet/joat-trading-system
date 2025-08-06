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
        self.layering_scorer = LayeringScoring(reference_size=5.0, base_score=1.0 #You can tune these
                                               )
        self.age_scorer = OrderAgeDistributionScorer()

        # AlphaBlender combines signals using specified weights and blending  method per side
        self.blender = AlphaBlender(
            weights = {'cancel_activity': 0.4, 'layering': 0.3, 'order_age': 0.3},
            blending_method = 'weighted average', #Options: 'weighted_average', 'max_score', 'min_score'
            adaptive = True #Enables adaptive reweighting from trade feedback

        )

    def update_market(self, timestamp: int, market_snapshot: Dict[str, Any]) -> None:
        """
        update internal scorers with the latest market snapshot and compute raw signal scores.
        Args:
            timestamp (int): Timestamp in milliseconds.
            market_snapshot (Dict[str, Any]): The current market state (book, trades, etc.).
        """
        
        if 'flag' in market_snapshot:
            for flag in market_snapshot['flag']:
                #Feed cancels flags to CancelActivityScorer
                self.cancel_scorer.register_events(
                    timestamp=flag['timestamp'],
                    event_type=flag['type'],
                    size=flag.get('size', 1.0),
                    distance_from_best=flag.get('distance', 0),
                    side=flag.get('side', 'ask') #Default to 'ask' if missing
                )

                #Feed Ladder and Layering flags to LayeringScoring
                self.layering_scorer.register_events(
                    timestamp=flag['timestamp'],
                    event_type = flag['type'],
                    size = flag.get('size', 1.0),
                    distance_from_best=flag.get('distance', 0),
                    side = flag.get('side', 'ask') #Default to 'ask' if missing
                )

                #Feed All age based flags to OrderAgeDistributionScoring
                self.age_scorer.register_events(
                    timestamp = flag['timestamp'],
                    event_type = flag['type'],
                    size = flag.get('size', 1.0),
                    distance_from_best=flag.get('distance', 0),
                    side = flag.get('side', 'ask')#Default to 'ask' if missing
                )



        #Compute Scores
        cancel_score_by_side = self.cancel_scorer.compute_score(timestamp)  #{'a': ...., 'b': ...}
        layering_score_by_side = self.layering_scorer.compute_score(timestamp)  #{'a': ...., 'b': ...}
        age_score_by_side = self.age_scorer.compute_score()     #{'a': ...., 'b': ...}

        #Update AlphaBlender for each side separately
        for side in ['ask', 'bid']:
            self.blender.update_signals(timestamp, {
                'cancel_activity': cancel_score_by_side.get(side, 0.0),    #side-aware
                'layering': layering_score_by_side.get(side, 0.0),         #side-aware 
                'order_age': age_score_by_side.get(side, 0.0)   #Side-Aware
            }, side=side)


    def get_alpha_signal(self, timestamp: int) -> Dict[str,float]:
        """
        Get the current alpha signal per side.
        Args:
            timestamp (int): Current time in ms (optional for consistency)
        Returns:
            Dict[str, float]: {'ask': score, 'bid': score}
        """
        return self.blender.compute_alpha_score(timestamp)
    

    def trade_feedback(self, signal_dict: Dict[str, float], pnl: float, side: str) -> None:
        """
        Provide trade outcome feedback to allow the blender to adaptively adjust signal weights.

        Args:
            signal_dict (Dict[str, float]): Signal values used for the trade.
            pnl (float): Realized profit or loss for that trade
            side (str): 'ask' or 'bid'
        """
        self.blender.update_trade_feedback(signal_dict, pnl, side=side)

    
    def get_debug(self) -> Dict[str, Any]:
        """
        Retrieve internal diagnostic information from the AlphaBlender

        Returns:
            Dict[str, Any]: Debug data for diagnostics or visualization (weights, raw scores, blended scores)
        """
        return self.blender.get_debug_view()

