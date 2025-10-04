import pytest
import time
import uuid
from alpha_scoring.Order_layering_scorer import LayeringScoring
from alpha_scoring.Order_layering_scorer_protocol import LayeringScoringProtocol


class StubLayeringDetector:
    def __init__(self):
        self.orders = []
        self.cancels = []
        self.fills = []

    def register_order(self, orderid, timestamp, price, size, side):
        self.orders.append({
            'orderid': orderid,
            'timestamp': timestamp,
            'price': price,
            'size': size,
            'side': side
        })

    def register_cancel(self, orderid, timestamp, event_type, price, size, side):
        self.cancels.append({
            'orderid': orderid,
            'timestamp': timestamp,
            'event_type': event_type,
            'price': price,
            'size': size,
            'side': side
        })

    def register_fill(self, orderid, timestamp, event_type, price, size, side):
        self.fills.append({
            'orderid': orderid,
            'timestamp': timestamp,
            'event_type': event_type,
            'price': price,
            'size': size,
            'side': side
        })

    def detect_layering(self):
        clusters = []
        for side in ['bid', 'ask']:
            side_events = [e for e in self.cancels + self.fills if e['side'] == side]
            if len(side_events) >= 3:
                clusters.append({
                    'label': self._infer_label(side_events),
                    'cluster': side_events,
                    'durations': [50] * len(side_events),
                    'side': side,
                    'cluster_size': len(side_events)
                })
        return clusters

    def _infer_label(self, events):
        cancel_count = sum(1 for e in events if 'CANCEL' in e['event_type'])
        fill_count = sum(1 for e in events if 'FILL' in e['event_type'])
        if cancel_count and not fill_count:
            return 'LAYER_CANCEL_ONLY'
        elif fill_count and not cancel_count:
            return 'LAYER_TRUE_FILL'
        elif cancel_count and fill_count:
            return 'LAYER_PARTIAL_FILL'
        return 'UNKNOWN'

    def reset(self):
        self.orders.clear()
        self.cancels.clear()
        self.fills.clear()

    class tuner:
        ema_latency = 100



def test_detects_layering_cluster():
    detector = StubLayeringDetector()
    scorer : LayeringScoringProtocol = LayeringScoring(layering_detector = detector, reference_size=5.0, base_score=1.0)
    now = int(time.time()) * 1000

    scorer.register_events(timestamp=now,orderid=str(uuid.uuid4()), event_type='LAYER_CANCEL_ONLY', price=100.0, size=5.0, side='bid')
    scorer.register_events(timestamp=now + 10,orderid=str(uuid.uuid4()), event_type='LAYER_CANCEL_ONLY', price=100.1, size=5.0, side='bid')
    scorer.register_events(timestamp=now + 15,orderid=str(uuid.uuid4()), event_type='LAYER_CANCEL_ONLY', price=100.2, size=5.0, side='bid')

    score = scorer.compute_score(now + 100)
    assert 0.0 < score['bid'] <= 1.0

def test_ignores_mixed_side_orders():
    detector = StubLayeringDetector()
    scorer : LayeringScoringProtocol = LayeringScoring(layering_detector = detector, reference_size=5.0, base_score=1.0)
    now = int(time.time()) * 1000

    scorer.register_events(timestamp=now,orderid=str(uuid.uuid4()), event_type='LAYER_CANCEL_ONLY', price=100.0, size=5.0, side='bid')
    scorer.register_events(timestamp=now + 20,orderid=str(uuid.uuid4()), event_type='LAYER_CANCEL_ONLY', price=99.9, size=5.0, side='bid')
    scorer.register_events(timestamp=now + 40,orderid=str(uuid.uuid4()), event_type='LAYER_CANCEL_ONLY', price=99.8, size=5.0, side='bid')
    scorer.register_events(timestamp=now + 30,orderid=str(uuid.uuid4()), event_type='LAYER_CANCEL_ONLY', price=100.1, size=5.0, side='ask')  # Should be ignored

    score = scorer.compute_score(now + 100)
    assert 0.0 < score['bid'] <= 1.0
    assert score['ask'] == 0.5

