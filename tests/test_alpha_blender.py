import pytest 
from alpha_scoring.AlphaBlender import AlphaBlender
from alpha_scoring.Alphablender_protocol import AlphaBlenderProtocol

#Test Protocol compliance
def  test_blender_protoocol_compliance():
    blender: AlphaBlenderProtocol = AlphaBlender(
        weights = {
            'cancel_activity': 0.2,
            'cancel_density_score': 0.1,
            'layering': 0.15,
            'order_age': 0.1,
            'order_laddering_score': 0.1,
            'iceberg_score': 0.1,
            'order_spoofing_score': 0.15,
            'synthetic_fill_score': 0.1
        },
        blending_method = 'weighted average',
        adaptive = False
    )
    assert hasattr(blender, 'compute_alpha_score')
    assert hasattr(blender, 'update_signals')
    assert hasattr(blender, 'update_trade_feedback')
    assert hasattr(blender, 'get_debug_view')
    assert hasattr(blender, 'reset')


def test_weighted_average_static():
    blender = AlphaBlender(
        weights = {
            'cancel_activity': 0.2,
            'cancel_density_score': 0.1,
            'layering': 0.15,
            'order_age': 0.1,
            'order_laddering_score': 0.1,
            'iceberg_score': 0.1,
            'order_spoofing_score': 0.15,
            'synthetic_fill_score': 0.1
        },
        blending_method = 'weighted average',
        adaptive = False
    )

    blender.update_signals(123,{
        'cancel_activity': 0.5,
        'cancel_density_score': 0.3,
        'layering': 0.4,
        'order_age': 0.6,
        'order_laddering_score': 0.2,
        'iceberg_score': 0.1,
        'order_spoofing_score': 0.25,
        'synthetic_fill_score': 0.15
    })

    score = blender.compute_alpha_score()
    expected = (0.6 * 0.5) + (0.4*0.3) + (0.2*0.2)
    assert abs(score["bid"] - expected) < 1e-6


def test_min_blending():
    blender = AlphaBlender(
        weights = {
            'cancel_activity': 1,
            'cancel_density_score': 1,
            'layering': 1,
            'order_age': 1,
            'order_laddering_score': 1,
            'iceberg_score': 1,
            'order_spoofing_score': 1,
            'synthetic_fill_score': 1
        },


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
        weights = {
            'cancel_activity': 1,
            'cancel_density_score': 1,
            'layering': 1,
            'order_age': 1,
            'order_laddering_score': 1,
            'iceberg_score': 1,
            'order_spoofing_score': 1,
            'synthetic_fill_score': 1
        },
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
        weights = {
            'cancel_activity': 0.2,
            'cancel_density_score': 0.1,
            'layering': 0.15,
            'order_age': 0.1,
            'order_laddering_score': 0.1,
            'iceberg_score': 0.1,
            'order_spoofing_score': 0.15,
            'synthetic_fill_score': 0.1
        },
        blending_method = 'weighted average',
        adaptive = True
    )

    signals = {
        'cancel_activity': 0.5,
        'cancel_density_score': 0.3,
        'layering': 0.4,
        'order_age': 0.6,
        'order_laddering_score': 0.2,
        'iceberg_score': 0.1,
        'order_spoofing_score': 0.25,
        'synthetic_fill_score': 0.15
    }

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
        weights = {
            'cancel_activity': 0.2,
            'cancel_density_score': 0.1,
            'layering': 0.15,
            'order_age': 0.1,
            'order_laddering_score': 0.1,
            'iceberg_score': 0.1,
            'order_spoofing_score': 0.15,
            'synthetic_fill_score': 0.1
        },
        adaptive = True

    )
    blender.update_signals(1234, {'cancel_activity': 0.9}, side='bid')
    blender.update_trade_feedback({'cancel_activity': 0.9}, 50, side='bid')
    blender.reset()

    for side in ['ask', 'bid']:
        assert blender.signal_performance_by_side[side]['cancel_activity']['hits'] == 0
        assert blender.latest_signals_by_side  == {'ask': {}, 'bid': {}}


