import unittest
import time
from unittest.mock import MagicMock
from alpha_scoring.synthetic_fill_scorer import SyntheticFillScorer  # Adjust path if needed

class TestSyntheticFillScorer(unittest.TestCase):
    def setUp(self):
        self.detector = MagicMock()
        self.scorer = SyntheticFillScorer(detector=self.detector, base_score=1.0, decay_half_life=5000)
        self.now = int(time.time() * 1000)

    def test_no_anomalies_yields_zero_score(self):
        self.detector.detect_anomalies.return_value = []
        score = self.scorer.compute_score(current_time=self.now)
        self.assertEqual(score['ask'], 0.0)
        self.assertEqual(score['bid'], 0.0)

    def test_basic_anomaly_score(self):
        self.detector.detect_anomalies.return_value = [{
            'side': 'bid',
            'weak_fills': 5,
            'true': 10
        }]
        score = self.scorer.compute_score(current_time=self.now)
        expected = min(1.0, 1.0 * (5 / 10))
        self.assertAlmostEqual(score['bid'], expected)
        self.assertEqual(score['ask'], 0.0)

    def test_score_caps_at_one(self):
        self.detector.detect_anomalies.return_value = [{
            'side': 'ask',
            'weak_fills': 1000,
            'true': 1
        }]
        score = self.scorer.compute_score(current_time=self.now)
        self.assertEqual(score['ask'], 1.0)

    def test_score_blending_with_previous(self):
        self.detector.detect_anomalies.return_value = [{
            'side': 'ask',
            'weak_fills': 10,
            'true': 10
        }]
        score1 = self.scorer.compute_score(current_time=self.now)

        later_time = self.now + 1000
        self.detector.detect_anomalies.return_value = [{
            'side': 'ask',
            'weak_fills': 2,
            'true': 10
        }]
        score2 = self.scorer.compute_score(current_time=later_time)

        self.assertLess(score2['ask'], score1['ask'])

    def test_score_decay_over_time(self):
        self.detector.detect_anomalies.return_value = [{
            'side': 'bid',
            'weak_fills': 10,
            'true': 10
        }]
        initial_score = self.scorer.compute_score(current_time=self.now)

        later_time = self.now + 5000
        self.detector.detect_anomalies.return_value = []
        decayed_score = self.scorer.compute_score(current_time=later_time)

        self.assertLess(decayed_score['bid'], initial_score['bid'])
        self.assertGreater(decayed_score['bid'], 0.0)

    def test_bid_and_ask_independent_scoring(self):
        self.detector.detect_anomalies.return_value = [
            {'side': 'bid', 'weak_fills': 10, 'true': 10},
            {'side': 'ask', 'weak_fills': 2, 'true': 10}
        ]
        score = self.scorer.compute_score(current_time=self.now)
        self.assertGreater(score['bid'], score['ask'])

if __name__ == "__main__":
    unittest.main()