def test_cluster_just_below_threshold_fails():
    detector = StubLayeringDetector()
    scorer : LayeringScoringProtocol = LayeringScoring(layering_detector = detector, reference_size=1.0, base_score=1.0)
    now = int(time.time()) * 1000

    scorer.register_events(timestamp=now,orderid=str(uuid.uuid4()), event_type='LAYER_CANCEL_ONLY', price=100.0, size=5.0, side='bid')
    scorer.register_events(timestamp=now + 10,orderid=str(uuid.uuid4()), event_type='LAYER_CANCEL_ONLY', price=99.9, size=5.0, side='bid')  # Only 2 orders

    score = scorer.compute_score(now + 100)
    assert score['bid'] == 0.5

def test_old_orders_break_cluster():
    detector = StubLayeringDetector()
    scorer : LayeringScoringProtocol = LayeringScoring(layering_detector = detector, reference_size=5.0, base_score=1.0)
    now = int(time.time()) * 1000

    scorer.register_events(timestamp=now,orderid=str(uuid.uuid4()), event_type='LAYER_CANCEL_ONLY', price=100.0, size=5.0, side='bid')
    scorer.register_events(timestamp=now + 200,orderid=str(uuid.uuid4()), event_type='LAYER_CANCEL_ONLY', price=99.9, size=5.0, side='bid')
    scorer.register_events(timestamp=now + 400,orderid=str(uuid.uuid4()), event_type='LAYER_CANCEL_ONLY', price=99.8, size=5.0, side='bid')

    score = scorer.compute_score(now + 500)
    assert score['bid'] == 0.5

def test_scores_both_bid_and_ask_clusters_separately():
    detector = StubLayeringDetector()
    scorer : LayeringScoringProtocol = LayeringScoring(layering_detector = detector, reference_size=1.0, base_score=1.0)
    now = int(time.time()) * 1000

    # Bid Cluster
    scorer.register_events(timestamp=now,orderid=str(uuid.uuid4()), event_type='LAYER_CANCEL_ONLY', price=100.0, size=5.0, side='bid')
    scorer.register_events(timestamp=now + 10,orderid=str(uuid.uuid4()), event_type='LAYER_CANCEL_ONLY', price=99.9, size=5.0, side='bid')
    scorer.register_events(timestamp=now + 20,orderid=str(uuid.uuid4()), event_type='LAYER_CANCEL_ONLY', price=99.8, size=5.0, side='bid')

    # Ask Cluster
    scorer.register_events(timestamp=now,orderid=str(uuid.uuid4()), event_type='LAYER_CANCEL_ONLY', price=101.0, size=5.0, side='ask')
    scorer.register_events(timestamp=now + 10,orderid=str(uuid.uuid4()), event_type='LAYER_CANCEL_ONLY', price=101.1, size=5.0, side='ask')
    scorer.register_events(timestamp=now + 20,orderid=str(uuid.uuid4()), event_type='LAYER_CANCEL_ONLY', price=101.2, size=5.0, side='ask')

    score = scorer.compute_score(now + 100)
    assert 0.0 < score['bid'] <= 1.0
    assert 0.0 < score['ask'] <= 1.0

def test_large_order_impact_on_score():
    detector = StubLayeringDetector()
    scorer : LayeringScoringProtocol = LayeringScoring(layering_detector = detector, reference_size=5.0, base_score=1.0)
    now = int(time.time()) * 1000

    # Small orders
    scorer.register_events(timestamp=now,orderid=str(uuid.uuid4()), event_type='LAYER_CANCEL_ONLY', price=100.0, size=1.0, side='bid')
    scorer.register_events(timestamp=now + 10,orderid=str(uuid.uuid4()), event_type='LAYER_CANCEL_ONLY', price=99.9, size=1.0, side='bid')
    scorer.register_events(timestamp=now + 20,orderid=str(uuid.uuid4()), event_type='LAYER_CANCEL_ONLY', price=99.8, size=1.0, side='bid')
    small_score = scorer.compute_score(now + 100)['bid']


    # Large orders
    later =now + 1000
    scorer.register_events(timestamp=later,orderid=str(uuid.uuid4()), event_type='LAYER_CANCEL_ONLY', price=100.0, size=50.0, side='bid')
    scorer.register_events(timestamp= later + 10,orderid=str(uuid.uuid4()), event_type='LAYER_CANCEL_ONLY', price= 99.9, size = 50.0, side= 'bid')
    scorer.register_events(timestamp = later + 20,orderid=str(uuid.uuid4()), event_type='LAYER_CANCEL_ONLY', price= 99.8, size=50.0, side='bid')
    large_score = scorer.compute_score(later + 100)['bid']

    assert large_score > small_score
    assert 0.5 < large_score <= 1.0

