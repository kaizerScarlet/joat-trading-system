from alpha_scoring.cancel_activity_scorer_protocol import CancelActivityScorerProtocol
from alpha_scoring.order_age_distribution_scorer_protocol import OrderAgeDistributionScorerProtocol
from alpha_scoring.Order_layering_scorer_protocol import LayeringScoringProtocol
from alpha_scoring.Alphablender_protocol import AlphaBlenderProtocol

from typing import Dict, Any

class AlphaSignalPipeline:
    """
    Orchestrates signal generation and fusion for alpha decisioning.
    Computes scores from cancel activity, layering, and order age modules,
    then blends them into a unified alpha signal using AlphaBlender.
    Supports adaptive feedback to refine weights based on PnL outcomes.
    """

    def __init__(self,
                  cancel_scorer : CancelActivityScorerProtocol,
                  age_scorer: OrderAgeDistributionScorerProtocol,
                  layering_scorer: LayeringScoringProtocol,
                  blender: AlphaBlenderProtocol, 
                  ):
        self.cancel_scorer = cancel_scorer
        self.layering_scorer = layering_scorer
        self.age_scorer = age_scorer

        self.blender = blender

    def update_market(self, timestamp: int, market_snapshot: Dict[str, Any]) -> None:
        """
        Updates internal scorers with the latest market snapshot and computes raw signal scores.
        """
        flags = market_snapshot.get('flag', [])
        for flag in flags:
            for scorer in [self.cancel_scorer, self.layering_scorer, self.age_scorer]:
                scorer.register_events(
                    timestamp=flag['timestamp'],
                    event_type=flag['type'],
                    price=flag['price'],
                    size=flag.get('size', 1.0),
                    side=flag.get('side', 'ask')
                )

        for side in ['ask', 'bid']:
            cancel_score = self.cancel_scorer.compute_score(timestamp, side)
            layering_score = self.layering_scorer.compute_score(timestamp, side)
            age_score = self.age_scorer.compute_score(side)

            self.blender.update_signals(timestamp, {
                'cancel_activity': cancel_score.get(side, 0.0),
                'layering': layering_score.get(side, 0.0),
                'order_age': age_score.get(side, 0.0)
            }, side=side)

    def get_alpha_signal(self) -> Dict[str, float]:
        """
        Returns the current alpha signal per side.
        """
        return self.blender.compute_alpha_score()

    def trade_feedback(self, signal_dict: Dict[str, float], pnl: float, side: str) -> None:
        """
        Provides trade outcome feedback to adaptively adjust signal weights.
        """
        self.blender.update_trade_feedback(signal_dict, pnl, side=side)

    def get_debug(self) -> Dict[str, Any]:
        """
        Retrieves internal diagnostics from the AlphaBlender.
        """
        return self.blender.get_debug_view()

    def reset(self) -> None:
        """
        Resets all scorers and blender state.
        """
        self.cancel_scorer.reset()
        self.layering_scorer.reset()
        self.age_scorer.reset()
        self.blender.reset()
