import unittest
from unittest.mock import MagicMock
import time
from cancel_window.synthetic_fill_detector import SyntheticFillDetection
from dynamic_risk_engine.cognitive_market_regime_classifier import CognitiveMarketRegimeClassifier, MarketRegime

class TestSyntheticFillDetection(unittest.TestCase):

    def setUp(self):
        mock_regime = MagicMock()
        mock_regime.get_current_regime.return_value = MarketRegime.UNKNOWN
        mock_regime.get_behavioral_overlay.return_value = "NORMAL"
        self.detector = SyntheticFillDetection(regime_classifier=mock_regime,retention_ms=300_000)
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
        self.assertEqual(self.detector.get_anomaly_score(), 0.0)
        self.assertEqual(self.detector.detect_anomalies(), [])

    def test_only_true_fills_no_anomaly(self):
        """
        True Fill Dominance
        """
        for i in range(3):
            self._register_event(f"order{i}", i * 100, "TRUE_FILL", side="bid")
        anomalies = self.detector.detect_anomalies()
        self.assertEqual(anomalies, [])
        self.assertEqual(self.detector.get_anomaly_score(), 0.0)

    def test_only_weak_fills_triggers_anomaly(self):
        """
        Weak Fill Dominance
        """
        for i in range(4):
            self._register_event(f"order{i}", i * 100, "WEAK_FILL", side="ask")
        anomalies = self.detector.detect_anomalies()
        self.assertEqual(len(anomalies), 1)
        anomaly = anomalies[0]
        self.assertEqual(anomaly['side'], "ask")
        self.assertEqual(anomaly['true_fills'], 0)
        self.assertEqual(anomaly['weak_fills'], 4)
        self.assertEqual(self.detector.get_anomaly_score(side="ask"), 1.0)

    def test_mixed_fills_triggers_anomaly(self):
        """
        Ratio-based anomaly detection        
        """
        for i in range(2):
            self._register_event(f"true{i}", i * 100, "TRUE_FILL", side="bid")
        for i in range(3):
            self._register_event(f"weak{i}", i * 100, "WEAK_FILL", side="bid")
        anomalies = self.detector.detect_anomalies()
        self.assertEqual(len(anomalies), 1)
        anomaly = anomalies[0]
        self.assertEqual(anomaly['true_fills'], 2)
        self.assertEqual(anomaly['weak_fills'], 3)
        score = self.detector.get_anomaly_score(side="bid")
        self.assertAlmostEqual(score, 3 / 5)

    def test_no_anomaly_when_true_equals_weak(self):
        """
        Threshold gating
        """
        for i in range(3):
            self._register_event(f"true{i}", i * 100, "TRUE_FILL", side="ask")
            self._register_event(f"weak{i}", i * 100, "WEAK_FILL", side="ask")
        anomalies = self.detector.detect_anomalies()
        self.assertEqual(anomalies, [])
        self.assertEqual(self.detector.get_anomaly_score(), 0.0)

    def test_multiple_sides_anomaly_detection(self):
        """
        Side specific anomaly isolation
        """
        for i in range(2):
            self._register_event(f"true_bid{i}", i * 100, "TRUE_FILL", side="bid")
            self._register_event(f"weak_bid{i}", i * 100, "WEAK_FILL", side="bid")
        for i in range(3):
            self._register_event(f"weak_ask{i}", i * 100, "WEAK_FILL", side="ask")
        anomalies = self.detector.detect_anomalies()
        self.assertEqual(len(anomalies), 1)
        self.assertEqual(anomalies[0]['side'], "ask")
        self.assertEqual(self.detector.get_anomaly_score(side="ask"), 3 / 3)
        self.assertEqual(self.detector.get_anomaly_score(side="bid"), 2 / 4)


    def test_score_caps_at_one(self):
        """
        Score normalization
        """
        for i in range(10):
            self._register_event(f"weak{i}", i * 100, "NO_CANCEL_FILL", side="bid")
        score = self.detector.get_anomaly_score(side="bid")
        self.assertEqual(score, 1.0)

    def test_prune_removes_old_events(self):
        """
        Time-window pruning
        """
        old_ts = self.now - 400_000
        self.detector.register_event("old_order", old_ts, "TRUE_FILL", price=100.0, size=1.0, side="ask")
        self.assertEqual(len(self.detector.events), 0)

    def test_event_type_filtering(self):
        """
        Event-type classification
        """
        self._register_event("true", 0, "TRUE_FILL", side="bid")
        self._register_event("weak1", 100, "WEAK_FILL", side="bid")
        self._register_event("weak2", 200, "NO_CANCEL_FILL", side="bid")
        self._register_event("other", 300, "EXECUTION", side="bid")
        anomalies = self.detector.detect_anomalies()
        self.assertEqual(len(anomalies), 1)
        self.assertEqual(anomalies[0]['weak_fills'], 2)
        self.assertEqual(anomalies[0]['true_fills'], 1)

if __name__ == "__main__":
    unittest.main()
