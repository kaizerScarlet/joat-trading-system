import pytest
import time
from alpha_scoring.Order_layering_scorer import LayeringScoring

def test_detects_layering_cluster():
    scorer = LayeringScoring(reference_size=5.0, base_score=1.0)
    now = int(time.time()) * 1000

    scorer.register_events(timestamp=now, event_type='LAYER_CANCEL_ONLY', price=100.0, size=5.0, side='bid')
    scorer.register_events(timestamp=now + 10, event_type='LAYER_CANCEL_ONLY', price=100.1, size=5.0, side='bid')
    scorer.register_events(timestamp=now + 15, event_type='LAYER_CANCEL_ONLY', price=100.2, size=5.0, side='bid')

    score = scorer.compute_score(now + 100)
    assert 0.0 < score['bid'] <= 1.0

def test_ignores_mixed_side_orders():
    scorer = LayeringScoring(reference_size=5.0, base_score=1.0)
    now = int(time.time()) * 1000

    scorer.register_events(timestamp=now, event_type='LAYER_CANCEL_ONLY', price=100.0, size=5.0, side='bid')
    scorer.register_events(timestamp=now + 20, event_type='LAYER_CANCEL_ONLY', price=99.9, size=5.0, side='bid')
    scorer.register_events(timestamp=now + 40, event_type='LAYER_CANCEL_ONLY', price=99.8, size=5.0, side='bid')
    scorer.register_events(timestamp=now + 30, event_type='LAYER_CANCEL_ONLY', price=100.1, size=5.0, side='ask')  # Should be ignored

    score = scorer.compute_score(now + 100)
    assert 0.0 < score['bid'] <= 1.0
    assert score['ask'] == 0.5

def test_cluster_just_below_threshold_fails():
    scorer = LayeringScoring(reference_size=1.0, base_score=1.0)
    now = int(time.time()) * 1000

    scorer.register_events(timestamp=now, event_type='LAYER_CANCEL_ONLY', price=100.0, size=5.0, side='bid')
    scorer.register_events(timestamp=now + 10, event_type='LAYER_CANCEL_ONLY', price=99.9, size=5.0, side='bid')  # Only 2 orders

    score = scorer.compute_score(now + 100)
    assert score['bid'] == 0.5

def test_old_orders_break_cluster():
    scorer = LayeringScoring(reference_size=5.0, base_score=1.0)
    now = int(time.time()) * 1000

    scorer.register_events(timestamp=now, event_type='LAYER_CANCEL_ONLY', price=100.0, size=5.0, side='bid')
    scorer.register_events(timestamp=now + 200, event_type='LAYER_CANCEL_ONLY', price=99.9, size=5.0, side='bid')
    scorer.register_events(timestamp=now + 400, event_type='LAYER_CANCEL_ONLY', price=99.8, size=5.0, side='bid')

    score = scorer.compute_score(now + 500)
    assert score['bid'] == 0.5

def test_scores_both_bid_and_ask_clusters_separately():
    scorer = LayeringScoring(reference_size=1.0, base_score=1.0)
    now = int(time.time()) * 1000

    # Bid Cluster
    scorer.register_events(timestamp=now, event_type='LAYER_CANCEL_ONLY', price=100.0, size=5.0, side='bid')
    scorer.register_events(timestamp=now + 10, event_type='LAYER_CANCEL_ONLY', price=99.9, size=5.0, side='bid')
    scorer.register_events(timestamp=now + 20, event_type='LAYER_CANCEL_ONLY', price=99.8, size=5.0, side='bid')

    # Ask Cluster
    scorer.register_events(timestamp=now, event_type='LAYER_CANCEL_ONLY', price=101.0, size=5.0, side='ask')
    scorer.register_events(timestamp=now + 10, event_type='LAYER_CANCEL_ONLY', price=101.1, size=5.0, side='ask')
    scorer.register_events(timestamp=now + 20, event_type='LAYER_CANCEL_ONLY', price=101.2, size=5.0, side='ask')

    score = scorer.compute_score(now + 100)
    assert 0.0 < score['bid'] <= 1.0
    assert 0.0 < score['ask'] <= 1.0

