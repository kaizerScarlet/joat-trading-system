import pytest
from alpha_scoring.cancel_activity_scorer import CancelActivityScorer

def test_single_cancel():
    scorer = CancelActivityScorer(window_ms=1000)
    scorer.register_events(1000, 'CANCEL_SPOOF', size=5.0, distance_from_best=0)
    score = scorer.compute_score(1500)
    assert score > 0.0

def test_partial_fill_penalty():
    scorer = CancelActivityScorer(window_ms=1000)
    scorer.register_events(1000, 'PARTIAL_FILL', size=5.0, distance_from_best=0)
    score = scorer.compute_score(1500)
    assert score < 0.0

def test_iceberg_cancel_bonus():
    scorer = CancelActivityScorer(window_ms=1000)
    scorer.register_events(1000, 'ICEBERG_CANCEL', size=5.0, distance_from_best=5)
    score = scorer.compute_score(1500)
    assert score > 0.0


def test_size_weighting():
    scorer = CancelActivityScorer(reference_size=5.0)
    scorer.register_events(1000, 'CANCEL_SPOOF', size=10.0, distance_from_best=0)
    high_score = scorer.compute_score(1500)

    scorer.reset()
    scorer.register_events(1000, 'CANCEL_SPOOF', size=2.5, distance_from_best=0)
    low_score = scorer.compute_score(1500)

    assert high_score > low_score

def test_depth_penalty():
    scorer = CancelActivityScorer(tick_penalty= 0.1)
    scorer.register_events(1000, 'CANCEL_SPOOF', size=5.0, distance_from_best=0)
    score_near = scorer.compute_score(1500)

    scorer.reset()
    scorer.register_events(1000, 'CANCEL_SPOOF', size=5.0, distance_from_best=5)
    score_far = scorer.compute_score(1500)

    assert score_near > score_far

def test_outside_window_ignored():
    scorer = CancelActivityScorer(window_ms=1000)
    scorer.register_events(1000, 'CANCEL_SPOOF', size=5.0, distance_from_best=0)
    score = scorer.compute_score(3000)  # 2 seconds later — outside window
    assert score == 0.0

def test_reset_clears_events():
    scorer = CancelActivityScorer()
    scorer.register_events(1000, 'CANCEL_SPOOF', size=5.0, distance_from_best=0)
    scorer.reset()
    assert scorer.compute_score(1500) == 0.0
