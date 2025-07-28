import pytest 
from alpha_scoring.order_age_scorer import OrderAgeDistributionScorer

def test_short_lived_burst_triggers_score():
    scorer = OrderAgeDistributionScorer(short_lived_threshold_ms= 100, burst_ratio_threshold=0.6)

    #Place and cancel 3 short-lived  orders
    scorer.place_order('01', timestamp=1000, price=100.0, size=1.0, side='b')
    scorer.cancel_order('o1' , timestamp=1050) #Age; 50ms

    scorer.place_order('o2', timestamp=1100, price=100.1, size=1.0, side='b')
    scorer.cancel_order('o3', timestamp=1150,) #Age: 50ms

    scorer.place_order('o3', timestamp=1200, price=100.2, size=1.0, side='b')
    scorer.fill_order('03', timestamp=1250)

    score = scorer.compute_score()
    assert score > 0.0


def test_long_lived_orders_produce_zero_score():
    scorer = OrderAgeDistributionScorer(short_lived_threshold_ms=100, burst_ratio_threshold = 0.6)

    #All orders are long lived
    scorer.place_order('o1', timestamp=1000, price=100.0, size=1.0, side='b')
    scorer.cancel_order('o1', timestamp=1500) #Age: 500ms

    scorer.place_order('o2', timestamp=1600, price=100.1, size=1.0, side='b')
    scorer.fill_order('02', timestamp=2100)  #Age: 500ms

    score = scorer.compute_score()
    assert score == 0.0

def test_mixed_orders_below_threshold_returns_zero():
    scorer = OrderAgeDistributionScorer(short_lived_threshold_ms=100, burst_ratio_threshold=0.6)

    #Only 1 of 3 orders is short lived -> 0.33 < 0.6
    scorer.place_order('o1', timestamp=1000, price=100.0, size=1.0, side='b')
    scorer.cance_order('o1', timestamp=1050) #Short-lived 

    scorer.place_order('o2', timestamp=1100, price=100.1, size=1.0, side='b')
    scorer.cancel_order('o2', timestamp=1200)

    scorer.place_order('o3', timestamp=1300, price=100.2, size=1.0, side='b')
    scorer.fill_order('o3', timestamp=1450)

    score = scorer.compute_score()
    assert score == 0.0

def test_empty_state_returns_zero():
    scorer = OrderAgeDistributionScorer()
    score = scorer.compute_score()

    assert score == 0.0

def test_reset_clears_all_data():
    scorer = OrderAgeDistributionScorer()

    scorer.place_order('o1', timestamp=1000, price=100.0, size=1.0, side='b')
    scorer.cancel_order('o1', timestamp=1050)
    assert scorer.compute_score() > 0


    scorer.reset()
    assert scorer.compute_score() == 0.0
    