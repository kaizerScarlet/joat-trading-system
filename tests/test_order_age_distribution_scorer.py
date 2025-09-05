import pytest 
from alpha_scoring.order_age_scorer import OrderAgeDistributionScorer

def test_short_lived_burst_triggers_score():
    scorer = OrderAgeDistributionScorer(short_lived_threshold_ms= 100, burst_ratio_threshold=0.6)

    #Place and cancel 3 short-lived  orders
    scorer.register_events(orderid='01', timestamp=1000, event_type="CANCEL_SPOOF",price=100.0, size=1.0, distance_from_best=0, side='bid')
    scorer.cancel_order(orderid='o1' , timestamp=1050, event_type="CANCEL_SPOOF", price=100.0, size=1.0, distance_from_best=0, side="bid") #Age; 50ms

    scorer.register_events(orderid='o2', timestamp=1100, event_type="CANCEL_SPOOF", price=100.1, size=1.0,distance_from_best=0, side='bid')
    scorer.cancel_order(orderid='o3', timestamp=1150, event_type="CANCEL_SPOOF", price=100.1, size=1.0, distance_from_best=0, side="bid") #Age: 50ms

    scorer.register_events(orderid='o3', timestamp=1200,event_type="TRUE_FILL", price=100.2, size=1.0,distance_from_best=0, side='bid')
    scorer.fill_order(orderid='03', timestamp=1250, event_type="TRUE_FILL", price=100.2, size=1.0, distance_from_best=0, side="bid")

    score_bid = scorer.compute_score(side="bid")["bid"]
    score_ask = scorer.compute_score(side="ask")["ask"]
    assert score_ask == 0.5
    assert score_bid > 0.5



def test_long_lived_orders_produce_baseline_score():
    scorer = OrderAgeDistributionScorer(short_lived_threshold_ms=100, burst_ratio_threshold = 0.6)

    #All orders are long lived
    scorer.register_events(orderid='o1', timestamp=1000, event_type="CANCEL_SPOOF",price=100.0, size=1.0,distance_from_best=5, side='bid')
    scorer.cancel_order(orderid='o1', timestamp=1500, event_type="CANCEL_SPOOF", price=100.0, size=1.0, distance_from_best=5, side="bid") #Age: 500ms

    scorer.register_events(orderid='o2', timestamp=1600, event_type="TRUE_FILL", price=100.1, size=1.0, distance_from_best=5, side='bid')
    scorer.fill_order(orderid='02', timestamp=2100, event_type="TRUE_FILL", price=100.1, size=1.0, distance_from_best=5, side="bid")  #Age: 500ms

    score_bid = scorer.compute_score(side="bid")["bid"]
    score_ask = scorer.compute_score(side="ask")['ask']
    assert score_ask == 0.5
    assert score_bid == 0.5

def test_mixed_orders_below_threshold_returns_baseline():
    scorer = OrderAgeDistributionScorer(short_lived_threshold_ms=100, burst_ratio_threshold=0.6)

    #Only 1 of 3 orders is short lived -> 0.33 < 0.6
    scorer.register_events(orderid='o1', timestamp=1000, event_type="CANCEL_SPOOF",  price=100.0, size=1.0, distance_from_best=2,side='bid')
    scorer.cancel_order(orderid='o1', timestamp=1050, event_type="CANCEL_SPOOF", price=100.0, size=1.0, distance_from_best=2, side="bid") #Short-lived 

    scorer.register_events(orderid='o2', timestamp=1100,event_type="CANCEL_SPOOF", price=100.1, size=1.0, distance_from_best=0, side='bid')
    scorer.cancel_order(orderid='o2', timestamp=1200, event_type="CANEL_SPOOF", price=100.1, size=1.0, distance_from_best=0,side="bid")

    scorer.register_events(orderid='o3', timestamp=1300,event_type="TRUE_FILL", price=100.2, size=1.0, distance_from_best=0,side='bid')
    scorer.fill_order(orderid='o3', timestamp=1450,event_type="TRUE_FILL", price=100.2, size=1.0, distance_from_best=0, side="bid")

    score_bid = scorer.compute_score(side="bid")["bid"]
    score_ask = scorer.compute_score(side="ask")["ask"]
    assert score_ask == 0.5
    assert score_bid == 0.5

def test_empty_state_returns_baseline():
    scorer = OrderAgeDistributionScorer()
    score_bid = scorer.compute_score(side="bid")["bid"]
    score_ask = scorer.compute_score(side="ask")["ask"]

    assert score_bid == 0.5
    assert score_ask == 0.5

def test_reset_clears_all_data():
    scorer = OrderAgeDistributionScorer()

    scorer.register_events(orderid='o1', timestamp=1000, event_type="CANCEL_SPOOF",price=100.0, size=1.0, distance_from_best=0,side='bid')
    scorer.cancel_order(orderid='o1', timestamp=1050, event_type="CANCEL_SPOOF", price=100.0, size=1.0, distance_from_best=0, side="bid")
    assert scorer.compute_score(side="bid")["bid"] > 0.5


    scorer.reset()
    assert scorer.compute_score(side="bid")["bid"] == 0.5
    