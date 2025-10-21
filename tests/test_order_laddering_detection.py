import unittest
from unittest.mock import MagicMock
import time
from dynamic_risk_engine.cognitive_market_regime_classifier import MarketRegime, CognitiveMarketRegimeClassifier
from cancel_window.order_laddering_detection import OrderLadderingDetection

class TestOrderLadderingDetection(unittest.TestCase):

    def setUp(self):
        mock_regime = MagicMock()
        mock_regime.get_current_regime.return_value = MarketRegime.UNKNOWN
        mock_regime.get_behavioral_overlay.return_value = "NORMAL"
        self.detector = OrderLadderingDetection(regime_classifier=mock_regime,retention_ms=300_000, step_window_ms=500)
        self.now = int(time.time() * 1000)

    def _register_ladder_event(self, orderid, offset_ms, event_type, price, size, side):
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
        self.assertEqual(self.detector.get_laddering_score(), 0.0)
        self.assertEqual(self.detector.detect_laddering_sequeces(), [])

    def test_below_sequence_threshold_no_detection(self):
        """
        Sequence gating
        """
        for i in range(2):
            self._register_ladder_event(f"order{i}", i * 100, "MULTILEVEL_LADDERING", 100.0 + i, 1.0, "bid")
        self.assertEqual(self.detector.detect_laddering_sequeces(), [])
        self.assertEqual(self.detector.get_laddering_score(), 0.0)

    def test_valid_laddering_sequence_detected(self):
        """
        Core laddering logic
        """
        for i in range(3):
            self._register_ladder_event(f"order{i}", i * 100, "MULTILEVEL_LADDERING", 100.0 + i, 1.0, "bid")
        sequences = self.detector.detect_laddering_sequeces()
        self.assertEqual(len(sequences), 1)
        seq = sequences[0]
        self.assertEqual(seq['side'], "bid")
        self.assertEqual(seq['count'], 3)
        self.assertEqual(seq['direction'], "up")
        self.assertAlmostEqual(seq['avg_size'], 1.0)
        self.assertIn("MULTILEVEL_LADDERING", seq['types'])

    def test_laddering_score_calculation(self):
        """
        Scoring formula validation
        """
        for i in range(3):
            self._register_ladder_event(f"order{i}", i * 100, "LADDER_CANCEL", 100.0 + i, 2.0, "bid")
        score = self.detector.get_laddering_score()
        self.assertGreater(score, 0.0)
        self.assertLessEqual(score, 1.0)

    def test_score_caps_at_one(self):
        """
        Score normalization
        """
        for i in range(20):
            self._register_ladder_event(f"order{i}", i * 10, "LADDER_TRUE_FILL", 100.0 + i, 5.0, "bid")
        self.detector.regime_classifier.get_current_regime.return_value = MarketRegime.VOLATILE
        self.detector.regime_classifier.get_behavioral_overlay.return_value = "LIQUIDITY_VACUUM"

        score = self.detector.get_laddering_score()
        self.assertEqual(score, 1.0)

    def test_sequence_direction_down_for_ask(self):
        """
        Direction logic for ask side
        """
        for i in range(3):
            self._register_ladder_event(f"order{i}", i * 100, "LADDER_CANCEL_ONLY", 105.0 - i, 1.0, "ask")
        sequences = self.detector.detect_laddering_sequeces()
        self.assertEqual(sequences[0]['direction'], "down")

    def test_mixed_event_types_in_sequence(self):
        """
        Event-type aggregation
        """
        self._register_ladder_event("order1", 0, "LADDER_CANCEL", 100.0, 1.0, "bid")
        self._register_ladder_event("order2", 100, "LADDER_TRUE_FILL", 101.0, 1.0, "bid")
        self._register_ladder_event("order3", 200, "LADDER_CANCEL_ONLY", 102.0, 1.0, "bid")
        types = self.detector.detect_laddering_sequeces()[0]['types']
        self.assertIn("LADDER_CANCEL", types)
        self.assertIn("LADDER_TRUE_FILL", types)
        self.assertIn("LADDER_CANCEL_ONLY", types)

    def test_prune_removes_old_events(self):
        """
        Time-window pruning
        """
        old_ts = self.now - 400_000
        self.detector.register_event("old_order", old_ts, "LADDER_CANCEL", 100.0, 1.0, "bid")
        self.assertEqual(len(self.detector.events), 0)

    def test_non_ladder_events_are_ignored(self):
        """
        Event-type filtering
        """
        self.detector.register_event("non_ladder", self.now, "CANCEL", 100.0, 1.0, "bid")
        self.assertEqual(self.detector.detect_laddering_sequeces(), [])
        self.assertEqual(self.detector.get_laddering_score(), 0.0)

    def test_bid_direction_validation(self):
        """
        Direction logic for bids
        """
        # Should be upward for bid
        self._register_ladder_event("order1", 0, "MULTILEVEL_LADDERING", 100.0, 1.0, "bid")
        self._register_ladder_event("order2", 100, "MULTILEVEL_LADDERING", 101.0, 1.0, "bid")
        self._register_ladder_event("order3", 200, "MULTILEVEL_LADDERING", 102.0, 1.0, "bid")
        direction = self.detector.detect_laddering_sequeces()[0]['direction']
        self.assertEqual(direction, "up")

    def test_ask_direction_validation(self):
        """
        Direction logic for asks
        """
        # Should be downward for ask
        self._register_ladder_event("order1", 0, "MULTILEVEL_LADDERING", 102.0, 1.0, "ask")
        self._register_ladder_event("order2", 100, "MULTILEVEL_LADDERING", 101.0, 1.0, "ask")
        self._register_ladder_event("order3", 200, "MULTILEVEL_LADDERING", 100.0, 1.0, "ask")
        direction = self.detector.detect_laddering_sequeces()[0]['direction']
        self.assertEqual(direction, "down")

    def test_score_amplified_in_volatile_regime(self):
        self.detector.regime_classifier.get_current_regime.return_value = MarketRegime.VOLATILE
        self.detector.regime_classifier.get_behavioral_overlay.return_value = "LIQUIDITY_VACUUM"
        # Register dense laddering events...
        for i in range(20):
            self._register_ladder_event(
            f"order{i}", i * 10, "LADDER_TRUE_FILL", 100.0 + i, 5.0, "bid"
        )

        score = self.detector.get_laddering_score()
        self.assertEqual(score, 1.0)  # Expect cap due to amplification


if __name__ == "__main__":
    unittest.main()
