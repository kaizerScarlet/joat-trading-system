import pytest
from alpha_scoring.Order_layering_scorer import LayeringScoring

def test_detects_layering_cluster():
    scorer = LayeringScoring(reference_size = 5.0, base_score=1.0)
    base_time = 1000

    #cluster 1 -should be detected
    scorer.register_order(base_time, price = 100.0, size= 5.0, side= 'b')
    scorer.register_order(base_time + 10, price= 100.1, size= 5.0 , side= 'b')
    scorer.register_order(base_time + 15, price= 100.2, size = 5.0, side ='b')

    score = scorer.compute_score(base_time + 100)
    assert score > 0.0


def test_ignores_mixed_side_orders():
    scorer = LayeringScoring(reference_size = 5.0, base_score=1.0)

    #valid bid orders
    scorer.register_order(base_time=1000, price=100.0, size=5.0, side='b')
    scorer.register_order(base_time=1020, price=99.9, size= 5.0, side ='b')
    scorer.register_order(base_time=1040, price=99.8, size=5.0, side='b')

    #Interleaved ask order (should not be included)
    scorer.register_order(1030, price=100.1, size=5.0, side='a')

    score = scorer.compute_score(current_time = 1100)
    assert score > 0.0

def test_cluster_just_below_threshold_fails():
    scorer =LayeringScoring(reference_size = 5.0, base_score=1.0)

    scorer.register_order(base_time=1000, price=100.0, size=5.0, side='b')
    scorer.register_order(base_time=1010, price= 99.9, size= 5.0, side='b') #Only 2 orders


    score = scorer.compute_score(current_time=1100)
    assert score == 0.0


def test_old_orders_break_cluster():
    scorer = LayeringScoring(reference_size = 5.0, base_score=1.0)

    scorer.register_order(base_time=1000, price=100.0, size=5.0, side='b')
    scorer.register_order(base_time=1200, price=99.9, size=5.0, side='b')
    scorer.register_order(base_time=1400, price=99.8, size=5.0, side='b')

    score = scorer.compute_score(current_time=1500)
    assert score == 0.0


def test_scores_both_bid_and_ask_clusters_separately():
    scorer = LayeringScoring(reference_size=5.0, base_score=1.0)

    #Bid Cluster
    scorer.register_order(base_time=1000, price= 100.0, size=5.0, side='b')
    scorer.register_order(base_time=1010, price= 99.9, size= 5.0, side='b')
    scorer.register_order(base_time=1020, price=99.8, size=5.0, side='b')

    #Ask Cluster
    scorer.register_order(base_time=1000, price=101.0, size=5.0, side='a')
    scorer.register_order(base_time=1010, price=101.1, size=5.0, side='a')
    scorer.register_order(base_time=1020, price=101.2, size=5.0, side='a')

    score = scorer.compute_score(current_time=1100)

    assert score > 0.0


def test_large_order_impact_on_score():
    scorer = LayeringScoring()

    #small orders
    scorer.register_order(base_time=1000, price=100.0, size=1.0, side='b')
    scorer.register_order(base_time=1010, price=99.9, size=1.0, side='b')
    scorer.register_order(base_time=1020, price=99.8, size=1.0, side= 'b')

    small_score = scorer.compute_score(current_time=1100)

    scorer.reset()


    #Large orders
    scorer.register_order(base_time=1000, price=100.0, size=50.0, side='b')
    scorer.register_order(base_time=1010, price= 99.9, size= 50.0, side = 'b')
    scorer.register_order(base_time=1020, price=99.8, size = 50.0, side= 'b')

    large_score = scorer.compute_score(current_time=1100)

    assert large_score > small_score 



def test_sequential_clusters_scored_separately():
    scorer = LayeringScoring()

    #Cluster 1
    scorer.register_order(base_time=1000, price=100.0, size=5.0, side='b')
    scorer.register_order(base_time=1010, price=99.9, size= 5.0, side='b')
    scorer.register_order(base_time=1020, price=99.8, size=5.0, side='b')

    first_score = scorer.compute_score(current_time=1100)

    scorer.reset()

    #Cluster 2 later
    scorer.register_order(base_time=2000, price=100.0, size= 5.0, side='b')
    scorer.register_order(base_time=2010, price=99.9, size=5.0, side='b')
    scorer.register_order(base_time=2020, price=99.8, size=5.0, side='b')

    second_score = scorer.compute_score(current_time=2100)

    assert first_score > 0.0
    assert second_score > 0.0


def test_time_decay_reduces_score():
    scorer = LayeringScoring()


    #Valid cluster
    scorer.register_order(base_time=1000, price=100.0, size=5.0, side='b')
    scorer.register_order(base_time=1010, price= 99.9, size = 5.0, side = 'b')
    scorer.register_order(base_time=1020, price=99.8, size= 5.0, side= 'b')

    fresh_score = scorer.compute_score(current_time=1100)
    decayed_score = scorer.compute_score(current_time=2000)

    assert decayed_score < fresh_score
    assert decayed_score > 0.0