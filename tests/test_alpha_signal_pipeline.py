import unittest
from unittest.mock import MagicMock
from alpha_scoring.alpha_pipeline import AlphaSignalPipeline

class TestAlphaSignalPipeline(unittest.TestCase):
    def setUp(self):
        

        # Replace scorers and blender with mocks
        self.cancel_scorer = MagicMock()
        self.layering_scorer = MagicMock()
        self.age_scorer = MagicMock()
        self.blender = MagicMock()


        self.pipeline = AlphaSignalPipeline(
            cancel_scorer=self.cancel_scorer,
            age_scorer=self.age_scorer,
            layering_scorer=self.layering_scorer,
            blender=self.blender
        )

        # Default mock return values per side
        self.pipeline.cancel_scorer.compute_score.return_value = {'ask': 0.6, 'bid': 0.6}
        self.pipeline.layering_scorer.compute_score.return_value = {'ask': 0.4, 'bid': 0.4}
        self.pipeline.age_scorer.compute_score.return_value = {'ask': 0.5, 'bid': 0.5}

    def test_update_market_calls_all_scorers_and_blender(self):
        market_snapshot = {'flag': [
            {'timestamp': 1700000000, 'type': 'LAYER_CANCEL_ONLY', 'price': 100.0, 'size': 5.0, 'side': 'bid'}
        ]}
        timestamp = 1700000000

        self.pipeline.update_market(timestamp, market_snapshot)

        # Ensure register_events was called
        self.pipeline.cancel_scorer.register_events.assert_called()
        self.pipeline.layering_scorer.register_events.assert_called()
        self.pipeline.age_scorer.register_events.assert_called()

        # Ensure compute_score was called per side
        self.pipeline.cancel_scorer.compute_score.assert_any_call(timestamp, 'ask')
        self.pipeline.cancel_scorer.compute_score.assert_any_call(timestamp, 'bid')
        self.pipeline.layering_scorer.compute_score.assert_any_call(timestamp, 'ask')
        self.pipeline.layering_scorer.compute_score.assert_any_call(timestamp, 'bid')
        self.pipeline.age_scorer.compute_score.assert_any_call('ask')
        self.pipeline.age_scorer.compute_score.assert_any_call('bid')

        # Ensure blender received correct signals
        self.pipeline.blender.update_signals.assert_any_call(timestamp, {
            'cancel_activity': 0.6,
            'layering': 0.4,
            'order_age': 0.5
        }, side='ask')

        self.pipeline.blender.update_signals.assert_any_call(timestamp, {
            'cancel_activity': 0.6,
            'layering': 0.4,
            'order_age': 0.5
        }, side='bid')

    def test_get_alpha_signal_delegates_to_blender(self):
        self.pipeline.blender.compute_alpha_score.return_value = {'ask': 0.72, 'bid': 0.68}
        signal = self.pipeline.get_alpha_signal()
        self.assertEqual(signal, {'ask': 0.72, 'bid': 0.68})
        self.pipeline.blender.compute_alpha_score.assert_called_once()

    def test_trade_feedback_updates_blender(self):
        signal_dict = {'cancel_activity': 0.4, 'layering': 0.5, 'order_age': 0.6}
        pnl = -25.0
        self.pipeline.trade_feedback(signal_dict, pnl, side='bid')
        self.pipeline.blender.update_trade_feedback.assert_called_once_with(signal_dict, pnl, side='bid')

    def test_get_debug_returns_blender_debug_view(self):
        self.pipeline.blender.get_debug_view.return_value = {
            'signals': {}, 'weights': {}, 'history': []
        }
        debug = self.pipeline.get_debug()
        self.assertIsInstance(debug, dict)
        self.pipeline.blender.get_debug_view.assert_called_once()

    def test_pipeline_with_zero_scores(self):
        self.pipeline.cancel_scorer.compute_score.return_value = {'ask': 0.0, 'bid': 0.0}
        self.pipeline.layering_scorer.compute_score.return_value = {'ask': 0.0, 'bid': 0.0}
        self.pipeline.age_scorer.compute_score.return_value = {'ask': 0.0, 'bid': 0.0}

        snapshot = {'flag': []}
        ts = 170001000
        self.pipeline.update_market(ts, snapshot)

        self.pipeline.blender.update_signals.assert_any_call(ts, {
            'cancel_activity': 0.0,
            'layering': 0.0,
            'order_age': 0.0
        }, side='ask')

        self.pipeline.blender.update_signals.assert_any_call(ts, {
            'cancel_activity': 0.0,
            'layering': 0.0,
            'order_age': 0.0
        }, side='bid')


    def test_reset_clears_all_modules(self):
        self.pipeline.reset()
        self.pipeline.cancel_scorer.reset.assert_called_once()
        self.pipeline.layering_scorer.reset.assert_called_once()
        self.pipeline.age_scorer.reset.assert_called_once()
        self.pipeline.blender.reset.assert_called_once()

    def test_update_market_with_no_flags(self):
        snapshot = {}  # no 'flag' key
        ts = 170001000
        self.pipeline.update_market(ts, snapshot)
        self.pipeline.blender.update_signals.assert_any_call(ts, {
            'cancel_activity': 0.6,
            'layering': 0.4,
            'order_age': 0.5
        }, side='ask')

    def test_update_market_with_missing_side(self):
        snapshot = {'flag': [{'timestamp': 1700000000, 'type': 'CANCEL', 'price': 99.0}]}
        ts = 1700000000
        self.pipeline.update_market(ts, snapshot)
        self.pipeline.cancel_scorer.register_events.assert_called_with(
            timestamp=1700000000,
            event_type='CANCEL',
            price=99.0,
            size=1.0,
            side='ask'  # default fallback
        )




if __name__ == '__main__':
    unittest.main()
