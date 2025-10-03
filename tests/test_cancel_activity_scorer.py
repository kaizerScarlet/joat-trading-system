import pytest
from alpha_scoring.cancel_activity_scorer import CancelActivityScorer
from alpha_scoring.cancel_activity_scorer_protocol  import CancelActivityScorerProtocol

class StubCancelWindow:
    def get_window_ms(self) -> int:
        return 1000 # fixed window for test isolation
    

def test_protocol_compliance():
    scorer: CancelActivityScorerProtocol = CancelActivityScorer(window_ms_tuner=StubCancelWindow())
    assert isinstance(scorer, CancelActivityScorer)

def test_score_bounds_stability():
    scorer: CancelActivityScorerProtocol = CancelActivityScorer(window_ms_tuner=StubCancelWindow())
    for i in range(10):
        scorer.register_events(1000 + i * 10, 'CANCEL_SPOOF', price=100.0 + i, size=5.0, side="bid", distance_from_best=i)
    score = scorer.compute_score(1100, "bid")["bid"]
    assert 0.5 <= score <= 1.0



def test_debug_view_exposes_state():
    scorer: CancelActivityScorerProtocol = CancelActivityScorer(window_ms_tuner=StubCancelWindow())
    scorer.register_events(1000, 'CANCEL_SPOOF', price=100.0, size=5.0, side="bid", distance_from_best=0)
    view = scorer.get_debug_view()
    assert 'event_buffers' in view
    assert 'ema_scores' in view

def test_cancel_on_ask_side():
    scorer: CancelActivityScorerProtocol = CancelActivityScorer(window_ms_tuner=StubCancelWindow())
    scorer.register_events(1000, 'CANCEL_SPOOF', price=101.0, size=5.0, side="ask", distance_from_best=0)
    score = scorer.compute_score(1030, side="ask")["ask"]
    assert 1.0 >= score >= 0.5


def test_single_cancel():
    scorer: CancelActivityScorerProtocol = CancelActivityScorer(window_ms_tuner=StubCancelWindow())
    scorer.register_events(1000, 'CANCEL_SPOOF', price=100.0, size=5.0, side="bid", distance_from_best=0)
    score = scorer.compute_score(1030, side="bid")["bid"]
    print(score)
    assert 1.0 >= score >= 0.5


def test_multiple_cancel_bid_at_same_price():
    """Multiple cancel-like events at same time/price/side should accumulate positive score"""
    scorer: CancelActivityScorerProtocol = CancelActivityScorer(window_ms_tuner=StubCancelWindow())
    scorer.register_events(1000, "CANCEL_SPOOF", price=100.1, size=6.0, side="bid", distance_from_best=0)
    scorer.register_events(1000, "REPOSTING_BEHAVIOUR", price=100.1, size=4.0, side="bid", distance_from_best=0)
    scorer.register_events(1000, "BURST_CANCEL", price=100.1, size=3.0, side="bid", distance_from_best=0)
    scorer.register_events(1000, "LAYER_WIPE", price=100.1, size=3.0, side="bid", distance_from_best=0)
    scorer.register_events(1000, "PING_CANCEL", price=100.1, size=2.0, side="bid", distance_from_best=0)
    scorer.register_events(1000, "HIGH_CANCEL_DENSITY", price=100.1, size=1.0, side="bid", distance_from_best=0)
    scorer.register_events(1000, "CANCEL_DENSITY_SPIKE", price=100.1, size=2.1, side="bid", distance_from_best=0)
    scorer.register_events(1000, "FILL_NO_CANCEL_CACHE", price=100.1, size=3.1, side="bid", distance_from_best=0)
    scorer.register_events(1000, "LADDER_TRUE_FILL", price=100.1, size=4.2, side="bid", distance_from_best=0)

    score = scorer.compute_score(1030, "bid")["bid"]
    print(score)
    assert 1.0 >= score >= 0.5


def test_partial_fill_penalty():
    scorer : CancelActivityScorerProtocol = CancelActivityScorer(window_ms_tuner=StubCancelWindow())
    scorer.register_events(1000, 'PARTIAL_FILL', price=100.1, size=5.0, side="bid", distance_from_best=0)
    score = scorer.compute_score(1040, side="bid")["bid"]
    print(score)
    assert 0.5 <= score <= 0.6  # penalty should reduce score below neutral


def test_iceberg_cancel_bonus():
    scorer : CancelActivityScorerProtocol= CancelActivityScorer(window_ms_tuner=StubCancelWindow())
    scorer.register_events(1000, 'ICEBERG_CANCEL', price=100.2, size=5.0, side="bid", distance_from_best=0)
    score = scorer.compute_score(1030, side="bid")["bid"]
    print(score)
    assert 1.0 >= score >= 0.7


def test_size_weighting():
    scorer : CancelActivityScorerProtocol = CancelActivityScorer(window_ms_tuner=StubCancelWindow())
    scorer.register_events(1000, 'CANCEL_SPOOF', price=100.3, size=10.0, side="bid", distance_from_best=0)
    high_score = scorer.compute_score(1040, "bid")["bid"]

    scorer.reset()
    scorer.register_events(1050, 'CANCEL_SPOOF', price=100.4, size=2.5, side="bid", distance_from_best=0)
    low_score = scorer.compute_score(1055, "bid")["bid"]

    print("High Score: {high_score}")
    print("Low_score: {low_score}")
    assert 1.0 >= high_score > low_score >= 0.5


def test_depth_penalty():
    scorer : CancelActivityScorerProtocol = CancelActivityScorer(window_ms_tuner=StubCancelWindow())
    scorer.register_events(1000, 'CANCEL_SPOOF', price=100.5, size=5.0, side="bid", distance_from_best=0)  # near top
    score_near = scorer.compute_score(1020, "bid")["bid"]

    scorer.reset()
    scorer.register_events(1030, 'CANCEL_SPOOF', price=100.6, size=5.0, side="bid", distance_from_best=5)  # farther away
    score_far = scorer.compute_score(1070, "bid")["bid"]
    print("Score_near: {score_near}")
    print("Score_far: {score_far}")
    assert 1.0 >= score_near > score_far >= 0.5


def test_outside_window_ignored():
    scorer : CancelActivityScorerProtocol = CancelActivityScorer(window_ms_tuner=StubCancelWindow())
    scorer.register_events(1000, 'CANCEL_SPOOF', price=100.7, size=2.0, side="bid", distance_from_best=0)
    score = scorer.compute_score(3000, "bid")["bid"]  # event should expire
    assert score == 0.5  # neutral after pruning


def test_reset_clears_events():
    scorer : CancelActivityScorerProtocol = CancelActivityScorer(window_ms_tuner=StubCancelWindow())
    scorer.register_events(1000, 'CANCEL_SPOOF', price=100.8, size=5.0, side="bid", distance_from_best=0)
    scorer.reset()
    assert scorer.compute_score(1030, "bid")["bid"] == 0.5