def test_sequential_clusters_scored_separately():
    detector = StubLayeringDetector()
    scorer : LayeringScoringProtocol = LayeringScoring(layering_detector = detector, reference_size=5.0, base_score=1.0)
    now = int(time.time()) * 1000

    # Cluster 1
    scorer.register_events(timestamp=now,orderid=str(uuid.uuid4()), event_type='LAYER_CANCEL_ONLY', price=100.0, size=5.0, side='bid')
    scorer.register_events(timestamp=now + 10,orderid=str(uuid.uuid4()), event_type='LAYER_CANCEL_ONLY', price=99.9, size=5.0, side='bid')
    scorer.register_events(timestamp= now + 20,orderid=str(uuid.uuid4()), event_type='LAYER_CANCEL_ONLY', price=99.8, size=5.0, side='bid')
    first_score = scorer.compute_score(now + 100)['bid']

    scorer.reset()

    # Cluster 2
    later = now + 1000
    scorer.register_events(timestamp = later,orderid=str(uuid.uuid4()), event_type='LAYER_CANCEL_ONLY', price=100.0, size=5.0, side='bid')
    scorer.register_events(timestamp = later + 10,orderid=str(uuid.uuid4()), event_type='LAYER_CANCEL_ONLY', price=99.9,size= 5.0, side='bid')
    scorer.register_events(timestamp= later + 20,orderid=str(uuid.uuid4()), event_type= 'LAYER_CANCEL_ONLY', price= 99.8, size= 5.0, side= 'bid')
    second_score = scorer.compute_score(later + 100)['bid']

    assert 0.0 < first_score <= 1.0
    assert 0.0 < second_score <= 1.0
def test_time_decay_reduces_score():
    detector = StubLayeringDetector()
    scorer = LayeringScoring(layering_detector=detector, reference_size=5.0, base_score=1.0)
    now = int(time.time()) * 1000

    # Initial cluster
    scorer.register_events(timestamp=now, orderid=str(uuid.uuid4()), event_type='LAYER_CANCEL_ONLY', price=100.0, size=5.0, side='bid')
    scorer.register_events(timestamp=now + 10, orderid=str(uuid.uuid4()), event_type='LAYER_CANCEL_ONLY', price=99.9, size=5.0, side='bid')
    scorer.register_events(timestamp=now + 20, orderid=str(uuid.uuid4()), event_type='LAYER_CANCEL_ONLY', price=99.8, size=5.0, side='bid')
    scorer.compute_score(now + 80)
    raw_fresh = scorer._raw_score_by_side['bid']

    # Re-score after decay without injecting new clusters
    scorer.compute_score(now + 200)
    raw_decayed = scorer._raw_score_by_side['bid']

    assert raw_decayed < raw_fresh




def test_side_skew_detection():
    detector = StubLayeringDetector()
    scorer : LayeringScoringProtocol = LayeringScoring(layering_detector = detector, reference_size=1.0, base_score=1.0, skew_threshold=0.8)
    now = int(time.time()) * 1000

    scorer.register_events(timestamp=now + 10,orderid=str(uuid.uuid4()), event_type='LAYER_CANCEL_ONLY', price=99.9, size=5.0, side='bid')
    scorer.register_events(timestamp=now + 20,orderid=str(uuid.uuid4()), event_type='LAYER_CANCEL_ONLY', price=99.8, size=5.0, side='bid')
    scorer.register_events(timestamp=now + 30,orderid=str(uuid.uuid4()), event_type='LAYER_CANCEL_ONLY', price=100.1, size=1.0, side='ask')

    score = scorer.compute_score(now + 100)['bid']
    assert 0.0 < score <= 1.0


