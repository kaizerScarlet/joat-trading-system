import unittest
import time
from unittest.mock import MagicMock
from dynamic_risk_engine.cognitive_market_regime_classifier import CognitiveMarketRegimeClassifier, MarketRegime
from alpha_scoring.order_iceberg_scorer import IcebergScorer

class TestIcebergScorer(unittest.TestCase):
    def setUp(self):
        self.detector = MagicMock()
        self.scorer = IcebergScorer(detector=self.detector, base_score=1.0, decay_half_life=5000)
        self.now = int(time.time() * 1000)

    def test_no_icebergs_yields_zero_score(self):
        self.detector.detect_icebergs.return_value = []
        score = self.scorer.compute_score(current_time=self.now)
        self.assertEqual(score['ask'], 0.0)
        self.assertEqual(score['bid'], 0.0)

    def test_single_iceberg_score(self):
        self.detector.detect_icebergs.return_value = [{'side': 'bid', 'total_size': 100, 'duration': 50}]
        score = self.scorer.compute_score(current_time=self.now)
        expected = min(1.0, 1.0 * (100 / 50))  # base_score * aggression
        self.assertAlmostEqual(score['bid'], expected)
        self.assertEqual(score['ask'], 0.0)

    def test_score_caps_at_one(self):
        self.detector.detect_icebergs.return_value = [{'side': 'ask', 'total_size': 1000, 'duration': 1}]
        score = self.scorer.compute_score(current_time=self.now)
        self.assertEqual(score['ask'], 1.0)

    def test_score_blending_with_previous(self):
        # First iceberg: moderate aggression
        self.detector.detect_icebergs.return_value = [{'side': 'ask', 'total_size': 5, 'duration': 10}]
        score1 = self.scorer.compute_score(current_time=self.now)

        # Second iceberg: weaker
        later_time = self.now + 1000
        self.detector.detect_icebergs.return_value = [{'side': 'ask', 'total_size': 2, 'duration': 10}]
        score2 = self.scorer.compute_score(current_time=later_time)

        print(f"Score1: {score1['ask']}, Score2: {score2['ask']}")
        self.assertLess(score2['ask'], score1['ask'])



    def test_score_decay_over_time(self):
        # Initial iceberg
        self.detector.detect_icebergs.return_value = [{'side': 'bid', 'total_size': 100, 'duration': 10}]
        initial_score = self.scorer.compute_score(current_time=self.now)

        # No new iceberg, just time passing
        later_time = self.now + 5000
        self.detector.detect_icebergs.return_value = []
        decayed_score = self.scorer.compute_score(current_time=later_time)

        self.assertLess(decayed_score['bid'], initial_score['bid'])
        self.assertGreater(decayed_score['bid'], 0.0)

    def test_bid_and_ask_independent_scoring(self):
        self.detector.detect_icebergs.return_value = [
            {'side': 'bid', 'total_size': 5, 'duration': 10},  # aggression = 0.5
            {'side': 'ask', 'total_size': 2, 'duration': 10}   # aggression = 0.2
        ]
        score = self.scorer.compute_score(current_time=self.now)
        print(f"Bid: {score['bid']}, Ask: {score['ask']}")
        self.assertGreater(score['bid'], score['ask'])



if __name__ == "__main__":
    unittest.main()
