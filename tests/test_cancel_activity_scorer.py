import pytest
from alpha_scoring.cancel_activity_scorer import CancelActivityScorer

def test_single_cancel():
    scorer = CancelActivityScorer()
    scorer.register_events(1000, 'CANCEL_SPOOF',price=100.0, size=5.0, side="bid")
    score = scorer.compute_score(1500, side="bid")["bid"]
    assert score > 0.0

def test_partial_fill_penalty():
    scorer = CancelActivityScorer()
    scorer.register_events(1000, 'PARTIAL_FILL',price=100.1, size=5.0, side="bid")
    score = scorer.compute_score(1500, side="bid")["bid"]
    assert score < 0.0

def test_iceberg_cancel_bonus():
    scorer = CancelActivityScorer()
    scorer.register_events(1000, 'ICEBERG_CANCEL',price=100.2, size=5.0, side="bid")
    score = scorer.compute_score(1500, side="bid")["bid"]
    assert score > 0.0


def test_size_weighting():
    scorer = CancelActivityScorer()
    scorer.register_events(1000, 'CANCEL_SPOOF',price=100.3, size=10.0, side="bid")
    high_score = scorer.compute_score(1500, "bid")["bid"]

    scorer.reset()
    scorer.register_events(1000, 'CANCEL_SPOOF',price=100.4, size=2.5, side= "bid")
    low_score = scorer.compute_score(1500, "bid")["bid"]

    assert high_score > low_score

def test_depth_penalty():
    scorer = CancelActivityScorer()
    scorer.register_events(1000, 'CANCEL_SPOOF',price=100.5, size=5.0, side="bid")
    score_near = scorer.compute_score(1500, "bid")["bid"]

    scorer.reset()
    scorer.register_events(1000, 'CANCEL_SPOOF',price=100.6, size=5.0, side="bid")
    score_far = scorer.compute_score(1500, "bid")["bid"]

    assert score_near > score_far

def test_outside_window_ignored():
    scorer = CancelActivityScorer()
    scorer.register_events(1000, 'CANCEL_SPOOF',price=100.7, size=5.0, side="bid")
    score = scorer.compute_score(3000, "bid")["bid"]  # 2 seconds later — outside window
    assert score == 0.5

def test_reset_clears_events():
    scorer = CancelActivityScorer()
    scorer.register_events(1000, 'CANCEL_SPOOF',price=100.8, size=5.0, side="bid")
    scorer.reset()
    assert scorer.compute_score(1500, "bid")["bid"] == 0.5
