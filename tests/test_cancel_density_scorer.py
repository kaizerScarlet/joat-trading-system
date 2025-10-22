import unittest
import time
from unittest.mock import MagicMock
from dynamic_risk_engine.cognitive_market_regime_classifier import MarketRegime, CognitiveMarketRegimeClassifier
from cancel_window.cancel_density_detection import CancelDensityDetection
from alpha_scoring.cancel_density_scorer import CancelDensityScorer

class TestCancelDensityScorer(unittest.TestCase):

    def setUp(self):
        mock_regime = MagicMock()
        mock_regime.get_current_regime.return_value = MarketRegime.UNKNOWN
        mock_regime.get_behavioral_overlay.return_value = "NORMAL"

        self.detector = CancelDensityDetection(regime_classifier=mock_regime, window_ms=1000, threshold=4)
        

        self.scorer = CancelDensityScorer(detector=self.detector, base_score=1.0, decay_half_life=5000)
        self.now = int(time.time() * 1000)
    def _register_spike(self, side: str, count: int, unique_prices: int = None, timestamp: int = None):
        unique_prices = unique_prices or count
        timestamp = timestamp or self.now
        for i in range(count):
            self.detector.register_cancel(
                orderid=f"{side}_{i}",
                timestamp=timestamp,
                event_type="CANCEL",
                price=100.0 + i if unique_prices > 1 else 100.0,
                size=1.0,
                side=side
            )

  
    def test_empty_detector_yields_zero_score(self):
        score = self.scorer.compute_score(current_time=self.now)
        self.assertEqual(score['ask'], 0.0)
        self.assertEqual(score['bid'], 0.0)

    def test_single_spike_score_calculation(self):
        self._register_spike("bid", count=10, unique_prices=5)
        score = self.scorer.compute_score(current_time=self.now)
        expected = min(1.0, 1.0 * (10 / 5))  # base_score * intensity
        self.assertAlmostEqual(score['bid'], expected)
        self.assertEqual(score['ask'], 0.0)

    def test_score_decay_over_time(self):
        # Initial spike
        self._register_spike("ask", count=10, unique_prices=5, timestamp=self.now)
        initial_score = self.scorer.compute_score(current_time=self.now)

        # No new cancels, after window expiration
        later_time = self.now + 1500
        decayed_score = self.scorer.compute_score(current_time=later_time)

        print(f"Initial score: {initial_score['ask']}")
        print(f"Decayed score: {decayed_score['ask']}")
        self.assertLess(decayed_score['ask'], initial_score['ask'])
        self.assertGreater(decayed_score['ask'], 0.0)





    def test_score_caps_at_one(self):
        self._register_spike("bid", count=100, unique_prices=1)
        score = self.scorer.compute_score(current_time=self.now)
        self.assertEqual(score['bid'], 1.0)

    def test_score_blending_with_previous(self):
        # First spike: strong
        self._register_spike("ask", count=10, unique_prices=10, timestamp=self.now)
        score1 = self.scorer.compute_score(current_time=self.now)

        # Second spike: weaker, after window expiration
        later_time = self.now + 1500
        self._register_spike("ask", count=2, unique_prices=5, timestamp=later_time)
        score2 = self.scorer.compute_score(current_time=later_time)

        print(f"Score1 (strong spike): {score1['ask']}")
        print(f"Score2 (weaker spike + decay): {score2['ask']}")
        self.assertLess(score2['ask'], score1['ask'])  # decay + weaker spike





    def test_bid_and_ask_independent_scoring(self):
        self._register_spike("bid", count=5, unique_prices=5)
        self._register_spike("ask", count=3, unique_prices=5)
        score = self.scorer.compute_score(current_time=self.now)
        self.assertGreater(score['bid'], score['ask'])

if __name__ == "__main__":
    unittest.main()
