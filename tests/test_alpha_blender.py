import pytest 
from alpha_scoring.AlphaBlender import AlphaBlender 


def test_weighted_average_static():
    blender = AlphaBlender(
        weights = {'cancel_activity': 0.5, 'layering': 0.3, 'order_age': 0.2},
        blending_method = 'weighted average',
        adaptive = False
    )

    blender.update_signals(123,{
        'cancel_activity': 0.6,
        'layering': 0.4,
        'order_age': 0.2
    })

    score = blender.compute_alpha_score()
    expected = (0.6 * 0.5) + (0.4*0.3) + (0.2*0.2)
    assert abs(score["bid"] - expected) < 1e-6


def test_min_blending():
    blender = AlphaBlender(
        weights = {'cancel_activity': 1, 'layering' : 1, 'order_age': 1},
        blending_method = 'min',
        adaptive = False
    )

    blender.update_signals(123, {
        'cancel_activity': 0.9,
        'layer': 0.6,
        'order_age': 0.3
    })

    assert blender.compute_alpha_score()['bid']  == 0.3

def test_max_blending():
    blender = AlphaBlender(
        weights = {'cancel_activity': 1, 'layering': 1, 'order_age': 1},
        blending_method = 'max',
        adaptive = False
    )

    blender.update_signals(123, {
        'cancel_activity': 0.9,
        'layering': 0.6,
        'order_age': 0.3
    })

    assert blender.compute_alpha_score()['bid']  == 0.9

def test_adaptive_weights_update():
    blender = AlphaBlender(
        weights = {'cancel_activity': 0.4, 'layering': 0.3, 'order_age': 0.3},
        blending_method = 'weighted average',
        adaptive = True
    )

    signals = {'cancel_activty': 0.6, 'layering': 0.5, 'order_age': 0.4}

    #Simulate 3 trades with feedback
    for pnl in [100, -50, 200]:
        blender.update_signals(1000, signals)
        _ = blender.compute_alpha_score()
        blender.update_trade_feedback(signals, pnl)

    weights = blender.dynamic_weights_by_side['ask']
    assert abs(sum(weights.values()) -1.0) < 1e-6
    assert all(w >= 0 for w in weights.values())


def test_reset():
    blender = AlphaBlender(
        weights = {'cancel_activity': 0.4, 'layering': 0.3, 'order_age': 0.3},
        adaptive = True

    )
    blender.update_signals(1234, {'cancel_activity': 0.9})
    blender.update_trade_feedback({'cancel_activity': 0.9}, 50)
    blender.reset()

    for side in ['ask', 'bid']:
        assert blender.signal_performance_by_side[side]['cancel_activity']['hits'] == 0
        assert blender.latest_signals_by_side  == {'ask': {}, 'bid': {}}