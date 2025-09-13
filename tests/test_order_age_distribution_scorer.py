import pytest
from alpha_scoring.order_age_scorer import OrderAgeDistributionScorer

def test_empty_state_returns_baseline():
    scorer = OrderAgeDistributionScorer()
    score = scorer.compute_score('bid')
    assert score['bid'] == 0.0
    assert score['ask'] == 0.0

def test_short_lived_burst_triggers_score():
    scorer = OrderAgeDistributionScorer(short_lived_threshold_ms=100, burst_ratio_threshold=0.3, decay_half_life_ms=500)

    for i in range(3):
        ts = 1000 + i * 100
        oid = f'o{i}'

        scorer.register_events(oid, ts, 'PLACE_ORDER', 100.0 + i * 0.01, 5.0, 0, 'bid')     #Place order is for whern order first arrives in order book, now you need to figure out when it gets arrives first, then cancelled or filled
        scorer.register_events(oid, ts + 50, 'CANCEL_SPOOF', 100.0 + i * 0.01, 5.0, 0, 'bid')

    score = scorer.compute_score('bid')
    assert score['bid'] > 0.5
    assert score['ask'] == 0.0

def test_long_lived_orders_produce_baseline_score():
    scorer = OrderAgeDistributionScorer(short_lived_threshold_ms=100, burst_ratio_threshold=0.6)

    scorer.register_events('o1', 1000, 'PLACE_ORDER', 100.0, 1.0, 5, 'bid')
    scorer.register_events('o1', 1500, 'CANCEL_SPOOF', 100.0, 1.0, 5, 'bid')

    scorer.register_events('o2', 1600, 'PLACE_ORDER', 100.1, 1.0, 5, 'bid')
    scorer.register_events('o2', 2100, 'TRUE_FILL', 100.1, 1.0, 5, 'bid')

    score = scorer.compute_score('bid')
    assert score['bid'] == 0.0
    assert score['ask'] == 0.0

def test_mixed_orders_below_threshold_returns_baseline():
    scorer = OrderAgeDistributionScorer(short_lived_threshold_ms=100, burst_ratio_threshold=0.6)

    scorer.register_events('o1', 1000, 'PLACE_ORDER', 100.0, 1.0, 2, 'bid')
    scorer.register_events('o1', 1050, 'CANCEL_SPOOF', 100.0, 1.0, 2, 'bid')

    scorer.register_events('o2', 1100, 'PLACE_ORDER', 100.1, 1.0, 0, 'bid')
    scorer.register_events('o2', 1200, 'CANCEL_SPOOF', 100.1, 1.0, 0, 'bid')

    scorer.register_events('o3', 1300, 'PLACE_ORDER', 100.2, 1.0, 0, 'bid')
    scorer.register_events('o3', 1450, 'TRUE_FILL', 100.2, 1.0, 0, 'bid')

    score = scorer.compute_score('bid')
    assert score['bid'] > 0.5
    assert score['ask'] == 0.0

def test_reset_clears_all_data():
    scorer = OrderAgeDistributionScorer(short_lived_threshold_ms=100, burst_ratio_threshold=0.3)

    scorer.register_events('o1', 1000, 'PLACE_ORDER', 100.0, 5.0, 0, 'bid')
    scorer.register_events('o1', 1050, 'CANCEL_SPOOF', 100.0, 5.0, 0, 'bid')

    score_before = scorer.compute_score('bid')['bid']
    assert score_before > 0.5

    scorer.reset()
    score_after = scorer.compute_score('bid')['bid']
    assert score_after == 0.0

def test_volume_weighting_effect():
    scorer = OrderAgeDistributionScorer(enable_volume_weighting=True, short_lived_threshold_ms=100, burst_ratio_threshold=0.3)

    scorer.register_events('o1', 1000, 'PLACE_ORDER', 100.0, 10.0, 0, 'bid')
    scorer.register_events('o1', 1050, 'CANCEL_SPOOF', 100.0, 10.0, 0, 'bid')

    scorer.register_events('o2', 1100, 'PLACE_ORDER', 100.1, 1.0, 0, 'bid')
    scorer.register_events('o2', 1150, 'TRUE_FILL', 100.1, 1.0, 0, 'bid')

    score = scorer.compute_score('bid')
    assert score['bid'] > 0.5

def test_decay_half_life_sensitivity():
    scorer_fast_decay = OrderAgeDistributionScorer(decay_half_life_ms=100)
    scorer_slow_decay = OrderAgeDistributionScorer(decay_half_life_ms=1000)

    for scorer in [scorer_fast_decay, scorer_slow_decay]:
        scorer.register_events('o1', 1000, 'PLACE_ORDER', 100.0, 5.0, 0, 'bid')
        scorer.register_events('o1', 1050, 'CANCEL_SPOOF', 100.0, 5.0, 0, 'bid')

    score_fast = scorer_fast_decay.compute_score('bid')['bid']
    score_slow = scorer_slow_decay.compute_score('bid')['bid']
    assert score_slow > score_fast

def test_side_scoring_toggle():
    scorer = OrderAgeDistributionScorer(enable_side_scoring=False)

    scorer.register_events('o1', 1000, 'PLACE_ORDER', 100.0, 5.0, 0, 'bid')
    scorer.register_events('o1', 1050, 'CANCEL_SPOOF', 100.0, 5.0, 0, 'bid')

    score = scorer.compute_score('bid')
    assert 'combined' in score
    assert isinstance(score['combined'], float)

def test_zero_size_order_handling():
    scorer = OrderAgeDistributionScorer()

    scorer.register_events('o1', 1000, 'PLACE_ORDER', 100.0, 0.0, 0, 'bid')
    scorer.register_events('o1', 1050, 'CANCEL_SPOOF', 100.0, 0.0, 0, 'bid')

    score = scorer.compute_score('bid')
    assert score['bid'] == 0.0