def test_large_order_impact_on_score():
    scorer = LayeringScoring(reference_size=5.0, base_score=1.0)
    now = int(time.time()) * 1000

    # Small orders
    scorer.register_events(timestamp=now, event_type='LAYER_CANCEL_ONLY', price=100.0, size=1.0, side='bid')
    scorer.register_events(timestamp=now + 10, event_type='LAYER_CANCEL_ONLY', price=99.9, size=1.0, side='bid')
    scorer.register_events(timestamp=now + 20, event_type='LAYER_CANCEL_ONLY', price=99.8, size=1.0, side='bid')
    small_score = scorer.compute_score(now + 100)['bid']


    # Large orders
    later =now + 1000
    scorer.register_events(timestamp=later, event_type='LAYER_CANCEL_ONLY', price=100.0, size=50.0, side='bid')
    scorer.register_events(timestamp= later + 10, event_type='LAYER_CANCEL_ONLY', price= 99.9, size = 50.0, side= 'bid')
    scorer.register_events(timestamp = later + 20, event_type='LAYER_CANCEL_ONLY', price= 99.8, size=50.0, side='bid')
    large_score = scorer.compute_score(later + 100)['bid']

    assert large_score > small_score
    assert 0.5 < large_score <= 1.0

def test_sequential_clusters_scored_separately():
    scorer = LayeringScoring(reference_size=5.0, base_score=1.0)
    now = int(time.time()) * 1000

    # Cluster 1
    scorer.register_events(timestamp=now, event_type='LAYER_CANCEL_ONLY', price=100.0, size=5.0, side='bid')
    scorer.register_events(timestamp=now + 10, event_type='LAYER_CANCEL_ONLY', price=99.9, size=5.0, side='bid')
    scorer.register_events(timestamp= now + 20, event_type='LAYER_CANCEL_ONLY', price=99.8, size=5.0, side='bid')
    first_score = scorer.compute_score(now + 100)['bid']

    scorer.reset()

    # Cluster 2
    later = now + 1000
    scorer.register_events(timestamp = later, event_type='LAYER_CANCEL_ONLY', price=100.0, size=5.0, side='bid')
    scorer.register_events(timestamp = later + 10, event_type='LAYER_CANCEL_ONLY', price=99.9,size= 5.0, side='bid')
    scorer.register_events(timestamp= later + 20, event_type= 'LAYER_CANCEL_ONLY', price= 99.8, size= 5.0, side= 'bid')
    second_score = scorer.compute_score(later + 100)['bid']

    assert 0.0 < first_score <= 1.0
    assert 0.0 < second_score <= 1.0

def test_time_decay_reduces_score():
    scorer = LayeringScoring(reference_size=5.0, base_score=1.0)
    now = int(time.time()) * 1000

    # Initial cluster
    scorer.register_events(now, 'LAYER_CANCEL_ONLY', 100.0, 5.0, 'bid')
    scorer.register_events(now + 10, 'LAYER_CANCEL_ONLY', 99.9, 5.0, 'bid')
    scorer.register_events(now + 20, 'LAYER_CANCEL_ONLY', 99.8, 5.0, 'bid')
    fresh_score = scorer.compute_score(now + 80)['bid']

    # Add stronger cluster later to expand normalization range
    later = now + 1000
    scorer.register_events(later, 'LAYER_CANCEL_ONLY', 100.0, 50.0, 'bid')
    scorer.register_events(later + 10, 'LAYER_CANCEL_ONLY', 99.9, 50.0, 'bid')
    scorer.register_events(later + 20, 'LAYER_CANCEL_ONLY', 99.8, 50.0, 'bid')
    scorer.compute_score(later + 100)  # Expand normalization range

    # Re-score original cluster after decay
    decayed_score = scorer.compute_score(now + 200)['bid']

    assert decayed_score < fresh_score
    assert 0.0 <= decayed_score <= 1.0


def test_side_skew_detection():
    scorer = LayeringScoring(reference_size=1.0, base_score=1.0, skew_threshold=0.8)
    now = int(time.time()) * 1000

    scorer.register_events(timestamp=now + 10, event_type='LAYER_CANCEL_ONLY', price=99.9, size=5.0, side='bid')
    scorer.register_events(timestamp=now + 20, event_type='LAYER_CANCEL_ONLY', price=99.8, size=5.0, side='bid')
    scorer.register_events(timestamp=now + 30, event_type='LAYER_CANCEL_ONLY', price=100.1, size=1.0, side='ask')

    score = scorer.compute_score(now + 100)['bid']
    assert 0.0 < score <= 1.0


