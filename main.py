# main.py

from alpha_scoring.cancel_activity_scorer import CancelActivityScorer
from alpha_scoring.order_age_distribution_scorer import OrderAgeDistributionScorer
from alpha_scoring.layering_scorer import LayeringScoring
from alpha_scoring.alpha_blender import AlphaBlender
from alpha_scoring.alpha_signal_pipeline import AlphaSignalPipeline

def alphablender():
    # Instantiate modules
    cancel_scorer = CancelActivityScorer()
    age_scorer = OrderAgeDistributionScorer()
    layering_scorer = LayeringScoring(reference_size=5.0, base_score=1.0)
    blender = AlphaBlender(
        weights={'cancel_activity': 0.4, 'layering': 0.3, 'order_age': 0.3},
        blending_method='weighted_average',# Options: 'weighted_average', 'max_score', 'min_score'
        adaptive=True
    )

    # Inject into pipeline
    pipeline = AlphaSignalPipeline(
        cancel_scorer=cancel_scorer,
        age_scorer=age_scorer,
        layering_scorer=layering_scorer
    )

    # Inject blender manually if needed (or pass via constructor if refactored)
    pipeline.blender = blender

    # Simulate market snapshot
    market_snapshot = {
        'flag': [
            {'timestamp': 1696300000000, 'type': 'LAYER_CANCEL_ONLY', 'price': 101.5, 'size': 10, 'side': 'ask'},
            {'timestamp': 1696300000000, 'type': 'TRUE_FILL', 'price': 101.0, 'size': 5, 'side': 'bid'}
        ]
    }

    # Run pipeline
    pipeline.update_market(timestamp=1696300000000, market_snapshot=market_snapshot)
    alpha = pipeline.get_alpha_signal()
    print("Alpha Signal:", alpha)

    # Simulate feedback
    pipeline.trade_feedback(signal_dict=alpha, pnl=1.25, side='bid')
    print("Blender Debug View: ", pipeline.get_debug())


if __name__ == "__main__":
    alphablender()
