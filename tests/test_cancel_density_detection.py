import unittest
from unittest.mock import Mock
import time
from dynamic_risk_engine.cognitive_market_regime_classifier import CognitiveMarketRegimeClassifier, MarketRegime
from cancel_window.cancel_density_detection import CancelDensityDetection

class TestCancelDensityDetection(unittest.TestCase):

    def setUp(self):
        # Mock the regime classifier
        mock_regime = Mock()
        mock_regime.get_current_regime.return_value = MarketRegime.UNKNOWN
        mock_regime.get_behavioral_overlay.return_value = "NORMAL"
        self.detector = CancelDensityDetection(regime_classifier= mock_regime,window_ms=1000, threshold=5)
        self.now = int(time.time() * 1000)

    def _register_batch(self, side: str, count: int, price_start: float = 100.0, spacing: float = 0.1):
        for i in range(count):
            self.detector.register_cancel(
                orderid=f"order_{side}_{i}",
                timestamp=self.now,
                event_type="CANCEL",
                price=price_start + i * spacing,
                size=1.0,
                side=side
            )

    def test_empty_detector_has_zero_score(self):
        """
        test_empty_detector_has_zero_score ensures no false positives
        """
        self.assertEqual(self.detector.get_density_score(), 0.0)
        self.assertEqual(self.detector.detect_spikes(), [])

    def test_below_threshold_no_spike(self):
        """
        test_below_threshold_no_spike confirms no premature spike detection
        """
        self._register_batch("bid", count=4)
        spikes = self.detector.detect_spikes()
        self.assertEqual(spikes, [])
        self.assertEqual(self.detector.get_density_score(), 0.0)

    def test_exact_threshold_triggers_spike(self):
        """
        test_exact_threshold_triggers_spike validates boundary condition
        """
        self._register_batch("ask", count=5)
        spikes = self.detector.detect_spikes()
        self.assertEqual(len(spikes), 1)
        self.assertEqual(spikes[0]['side'], "ask")
        self.assertEqual(spikes[0]['count'], 5)
        self.assertEqual(spikes[0]['unique_prices'], 5)
        self.assertGreater(self.detector.get_density_score(), 0.0)

    def test_multiple_sides_spike_detection(self):
        """
        test_multiple_sides_spike_detection checks bid/ask separation
        """
        self._register_batch("bid", count=6)
        self._register_batch("ask", count=7)
        spikes = self.detector.detect_spikes()
        self.assertEqual(len(spikes), 2)
        self.assertTrue(any(s['side'] == "bid" for s in spikes))
        self.assertTrue(any(s['side'] == "ask" for s in spikes))
        self.assertAlmostEqual(self.detector.get_density_score(), (6 + 7) / 50.0)

    def test_prune_removes_old_events(self):
        """
        test_prune_removes_old_events ensures pruning works
        """
        # Register events in the past
        old_ts = self.now - 2000  # older than window_ms
        self.detector.register_cancel("old_order", old_ts, "CANCEL", 101.0, 1.0, "bid")
        self.detector.detect_spikes(current_time=self.now)
        self.assertEqual(len(self.detector.events), 0)

    def test_score_caps_at_one(self):
        """
        test_score_caps_at_one confirms normalization logic
        """
        self._register_batch("bid", count=60)
        score = self.detector.get_density_score()
        self.assertEqual(score, 1.0)

    def test_mixed_event_types_are_counted(self):
        """
        test_mixed_event_types_are_counted proves event-type agnosticism
        """
        for i in range(5):
            self.detector.register_cancel(
                orderid=f"order_{i}",
                timestamp=self.now,
                event_type="LAYER_WIPE",  # different event type
                price=100.0 + i,
                size=1.0,
                side="bid"
            )
        spikes = self.detector.detect_spikes()
        self.assertEqual(len(spikes), 1)
        self.assertEqual(spikes[0]['side'], "bid")

    def test_unique_price_count_is_correct(self):
        """
        test_unique_price_count_is_correct validates uniqueness logic
        """
        # Duplicate prices
        for i in range(5):
            self.detector.register_cancel(
                orderid=f"order_dup_{i}",
                timestamp=self.now,
                event_type="CANCEL",
                price=100.0,  # same price
                size=1.0,
                side="ask"
            )
        spikes = self.detector.detect_spikes()
        self.assertEqual(spikes[0]['unique_prices'], 1)

    def test_score_amplified_in_volatile_regime(self):
        self.detector.regime_classifier.get_current_regime.return_value = MarketRegime.VOLATILE
        self.detector.regime_classifier.get_behavioral_overlay.return_value = "CANCEL_DENSITY_SPIKE"

        self._register_batch("bid", count=30)
        score = self.detector.get_density_score()
        self.assertGreaterEqual(score, 0.75)
        self.assertLessEqual(score, 1.0)



if __name__ == "__main__":
    unittest.main()