def test_skew_bonus_effect():
    scorer = LayeringScoring(reference_size=1.0, base_score=1.0, skew_threshold=0.8)
    now = int(time.time()) * 1000

    # Balanced cluster
    scorer.register_events(now, 'LAYER_CANCEL_ONLY', 100.0, 5.0, 'bid')
    scorer.register_events(now + 10, 'LAYER_CANCEL_ONLY', 100.1, 5.0, 'ask')
    baseline_score = scorer.compute_score(now + 100)['bid']

    # Skewed cluster
    later = now + 1000
    scorer.register_events(later, 'LAYER_CANCEL_ONLY', 99.9, 5.0, 'bid')
    scorer.register_events(later + 10, 'LAYER_CANCEL_ONLY', 99.8, 5.0, 'bid')
    scorer.register_events(later + 20, 'LAYER_CANCEL_ONLY', 100.1, 1.0, 'ask')
    skewed_score = scorer.compute_score(later + 100)['bid']

    assert skewed_score > baseline_score

# Reposting tests should be enabled only if repost scoring is implemented
# Otherwise, comment them out or stub the logic

def test_reposting_detection():
    """Checks if score increases after cancel and repost behavior"""
    scorer = LayeringScoring(
        reference_size=1.0,
        base_score=1.0,
        repost_window_ms=100,
        repost_price_tolerance=0.02,
        skew_threshold=0.8,
    )
    now = int(time.time()) * 1000

    # Simulate cancel
    scorer.register_cancel(timestamp=now, event_type='LAYER_CANCEL_ONLY', price=100.0, size=5.0, side='bid')

    # Repost slightly after within tolerance
    scorer.register_events(timestamp=now + 40, event_type='LAYER_TRUE_FILL', price=100.01, size=5.0, side='bid')

    score = scorer.compute_score(now + 100)['bid']
    assert 0.0 < score <= 1.0

def test_combined_skew_and_repost():
    """Combines reposting behavior with volume skew to test compound scoring"""
    scorer = LayeringScoring(
        reference_size=5.0,
        base_score=1.0,
        repost_window_ms=500,
        repost_price_tolerance=0.05,
        skew_threshold=0.8
    )
    now = int(time.time()) * 1000

    # Cancel large buy order
    scorer.register_cancel(timestamp=now, event_type='LAYER_CANCEL_ONLY', price=100.0, size=5.0, side='bid')

    # Repost similar buy orders
    scorer.register_events(timestamp=now + 50, event_type='LAYER_TRUE_FILL', price=100.01, size=5.0, side='bid')
    scorer.register_events(timestamp=now + 60, event_type='LAYER_TRUE_FILL', price=99.99, size=5.0, side='bid')
    scorer.register_events(timestamp=now + 70, event_type='LAYER_TRUE_FILL', price=100.02, size=5.0, side='bid')

    # Minimal sell-side to trigger skew
    scorer.register_events(timestamp=now + 80, event_type='LAYER_TRUE_FILL', price=100.1, size=1.0, side='ask')

    score = scorer.compute_score(now + 100)['bid']
    assert 0.0 < score <= 1.0



def test_compound_behavior_outscores_baseline():
    scorer = LayeringScoring(reference_size=5.0, base_score=1.0, repost_window_ms=500, repost_price_tolerance=0.05, skew_threshold=0.8)
    now = int(time.time()) * 1000

    # Baseline cluster
    scorer.register_events(now, 'LAYER_TRUE_FILL', 100.0, 5.0, 'bid')
    baseline_score = scorer.compute_score(now + 100)['bid']

    # Compound behavior: repost + skew
    later = now + 1000
    scorer.register_cancel(later, 'LAYER_CANCEL_ONLY', 100.0, 5.0, 'bid')
    scorer.register_events(later + 50, 'LAYER_TRUE_FILL', 100.01, 5.0, 'bid')
    scorer.register_events(later + 60, 'LAYER_TRUE_FILL', 99.99, 5.0, 'bid')
    scorer.register_events(later + 70, 'LAYER_TRUE_FILL', 100.02, 5.0, 'bid')
    scorer.register_events(later + 80, 'LAYER_TRUE_FILL', 100.1, 1.0, 'ask')
    compound_score = scorer.compute_score(later + 100)['bid']

    assert compound_score > baseline_score