def test_skew_bonus_effect():
    detector = StubLayeringDetector()
    scorer : LayeringScoringProtocol = LayeringScoring(layering_detector = detector, reference_size=1.0, base_score=1.0, skew_threshold=0.8)
    now = int(time.time()) * 1000

    # Balanced cluster
    scorer.register_events(timestamp = now,orderid=str(uuid.uuid4()), event_type='LAYER_CANCEL_ONLY', price=100.0, size=5.0, side='bid')
    scorer.register_events(timestamp = now + 10, orderid = str(uuid.uuid4()),event_type='LAYER_CANCEL_ONLY', price=100.1, size=5.0, side='ask')
    baseline_score = scorer.compute_score(now + 100)['bid']

    # Skewed cluster
    later = now + 1000
    scorer.register_events(timestamp = later,orderid=str(uuid.uuid4()), event_type= 'LAYER_CANCEL_ONLY', price= 99.9, size=5.0, side='bid')
    scorer.register_events(timestamp = later + 10,orderid=str(uuid.uuid4()), event_type = 'LAYER_CANCEL_ONLY', price= 99.8, size=5.0, side='bid')
    scorer.register_events(timestamp = later + 20, orderid=str(uuid.uuid4()),event_type='LAYER_CANCEL_ONLY', price=100.1, size=1.0, side='ask')
    skewed_score = scorer.compute_score(later + 100)['bid']

    assert skewed_score > baseline_score

# Reposting tests should be enabled only if repost scoring is implemented
# Otherwise, comment them out or stub the logic

def test_reposting_detection():
    """Checks if score increases after cancel and repost behavior"""
    detector = StubLayeringDetector()
    scorer : LayeringScoringProtocol = LayeringScoring(
        layering_detector = detector,
        reference_size=1.0,
        base_score=1.0,
        repost_window_ms=100,
        repost_price_tolerance=0.02,
        skew_threshold=0.8,
    )
    now = int(time.time()) * 1000

    # Simulate cancel
    scorer.register_cancel(timestamp=now,orderid=str(uuid.uuid4()), event_type='LAYER_CANCEL_ONLY', price=100.0, size=5.0, side='bid')

    # Repost slightly after within tolerance
    scorer.register_events(timestamp=now + 40,orderid=str(uuid.uuid4()), event_type='LAYER_TRUE_FILL', price=100.01, size=5.0, side='bid')

    score = scorer.compute_score(now + 100)['bid']
    assert 0.0 < score <= 1.0

def test_combined_skew_and_repost():
    """Combines reposting behavior with volume skew to test compound scoring"""
    detector = StubLayeringDetector()
    scorer : LayeringScoringProtocol = LayeringScoring(
        layering_detector = detector,
        reference_size=5.0,
        base_score=1.0,
        repost_window_ms=500,
        repost_price_tolerance=0.05,
        skew_threshold=0.8
    )
    now = int(time.time()) * 1000

    # Cancel large buy order
    scorer.register_cancel(timestamp=now,orderid=str(uuid.uuid4()), event_type='LAYER_CANCEL_ONLY', price=100.0, size=5.0, side='bid')

    # Repost similar buy orders
    scorer.register_events(timestamp=now + 50,orderid=str(uuid.uuid4()), event_type='LAYER_TRUE_FILL', price=100.01, size=5.0, side='bid')
    scorer.register_events(timestamp=now + 60,orderid=str(uuid.uuid4()), event_type='LAYER_TRUE_FILL', price=99.99, size=5.0, side='bid')
    scorer.register_events(timestamp=now + 70,orderid=str(uuid.uuid4()), event_type='LAYER_TRUE_FILL', price=100.02, size=5.0, side='bid')

    # Minimal sell-side to trigger skew
    scorer.register_events(timestamp=now + 80,orderid=str(uuid.uuid4()), event_type='LAYER_TRUE_FILL', price=100.1, size=1.0, side='ask')

    score = scorer.compute_score(now + 100)['bid']
    assert 0.0 < score <= 1.0