import pytest
from alpha_scoring.AlphaBlender import AlphaBlender

def test_weighted_average_static():
    blender = AlphaBlender(
        weights={'cancel_activity': 0.5, 'layering': 0.3, 'order_age': 0.2},
        blending_method='weighted average',
        adaptive=False
    )

    blender.update_signals(123, {
        'cancel_activity': 0.6,
        'layering': 0.4,
        'order_age': 0.2
    }, side='bid')

    score = blender.compute_alpha_score()
    expected = (0.6 * 0.5) + (0.4 * 0.3) + (0.2 * 0.2)
    assert abs(score["bid"] - expected) < 1e-6

def test_min_blending():
    blender = AlphaBlender(
        weights={'cancel_activity': 1, 'layering': 1, 'order_age': 1},
        blending_method='min',
        adaptive=False
    )

    blender.update_signals(123, {
        'cancel_activity': 0.9,
        'layering': 0.6,
        'order_age': 0.3
    }, side='bid')

    assert blender.compute_alpha_score()['bid'] == 0.3

def test_max_blending():
    blender = AlphaBlender(
        weights = {
            'cancel_activity': 1,
            'cancel_density_score': 1,
            'layering': 1,
            'order_age': 1,
            'order_laddering_score': 1,
            'iceberg_score': 1,
            'order_spoofing_score': 1,
            'synthetic_fill_score': 1
        },
        blending_method='max',
        adaptive=False
    )

    blender.update_signals(123, {
        'cancel_activity': 0.9,
        'layering': 0.6,
        'order_age': 0.3
    }, side='bid')

    assert blender.compute_alpha_score()['bid'] == 0.9

def test_adaptive_weights_update():
    blender = AlphaBlender(
        weights={'cancel_activity': 0.4, 'layering': 0.3, 'order_age': 0.3},
        blending_method='weighted average',
        adaptive=True
    )

    signals = {'cancel_activity': 0.6, 'layering': 0.5, 'order_age': 0.4}

    for pnl in [100, -50, 200]:
        blender.update_signals(1000, signals, side='ask')
        _ = blender.compute_alpha_score()
        blender.update_trade_feedback(signals, pnl, side='ask')

    weights = blender.dynamic_weights_by_side['ask']
    assert abs(sum(weights.values()) - 1.0) < 1e-6
    assert all(w >= 0 for w in weights.values())

def test_reset():
    blender = AlphaBlender(
        weights={'cancel_activity': 0.4, 'layering': 0.3, 'order_age': 0.3},
        adaptive=True
    )

    blender.update_signals(1234, {'cancel_activity': 0.9}, side='bid')
    blender.update_trade_feedback({'cancel_activity': 0.9}, 50, side='bid')
    blender.reset()

    for side in ['ask', 'bid']:
        assert blender.signal_performance_by_side[side]['cancel_activity']['hits'] == 0
        assert blender.latest_signals_by_side == {'ask': {}, 'bid': {}}

def test_empty_signal_returns_zero():
    blender = AlphaBlender(weights={'cancel_activity': 1}, adaptive=False)
    score = blender.compute_alpha_score()
    assert score['bid'] == 0.0
    assert score['ask'] == 0.0

def test_side_specific_signal_fusion():
    blender = AlphaBlender(
        weights={'cancel_activity': 0.5, 'layering': 0.5},
        blending_method='weighted average',
        adaptive=False
    )

    blender.update_signals(100, {'cancel_activity': 0.8, 'layering': 0.2}, side='ask')
    blender.update_signals(100, {'cancel_activity': 0.4, 'layering': 0.6}, side='bid')

    scores = blender.compute_alpha_score()
    assert abs(scores['ask'] - 0.5) < 1e-6
    assert abs(scores['bid'] - 0.5) < 1e-6
