import unittest
import time
from unittest.mock import MagicMock
from alpha_scoring.order_laddering_scorer import LadderingScorer

class TestLadderingScorer(unittest.TestCase):
    def setUp(self):
        self.detector = MagicMock()
        self.scorer = LadderingScorer(detector=self.detector, base_score=1.0, decay_half_life=8000)
        self.now = int(time.time() * 1000)

    def test_no_sequences_yields_zero_score(self):
        self.detector.detect_laddering_sequeces.return_value = []
        score = self.scorer.compute_score(current_time=self.now)
        self.assertEqual(score['ask'], 0.0)
        self.assertEqual(score['bid'], 0.0)

    def test_basic_laddering_score(self):
        self.detector.detect_laddering_sequeces.return_value = [{
            'side': 'bid',
            'direction': 'up',
            'types': ['LADDER_CANCEL_ONLY'],
            'count': 5,
            'duration_ms': 1000
        }]
        score = self.scorer.compute_score(current_time=self.now)
        expected = min(1.0, 1.0 * 1.2 * 1.0 * (5 / 1001))
        self.assertAlmostEqual(score['bid'], expected)
        self.assertEqual(score['ask'], 0.0)

    def test_directional_bias(self):
        up_seq = {
            'side': 'ask',
            'direction': 'up',
            'types': ['LADDER_CANCEL_ONLY'],
            'count': 5,
            'duration_ms': 1000
        }
        down_seq = {
            'side': 'ask',
            'direction': 'down',
            'types': ['LADDER_CANCEL_ONLY'],
            'count': 5,
            'duration_ms': 1000
        }
        self.detector.detect_laddering_sequeces.return_value = [up_seq]
        up_score = self.scorer.compute_score(current_time=self.now)

        self.scorer = LadderingScorer(detector=self.detector)  # reset state
        self.detector.detect_laddering_sequeces.return_value = [down_seq]
        down_score = self.scorer.compute_score(current_time=self.now)

        self.assertGreater(up_score['ask'], down_score['ask'])

    def test_aggression_type_effect(self):
        cancel_only = {
            'side': 'bid',
            'direction': 'up',
            'types': ['LADDER_CANCEL_ONLY'],
            'count': 5,
            'duration_ms': 1000
        }
        mixed = {
            'side': 'bid',
            'direction': 'up',
            'types': ['LADDER_CANCEL_AND_ADD'],
            'count': 5,
            'duration_ms': 1000
        }
        self.detector.detect_laddering_sequeces.return_value = [cancel_only]
        score_cancel = self.scorer.compute_score(current_time=self.now)

        self.scorer = LadderingScorer(detector=self.detector)
        self.detector.detect_laddering_sequeces.return_value = [mixed]
        score_mixed = self.scorer.compute_score(current_time=self.now)

        self.assertGreater(score_cancel['bid'], score_mixed['bid'])

    def test_score_blending_with_previous(self):
        self.detector.detect_laddering_sequeces.return_value = [{
            'side': 'ask',
            'direction': 'up',
            'types': ['LADDER_CANCEL_ONLY'],
            'count': 10,
            'duration_ms': 1000
        }]
        score1 = self.scorer.compute_score(current_time=self.now)

        later_time = self.now + 1000
        self.detector.detect_laddering_sequeces.return_value = [{
            'side': 'ask',
            'direction': 'up',
            'types': ['LADDER_CANCEL_ONLY'],
            'count': 2,
            'duration_ms': 1000
        }]
        score2 = self.scorer.compute_score(current_time=later_time)

        self.assertLess(score2['ask'], score1['ask'])

    def test_score_decay_over_time(self):
        self.detector.detect_laddering_sequeces.return_value = [{
            'side': 'bid',
            'direction': 'up',
            'types': ['LADDER_CANCEL_ONLY'],
            'count': 10,
            'duration_ms': 1000
        }]
        initial_score = self.scorer.compute_score(current_time=self.now)

        later_time = self.now + 8000
        self.detector.detect_laddering_sequeces.return_value = []
        decayed_score = self.scorer.compute_score(current_time=later_time)

        self.assertLess(decayed_score['bid'], initial_score['bid'])
        self.assertGreater(decayed_score['bid'], 0.0)

    def test_score_caps_at_one(self):
        self.detector.detect_laddering_sequeces.return_value = [{
            'side': 'ask',
            'direction': 'up',
            'types': ['LADDER_CANCEL_ONLY'],
            'count': 1000,
            'duration_ms': 1
        }]
        score = self.scorer.compute_score(current_time=self.now)
        self.assertEqual(score['ask'], 1.0)

if __name__ == "__main__":
    unittest.main()
