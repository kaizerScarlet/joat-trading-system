import unittest
from unittest.mock import MagicMock
from alpha_scoring.alpha_pipeline import AlphaSignalPipeline

class TestAlphaSignalPipeline(unittest.TestCase):
    def setUp(self):
        self.cancel_scorer = MagicMock()
        self.cancel_density_scorer = MagicMock()
        self.layering_scorer = MagicMock()
        self.order_ladder_scorer = MagicMock()
        self.age_scorer = MagicMock()
        self.iceberg_scorer = MagicMock()
        self.order_spoofing_scorer = MagicMock()
        self.synthetic_fill_scorer = MagicMock()
        self.blender = MagicMock()

        self.pipeline = AlphaSignalPipeline(
            cancel_scorer=self.cancel_scorer,
            cancel_density_scorer=self.cancel_density_scorer,
            layering_scorer=self.layering_scorer,
            order_ladder_scorer=self.order_ladder_scorer,
            age_scorer=self.age_scorer,
            iceberg_scorer=self.iceberg_scorer,
            order_spoofing_scorer=self.order_spoofing_scorer,
            synthetic_fill_scorer=self.synthetic_fill_scorer,
            blender=self.blender
        )

        # Default mock return values
        self.cancel_scorer.compute_score.return_value = {'ask': 0.6, 'bid': 0.6}
        self.cancel_density_scorer.compute_score.return_value = {'ask': 0.3, 'bid': 0.3}
        self.layering_scorer.compute_score.return_value = {'ask': 0.4, 'bid': 0.4}
        self.order_ladder_scorer.compute_score.return_value = {'ask': 0.2, 'bid': 0.2}
        self.age_scorer.compute_score.return_value = {'ask': 0.5, 'bid': 0.5}
        self.iceberg_scorer.compute_score.return_value = {'ask': 0.1, 'bid': 0.1}
        self.order_spoofing_scorer.compute_score.return_value = {'ask': 0.25, 'bid': 0.25}
        self.synthetic_fill_scorer.compute_score.return_value = {'ask': 0.15, 'bid': 0.15}


    def test_update_market_calls_all_scorers_and_blender(self):
        market_snapshot = {'flag': [
            {'timestamp': 1700000000, 'type': 'CANCEL', 'price': 101.0, 'size': 5.0, 'side': 'ask'}
        ]}
        timestamp = 1700000000

        self.pipeline.update_market(timestamp, market_snapshot)

        # Ensure register_events was called on all scorers
        for scorer in [
            self.cancel_scorer,
            self.cancel_density_scorer,
            self.layering_scorer,
            self.order_ladder_scorer,
            self.age_scorer,
            self.iceberg_scorer,
            self.order_spoofing_scorer,
            self.synthetic_fill_scorer
        ]:
            scorer.register_events.assert_called()

        # Ensure blender received full signal set
        expected_signals = {
            'cancel_activity': 0.6,
            'cancel_density_score': 0.3,
            'layering': 0.4,
            'order_age': 0.5,
            'order_laddering_score': 0.2,
            'iceberg_score': 0.1,
            'order_spoofing_score': 0.25,
            'synthetic_fill_score': 0.15
        }

        self.blender.update_signals.assert_any_call(timestamp, expected_signals, side='ask')
        self.blender.update_signals.assert_any_call(timestamp, expected_signals, side='bid')


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
        # All scorers return zero
        for scorer in [
            self.cancel_scorer,
            self.cancel_density_scorer,
            self.layering_scorer,
            self.order_ladder_scorer,
            self.age_scorer,
            self.iceberg_scorer,
            self.order_spoofing_scorer,
            self.synthetic_fill_scorer
        ]:
            scorer.compute_score.return_value = {'ask': 0.0, 'bid': 0.0}

        snapshot = {'flag': []}
        ts = 170001000
        self.pipeline.update_market(ts, snapshot)

        expected_signals = {
            'cancel_activity': 0.0,
            'cancel_density_score': 0.0,
            'layering': 0.0,
            'order_age': 0.0,
            'order_laddering_score': 0.0,
            'iceberg_score': 0.0,
            'order_spoofing_score': 0.0,
            'synthetic_fill_score': 0.0
        }

        self.pipeline.blender.update_signals.assert_any_call(ts, expected_signals, side='ask')
        self.pipeline.blender.update_signals.assert_any_call(ts, expected_signals, side='bid')



    def test_reset_clears_all_modules(self):
        self.pipeline.reset()
        self.pipeline.cancel_scorer.reset.assert_called_once()
        self.pipeline.layering_scorer.reset.assert_called_once()
        self.pipeline.age_scorer.reset.assert_called_once()
        self.pipeline.blender.reset.assert_called_once()

    def test_update_market_with_no_flags(self):
        snapshot = {}
        ts = 170001000
        self.pipeline.update_market(ts, snapshot)

        expected_signals = {
            'cancel_activity': 0.6,
            'cancel_density_score': 0.3,
            'layering': 0.4,
            'order_age': 0.5,
            'order_laddering_score': 0.2,
            'iceberg_score': 0.1,
            'order_spoofing_score': 0.25,
            'synthetic_fill_score': 0.15
        }

        self.pipeline.blender.update_signals.assert_any_call(ts, expected_signals, side='ask')
        self.pipeline.blender.update_signals.assert_any_call(ts, expected_signals, side='bid')


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
