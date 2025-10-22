import unittest
import time
from unittest.mock import MagicMock
from alpha_scoring.order_spoofing_scorer import SpoofingScorer  # Adjust import path as needed

class TestSpoofingScorer(unittest.TestCase):
    def setUp(self):
        self.detector = MagicMock()
        self.scorer = SpoofingScorer(spoof_detector=self.detector, base_score=1.0, decay_half_life=5000)
        self.now = int(time.time() * 1000)

    def test_no_clusters_yields_zero_score(self):
        self.detector.detect_spoofing_clusters.return_value = []
        score = self.scorer.compute_score(current_time=self.now)
        self.assertEqual(score['ask'], 0.0)
        self.assertEqual(score['bid'], 0.0)

    def test_basic_spoofing_score(self):
        self.detector.detect_spoofing_clusters.return_value = [{
            'side': 'bid',
            'count': 5,
            'duration_ms': 1000,
            'types': ['CANCEL_SPOOF']
        }]
        score = self.scorer.compute_score(current_time=self.now)
        expected = min(1.0, 1.0 * (5 / 1000) * 1.0)
        self.assertAlmostEqual(score['bid'], expected)
        self.assertEqual(score['ask'], 0.0)

    def test_aggression_type_effect(self):
        cancel_spoof = {
            'side': 'ask',
            'count': 5,
            'duration_ms': 1000,
            'types': ['CANCEL_SPOOF']
        }
        passive_spoof = {
            'side': 'ask',
            'count': 5,
            'duration_ms': 1000,
            'types': ['PASSIVE_SPOOF']
        }

        self.detector.detect_spoofing_clusters.return_value = [cancel_spoof]
        score_cancel = self.scorer.compute_score(current_time=self.now)

        self.scorer = SpoofingScorer(spoof_detector=self.detector)
        self.detector.detect_spoofing_clusters.return_value = [passive_spoof]
        score_passive = self.scorer.compute_score(current_time=self.now)

        self.assertGreater(score_cancel['ask'], score_passive['ask'])

    def test_score_blending_with_previous(self):
        self.detector.detect_spoofing_clusters.return_value = [{
            'side': 'ask',
            'count': 10,
            'duration_ms': 1000,
            'types': ['CANCEL_SPOOF']
        }]
        score1 = self.scorer.compute_score(current_time=self.now)

        later_time = self.now + 1000
        self.detector.detect_spoofing_clusters.return_value = [{
            'side': 'ask',
            'count': 2,
            'duration_ms': 1000,
            'types': ['CANCEL_SPOOF']
        }]
        score2 = self.scorer.compute_score(current_time=later_time)

        self.assertLess(score2['ask'], score1['ask'])

    def test_score_decay_over_time(self):
        self.detector.detect_spoofing_clusters.return_value = [{
            'side': 'bid',
            'count': 10,
            'duration_ms': 1000,
            'types': ['CANCEL_SPOOF']
        }]
        initial_score = self.scorer.compute_score(current_time=self.now)

        later_time = self.now + 5000
        self.detector.detect_spoofing_clusters.return_value = []
        decayed_score = self.scorer.compute_score(current_time=later_time)

        self.assertLess(decayed_score['bid'], initial_score['bid'])
        self.assertGreater(decayed_score['bid'], 0.0)

    def test_score_caps_at_one(self):
        self.detector.detect_spoofing_clusters.return_value = [{
            'side': 'ask',
            'count': 1000,
            'duration_ms': 1,
            'types': ['CANCEL_SPOOF']
        }]
        score = self.scorer.compute_score(current_time=self.now)
        self.assertEqual(score['ask'], 1.0)

    def test_bid_and_ask_independent_scoring(self):
        self.detector.detect_spoofing_clusters.return_value = [
            {'side': 'bid', 'count': 10, 'duration_ms': 1000, 'types': ['CANCEL_SPOOF']},
            {'side': 'ask', 'count': 2, 'duration_ms': 1000, 'types': ['CANCEL_SPOOF']}
        ]
        score = self.scorer.compute_score(current_time=self.now)
        self.assertGreater(score['bid'], score['ask'])

if __name__ == "__main__":
    unittest.main()
