import unittest
from unittest.mock import MagicMock
import time
from cancel_window.order_spoofing_detection import OrderSpoofingDetection
from dynamic_risk_engine.cognitive_market_regime_classifier import CognitiveMarketRegimeClassifier, MarketRegime

class TestOrderSpoofingDetection(unittest.TestCase):

    def setUp(self):
        mock_regime = MagicMock()
        mock_regime.get_current_regime.return_value = MarketRegime.TRENDING
        mock_regime.get_behavioral_overlay.return_value = "NORMAL"
        self.detector = OrderSpoofingDetection(regime_classifier=mock_regime,retention_ms=300_000, burst_window_ms=250)
        self.now = int(time.time() * 1000)

    def _register_event(self, orderid, offset_ms, event_type, price=100.0, size=1.0, side="bid"):
        self.detector.register_event(
            orderid=orderid,
            timestamp=self.now + offset_ms,
            event_type=event_type,
            price=price,
            size=size,
            side=side
        )

    def test_empty_detector_has_zero_score(self):
        """
        Baseline behavior
        """
        self.assertEqual(self.detector.get_spoofing_score(), 0.0)
        self.assertEqual(self.detector.detect_spoofing_clusters(), [])

    def test_below_cluster_threshold_no_detection(self):
        """
        Cluster size gating
        """
        for i in range(2):
            self._register_event(f"order{i}", i * 100, "CANCEL_SPOOF")
        self.assertEqual(self.detector.detect_spoofing_clusters(), [])
        self.assertEqual(self.detector.get_spoofing_score(), 0.0)

    def test_valid_spoofing_cluster_detected(self):
        """
        Core spoofing cluster logic
        """
        for i in range(3):
            self._register_event(f"order{i}", i * 100, "BURST_CANCEL", price=100.0 + i)
        clusters = self.detector.detect_spoofing_clusters()
        self.assertEqual(len(clusters), 1)
        cluster = clusters[0]
        self.assertEqual(cluster['side'], "bid")
        self.assertEqual(cluster['count'], 3)
        self.assertAlmostEqual(cluster['avg_price'], 101.0)
        self.assertEqual(cluster['duration_ms'], 200)
        self.assertIn("BURST_CANCEL", cluster['types'])

    def test_multiple_clusters_detected(self):
        """
        Distinct burst separation
        """
        # First burst
        for i in range(3):
            self._register_event(f"orderA{i}", i * 50, "PING_CANCEL", price=100.0 + i)
        # Gap beyond burst window
        self._register_event("gap", 500, "REPOSTING_BEHAVIOUR", price=105.0)
        # Second burst
        for i in range(3):
            self._register_event(f"orderB{i}", 600 + i * 50, "CANCEL_SPOOF", price=106.0 + i)
        clusters = self.detector.detect_spoofing_clusters()
        self.assertEqual(len(clusters), 2)

    def test_score_calculation(self):
        """
        Scoring formula validation
        """
        for i in range(3):
            self._register_event(f"order{i}", i * 100, "CANCEL_SPOOF", price=100.0 + i)
        score = self.detector.get_spoofing_score()
        self.assertGreater(score, 0.0)
        self.assertLessEqual(score, 1.0)

    def test_score_caps_at_one(self):
        """
        Score normalization — capped at 1.0 if spoof pressure is extreme
        """
        for i in range(50):
            self._register_event(f"order{i}", i * 1, "BURST_CANCEL", price=100.0 + i)
        score = self.detector.get_spoofing_score()
        self.assertGreaterEqual(score, 0.75)
        self.assertLessEqual(score, 1.0)


    def test_prune_removes_old_events(self):
        """
        Time-window pruning
        """
        old_ts = self.now - 400_000
        self.detector.register_event("old_order", old_ts, "CANCEL_SPOOF", price=100.0, size=1.0, side="ask")
        self.assertEqual(len(self.detector.events), 0)

    def test_side_separation_in_clusters(self):
        """
        Bid/ask clustering
        """
        for i in range(3):
            self._register_event(f"bid_order{i}", i * 100, "PING_CANCEL", side="bid", price=100.0 + i)
            self._register_event(f"ask_order{i}", i * 100, "PING_CANCEL", side="ask", price=101.0 + i)
        clusters = self.detector.detect_spoofing_clusters()
        sides = {c['side'] for c in clusters}
        self.assertIn("bid", sides)
        self.assertIn("ask", sides)

    def test_event_type_aggregation_in_cluster(self):
        """
        Event-type collection
        """
        self._register_event("order1", 0, "PING_CANCEL", price=100.0)
        self._register_event("order2", 100, "REPOSTING_BEHAVIOUR", price=101.0)
        self._register_event("order3", 200, "CANCEL_SPOOF", price=102.0)
        types = self.detector.detect_spoofing_clusters()[0]['types']
        self.assertIn("PING_CANCEL", types)
        self.assertIn("REPOSTING_BEHAVIOUR", types)
        self.assertIn("CANCEL_SPOOF", types)

    def test_non_spoof_events_are_ignored(self):
        """
        Non-spoof event filtering
        """
        self.detector.register_event("non_spoof", self.now, "EXECUTION", price=100.0, size=1.0, side="bid")
        self.assertEqual(self.detector.detect_spoofing_clusters(), [])
        self.assertEqual(self.detector.get_spoofing_score(), 0.0)

if __name__ == "__main__":
    unittest.main()
