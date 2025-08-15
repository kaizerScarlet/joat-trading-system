import unittest
from unittest.mock import MagicMock
from alpha_scoring.alpha_pipeline import AlphaSignalPipeline


class TestAlphaSignalPipeline(unittest.TestCase):
    def setUp(self):
        """Initialize pipeline with mocked scorers and blender"""
        self.pipeline =AlphaSignalPipeline()

        #Replace real scorers with mocks
        self.pipeline.cancel_scorer = MagicMock()
        self.pipeline.age_scorer = MagicMock()
        self.pipeline.layering_scorer = MagicMock()
        self.pipeline.blender = MagicMock()


        #Default mock return values for scorers
        self.pipeline.cancel_scorer.compute_score.return_value = 0.6
        self.pipeline.layering_scorer.compute_score.return_value = 0.4
        self.pipeline.age_scorer.compute_score.return_value = 0.5

    def test_update_market_calls_all_scorers(self):
        """Ensure update market calls each scorer and passes signals to blender."""
        market_snapshot = {'book': {}, 'trades': []}
        timestamp =1699999999

        self.pipeline.update_market(timestamp, market_snapshot)

        self.pipeline.cancel_scorer.compute_score.assert_called_once_with(market_snapshot)
        self.pipeline.layering_scorer.compute_score.assert_called_once_with(market_snapshot)
        self.pipeline.age_scorer.compute_score.assert_called_once_with(market_snapshot)

        self.pipeline.blender.update_signals.assert_called_once_with(timestamp, {
            'cancel_activity': 0.6,
            'layering': 0.4,
            'order_age': 0.5
        })

    
    def test_get_alpha_signal_delegates_to_blender(self):
        """Ensure get_alpha_signal returns output from blender."""
        timestamp = 1700000000
        self.pipeline.blender.compute_alpha_score.return_value = 0.72
        
        score = self.pipeline.get_alpha_signal()

        self.pipeline.blender.compute_alpha_score.assert_called_once_with(timestamp)
        self.assertEqual(score, 0.72)


    def test_trade_feedback_updates_blender(self):
        """Test that trade feedback is routed to the blender."""
        signal_dict = {
            'cancel_activity': 0.4,
            'layering': 0.5,
            'order_age': 0.6
        }

        pnl = -25.0
        self.pipeline.trade_feedback(signal_dict, pnl)
        self.pipeline.blender.update_trade_feedback.assert_called_once_with(signal_dict, pnl)

    
    def test_get_debug_returns_blender_debug_view(self):
        """Ensure get_debug returns blender internals."""
        self.pipeline.blender.get_debug_view.return_value = {
            'signals': {},
            'weights': {},
            'history': []
        }

        debug = self.pipeline.get_debug()
        self.assertIsInstance(debug, dict)
        self.pipeline.blender.get_debug_view.assert_called_once()


    def test_pipeline_with_zero_scores(self):
        """Test pipeline when all scorers return zero."""
        self.pipeline.cancel_scorer.compute_score.return_value = 0.0
        self.pipeline.layering_scorer.compute_score.return_value = 0.0
        self.pipeline.age_scorer.compute_score.return_value = 0.0   


        snapshot = {'book': {}, 'trades': []}
        ts = 170001000
        self.pipeline.update_market(ts, snapshot)

        self.pipeline.blender.update_signals.assert_called_once_with(ts, {
            'cancel_activity': 0.0,
            'layering': 0.0,
            'order_age': 0.0
        })


    if __name__ == '__main__':
        unittest.main()    
    
