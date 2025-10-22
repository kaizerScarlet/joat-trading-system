from alpha_scoring.cancel_activity_scorer_protocol import CancelActivityScorerProtocol
from alpha_scoring.cancel_density_scorer import CancelDensityScorer
from alpha_scoring.order_iceberg_scorer import IcebergScorer
from alpha_scoring.order_age_distribution_scorer_protocol import OrderAgeDistributionScorerProtocol
from alpha_scoring.Order_layering_scorer_protocol import LayeringScoringProtocol
from alpha_scoring.order_spoofing_scorer import SpoofingScorer
from alpha_scoring.synthetic_fill_scorer import SyntheticFillScorer
from alpha_scoring.Alphablender_protocol import AlphaBlenderProtocol
from alpha_scoring.order_laddering_scorer_protocol import OrderLadderingScoringProtocol

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
                  cancel_density_scorer: CancelDensityScorer,
                  order_ladder_scorer: OrderLadderingScoringProtocol,
                  age_scorer: OrderAgeDistributionScorerProtocol,
                  iceberg_scorer: IcebergScorer,
                  layering_scorer: LayeringScoringProtocol,
                  order_spoofing_scorer: SpoofingScorer,
                  synthetic_fill_scorer: SyntheticFillScorer,
                  blender: AlphaBlenderProtocol, 
                  ):
        self.cancel_scorer = cancel_scorer
        self.cancel_density_scorer = cancel_density_scorer
        self.layering_scorer = layering_scorer
        self.age_scorer = age_scorer
        self.iceberg_scorer = iceberg_scorer
        self.order_ladder_scorer = order_ladder_scorer
        self.order_spoofing_scorer = order_spoofing_scorer
        self.synthetic_fill_scorer = synthetic_fill_scorer

        self.blender = blender

    def update_market(self, timestamp: int, market_snapshot: Dict[str, Any]) -> None:
        """
        Updates internal scorers with the latest market snapshot and computes raw signal scores.
        """
        flags = market_snapshot.get('flag', [])
        for flag in flags:
            for scorer in [self.cancel_scorer,
                            self.layering_scorer,
                            self.age_scorer,
                            self.iceberg_scorer,
                            self.order_ladder_scorer,
                            self.cancel_density_scorer,
                            self.order_spoofing_scorer,
                            self.synthetic_fill_scorer,
                            ]:
                scorer.register_events(
                    timestamp=flag['timestamp'],
                    event_type=flag['type'],
                    price=flag['price'],
                    size=flag.get('size', 1.0),
                    side=flag.get('side', 'ask')
                )

        for side in ['ask', 'bid']:
            cancel_score = self.cancel_scorer.compute_score(timestamp, side)
            cancel_density_score = self.cancel_density_scorer.compute_score()
            layering_score = self.layering_scorer.compute_score(timestamp, side)
            laddering_score = self.order_ladder_scorer.compute_score()
            age_score = self.age_scorer.compute_score(side)
            iceberg_score = self.iceberg_scorer.compute_score()
            order_spoofing_score = self.order_spoofing_scorer.compute_score()
            synthetic_fill_score = self.synthetic_fill_scorer.compute_score()

            self.blender.update_signals(timestamp, {
                'cancel_activity': cancel_score.get(side, 0.0),
                'layering': layering_score.get(side, 0.0),
                'order_age': age_score.get(side, 0.0),
                'iceberg_score': iceberg_score.get(side, 0.0),
                'cancel_density_score': cancel_density_score.get(side, 0.0),
                'order_laddering_score': laddering_score.get(side, 0.0),
                'order_spoofing_score': order_spoofing_score.get(side, 0.0),
                'synthetic_fill_score': synthetic_fill_score.get(side, 0.0),
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
        self.iceberg_scorer.reset()
        self.order_ladder_scorer.reset()
        self.cancel_density_scorer.reset()
        self.order_spoofing_scorer.reset()
        self.synthetic_fill_scorer.reset()


    def get_raw_scores(self, timestamp: int) -> Dict[str, Dict[str, float]]:
        cancel_density_score = self.cancel_density_scorer.compute_score()
        spoofing_score = self.order_spoofing_scorer.compute_score(timestamp)
        synthetic_score = self.synthetic_fill_scorer.compute_score(timestamp)
        iceberg_score = self.iceberg_scorer.compute_score()
        laddering_score = self.order_ladder_scorer.compute_score()

        return {
            'ask': {
                'cancel_activity': self.cancel_scorer.compute_score(timestamp, 'ask'),
                'cancel_density': cancel_density_score.get('ask', 0.0),
                'layering': self.layering_scorer.compute_score(timestamp, 'ask'),
                'order_age': self.age_scorer.compute_score('ask'),
                'laddering': laddering_score.get('ask', 0.0),
                'spoofing': spoofing_score.get('ask', 0.0),
                'synthetic_fill': synthetic_score.get('ask', 0.0),
                'iceberg': iceberg_score.get('ask', 0.0)
            },
            'bid': {
                'cancel_activity': self.cancel_scorer.compute_score(timestamp, 'bid'),
                'cancel_density': cancel_density_score.get('bid', 0.0),
                'layering': self.layering_scorer.compute_score(timestamp, 'bid'),
                'order_age': self.age_scorer.compute_score('bid'),
                'laddering': laddering_score.get('bid', 0.0),
                'spoofing': spoofing_score.get('bid', 0.0),
                'synthetic_fill': synthetic_score.get('bid', 0.0),
                'iceberg': iceberg_score.get('bid', 0.0)
            }
        }


