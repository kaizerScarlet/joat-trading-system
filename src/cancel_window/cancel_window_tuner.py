from typing import List, Dict
from cancel_window.simple_cancel_window import SimpleCancelWindow
from sklearn.metrics import precision_score, recall_score, f1_score

class CancelWindowTuner:
    """
    Utility to test different 'window_ms' values for SimpleCancelWindow
    using synthetic L2 messages for spoofing simulation.
    """

    def __init__(self, synthetic_l2_events: List[Dict], ground_truth_labels: List[bool]):
        """
        :param synthetic_l2_events: List of L2 events (dicts) with 'E' and updates under 'a' or 'b'
        :param ground_truth_labels: List of bools, indicating if each cancel is spoofing or not
        """
        assert len(ground_truth_labels) > 0, "Labels cannot be empty"
        self.events = synthetic_l2_events
        self.labels = ground_truth_labels

    def tune(self, candidate_windows: List[int]) -> Dict[int, Dict[str, float]]:
        """
        Runs spoof detection for multiple window sizes and evaluates metrics.
        :param candidate_windows: List of window_ms values to test
        :return: Dict mapping window_ms to precision, recall, f1
        """

        results = {}

        for win in candidate_windows:
            model = SimpleCancelWindow(window_ms=win)

            for evt in self.events:
                model.process_l2_update(evt)

            flags = model.flush_flags()
           # Filter predicted spoof cancels
            cancel_flags = [flag for flag in flags if flag['type'] == 'CANCEL_SPOOF']
            flagged_timestamps = [f['timestamp'] for f in cancel_flags]

            # Identify cancel-type events (i.e. a size of 0)
            cancel_events = [
                evt for evt in self.events
                if evt.get('a') and any(float(size) == 0 for _, size in evt['a'])
            ]

            # Match predictions only to the cancel events
            predictions = [evt['E'] in flagged_timestamps for evt in cancel_events]

            # Score the predictions
            precision = precision_score(self.labels, predictions)
            recall = recall_score(self.labels, predictions)
            f1 = f1_score(self.labels, predictions)

            results[win] = {
                'precision': round(precision, 4),
                'recall': round(recall, 4),
                'f1_score': round(f1, 4)
            }

        return results