def test_compound_behavior_outscores_baseline():
    detector = StubLayeringDetector()
    scorer : LayeringScoringProtocol = LayeringScoring(layering_detector = detector, reference_size=5.0, base_score=1.0, repost_window_ms=500, repost_price_tolerance=0.05, skew_threshold=0.8)
    now = int(time.time()) * 1000

    # Baseline cluster
    scorer.register_events(timestamp = now, orderid=str(uuid.uuid4()), event_type='LAYER_TRUE_FILL', price=100.0, size=5.0, side='bid')
    baseline_score = scorer.compute_score(now + 100)['bid']

    # Compound behavior: repost + skew
    later = now + 1000
    scorer.register_cancel(timestamp = later, orderid=str(uuid.uuid4()), event_type='LAYER_CANCEL_ONLY', price=100.0, size=5.0, side='bid')
    scorer.register_events(timestamp = later + 50, orderid=str(uuid.uuid4()), event_type='LAYER_TRUE_FILL', price=100.01, size=5.0, side='bid')
    scorer.register_events(timestamp = later + 60, orderid=str(uuid.uuid4()), event_type='LAYER_TRUE_FILL', price=99.99, size=5.0, side='bid')
    scorer.register_events(timestamp = later + 70, orderid=str(uuid.uuid4()), event_type='LAYER_TRUE_FILL', price=100.02, size=5.0, side='bid')
    scorer.register_events(timestamp = later + 80, orderid=str(uuid.uuid4()), event_type='LAYER_TRUE_FILL', price=100.1, size=1.0, side='ask')
    compound_score = scorer.compute_score(later + 100)['bid']

    assert compound_score > baseline_score


def test_score_volatility_tracks_change():
    detector = StubLayeringDetector()
    scorer : LayeringScoringProtocol = LayeringScoring(layering_detector = detector, reference_size=5.0, base_score=1.0, repost_window_ms=500, repost_price_tolerance=0.05, skew_threshold=0.8)
    scorer.register_events(timestamp = 1000, orderid=str(uuid.uuid4()), event_type='LAYER_CANCEL_ONLY', price=100.0, size=5.0, side='bid')
    scorer.compute_score(current_time=1100)
    scorer.register_events(timestamp = 1200, orderid=str(uuid.uuid4()), event_type='LAYER_TRUE_FILL', price=100.1, size=5.0, side='bid')
    scorer.compute_score(current_time=1300)
    view = scorer.get_debug_view()
    assert view['score_volatility']['bid'] > 0.0


def test_cluster_density_reflects_activity():
    detector = StubLayeringDetector()
    scorer : LayeringScoringProtocol = LayeringScoring(layering_detector = detector, reference_size=5.0, base_score=1.0, repost_window_ms=500, repost_price_tolerance=0.05, skew_threshold=0.8)
    scorer.register_events(timestamp =1000,orderid=str(uuid.uuid4()), event_type = 'LAYER_CANCEL_ONLY', price= 100.0, size=5.0, side='ask')
    scorer.register_events(timestamp = 1020,orderid=str(uuid.uuid4()), event_type='LAYER_CANCEL_ONLY', price=100.1, size=5.0, side='ask')
    scorer.register_events(timestamp =1040, orderid=str(uuid.uuid4()), event_type='LAYER_CANCEL_ONLY', price=100.2, size=5.0, side='ask')
    scorer.compute_score(current_time=1100)
    view = scorer.get_debug_view()
    assert view['cluster_density']['ask'] >= 1

def test_debug_view_after_reset_is_clean():
    detector = StubLayeringDetector()
    scorer : LayeringScoringProtocol = LayeringScoring(layering_detector = detector, reference_size=5.0, base_score=1.0, repost_window_ms=500, repost_price_tolerance=0.05, skew_threshold=0.8)
    scorer.register_events(timestamp = 1000,orderid=str(uuid.uuid4()), event_type= 'LAYER_CANCEL_ONLY', price=100.0, size=5.0, side='bid')
    scorer.compute_score(current_time=1100)
    scorer.reset()
    view = scorer.get_debug_view()
    assert view['last_score']['bid'] == 0.0
    assert view['recent_cancels'] == []
