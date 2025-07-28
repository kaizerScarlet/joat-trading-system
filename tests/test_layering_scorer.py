import pytest
from alpha_scoring.Order_layering_scorer import LayeringScoring

def test_detects_layering_cluster():
    scorer = LayeringScoring(reference_size = 5.0, base_score=1.0)
    timestamp = 1000

    #cluster 1 -should be detected
    scorer.register_order(timestamp, price = 100.0, size= 5.0, side= 'b')
    scorer.register_order(timestamp + 10, price= 100.1, size= 5.0 , side= 'b')
    scorer.register_order(timestamp + 15, price= 100.2, size = 5.0, side ='b')

    score = scorer.compute_score(timestamp + 100)
    assert score > 0.0


def test_ignores_mixed_side_orders():
    scorer = LayeringScoring(reference_size = 5.0, base_score=1.0)

    #valid bid orders
    scorer.register_order(timestamp=1000, price=100.0, size=5.0, side='b')
    scorer.register_order(timestamp=1020, price=99.9, size= 5.0, side ='b')
    scorer.register_order(timestamp=1040, price=99.8, size=5.0, side='b')

    #Interleaved ask order (should not be included)
    scorer.register_order(timestamp=1030, price=100.1, size=5.0, side='a')

    score = scorer.compute_score(current_time = 1100)
    assert score > 0.0

def test_cluster_just_below_threshold_fails():
    scorer =LayeringScoring(reference_size = 1.0, base_score=1.0)

    scorer.register_order(timestamp=1000, price=100.0, size=5.0, side='b')
    scorer.register_order(timestamp=1010, price= 99.9, size= 5.0, side='b') #Only 2 orders


    score = scorer.compute_score(current_time=1100)
    assert score == 0.0


def test_old_orders_break_cluster():
    scorer = LayeringScoring(reference_size = 5.0, base_score=1.0)

    scorer.register_order(timestamp=1000, price=100.0, size=5.0, side='b')
    scorer.register_order(timestamp=1200, price=99.9, size=5.0, side='b')
    scorer.register_order(timestamp=1400, price=99.8, size=5.0, side='b')

    score = scorer.compute_score(current_time=1500)
    assert score == 0.0


def test_scores_both_bid_and_ask_clusters_separately():
    scorer = LayeringScoring(reference_size=1.0, base_score=1.0)

    #Bid Cluster
    scorer.register_order(timestamp=1000, price= 100.0, size=5.0, side='b')
    scorer.register_order(timestamp=1010, price= 99.9, size= 5.0, side='b')
    scorer.register_order(timestamp=1020, price=99.8, size=5.0, side='b')

    #Ask Cluster
    scorer.register_order(timestamp=1000, price=101.0, size=5.0, side='a')
    scorer.register_order(timestamp=1010, price=101.1, size=5.0, side='a')
    scorer.register_order(timestamp=1020, price=101.2, size=5.0, side='a')

    score = scorer.compute_score(current_time=1100)

    assert score > 0.0


def test_large_order_impact_on_score():
    scorer = LayeringScoring(reference_size=5.0, base_score=1.0)

    #small orders
    scorer.register_order(timestamp=1000, price=100.0, size=1.0, side='b')
    scorer.register_order(timestamp=1010, price=99.9, size=1.0, side='b')
    scorer.register_order(timestamp=1020, price=99.8, size=1.0, side= 'b')

    small_score = scorer.compute_score(current_time=1100)

    scorer.reset()


    #Large orders
    scorer.register_order(timestamp=1000, price=100.0, size=50.0, side='b')
    scorer.register_order(timestamp=1010, price= 99.9, size= 50.0, side = 'b')
    scorer.register_order(timestamp=1020, price=99.8, size = 50.0, side= 'b')

    large_score = scorer.compute_score(current_time=1100)

    assert large_score > small_score 



def test_sequential_clusters_scored_separately():
    scorer = LayeringScoring(reference_size = 5.0, base_score=1.0)

    #Cluster 1
    scorer.register_order(timestamp=1000, price=100.0, size=5.0, side='b')
    scorer.register_order(timestamp=1010, price=99.9, size= 5.0, side='b')
    scorer.register_order(timestamp=1020, price=99.8, size=5.0, side='b')

    first_score = scorer.compute_score(current_time=1100)

    scorer.reset()

    #Cluster 2 later
    scorer.register_order(timestamp=2000, price=100.0, size= 5.0, side='b')
    scorer.register_order(timestamp=2010, price=99.9, size=5.0, side='b')
    scorer.register_order(timestamp=2020, price=99.8, size=5.0, side='b')

    second_score = scorer.compute_score(current_time=2100)

    assert first_score > 0.0
    assert second_score > 0.0


def test_time_decay_reduces_score():
    scorer = LayeringScoring(reference_size=5.0, base_score=1.0)


    #Valid cluster
    scorer.register_order(timestamp=1000, price=100.0, size=5.0, side='b')
    scorer.register_order(timestamp=1010, price= 99.9, size = 5.0, side = 'b')
    scorer.register_order(timestamp=1020, price=99.8, size= 5.0, side= 'b')

    fresh_score = scorer.compute_score(current_time=1080)
    decayed_score = scorer.compute_score(current_time=1100)

    assert decayed_score < fresh_score
    assert decayed_score > 0.0


def test_side_skew_detection():
    """Triggers when one side dominates the cluster"""
    scorer = LayeringScoring(
        reference_size = 1.0,
        base_score =1.0,
        skew_threshold = 1.0 #Low Threshold to trigger for test
    )

    #Heavy Buy-side activity
    scorer.register_order(timestamp=1000, price=100.0, size=5.0, side='b')
    scorer.register_order(timestamp=1010, price=99.9, size=5.0, side='b')
    scorer.register_order(timestamp=1020, price=99.8, size=5.0, side='b')
    scorer.register_order(timestamp=1030, price=100.1, size=1.0, side='s')

    score = scorer.compute_score(current_time=1100)
    assert score > 3.0 # 3 base orders + skew bump


def test_reposting_detection():
    """Checks if score increase after cancel and repost behaviour"""
    scorer = LayeringScoring(
        reference_size = 1.0,
        base_score=1.0,
        repost_window_ms = 100,
        repost_price_tolerance=0.02,
        skew_threshold = 0.8,
    )

    #simulate a cancel
    scorer.register_cancel(timestamp=1000, price=100.0, size=5.0, side='b')

    #Repost same order slightly after
    scorer.register_order(timestamp=1040, price=100.01, size=5.0, side='b')

    score = scorer.compute_score(current_time=1100)
    assert score >= 1.0 #Includesrepost score bump



def test_combined_skew_and_repost():
    scorer = LayeringScoring(
        reference_size = 5.0,
        base_score = 1.0,
        repost_window_ms = 500,
        skew_threshold = 0.8,
        repost_price_tolerance = 0.05
    )

    #Cancel large buy order
    scorer.register_cancel(timestamp=1000, price=100.0, size=5.0, side='b')


    #Repost similar buy orders
    scorer.register_order(timestamp=1050, price=100.01, size=5.0, side='b')
    scorer.register_order(timestamp=1060, price=99.99, size=5.0, side='b')
    scorer.register_order(timestamp=1070, price=100.02, size=5.0, side='b')


    #Minimal sell-side to trigger skew
    scorer.register_order(timestamp=1080, price=100.1, size=1.0, side='s')

    score = scorer.compute_score(current_time=1100)

    #Should include decay score + skew bump + reposting bump
    assert score >= 4.0
    




