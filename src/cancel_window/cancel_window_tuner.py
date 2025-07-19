import copy
from typing import List, Dict
from  cancel_window.simple_cancel_window import SimpleCancelWindow
from sklearn.metrics import precision_score, recall_score, f1_score


class CancelWindowTuner:
    """
    Utility to test different 'window_ms' values for SimpleCancelWindow
    using historical event data and known spoofing labels.
    """

    def __init__(self, historical_events: List[dict], ground_truth_labels: List[bool]):
        """
        :params historical_events: A list of dicts with keys: 'timestamop', 'price', 'side', 'size'
        :params ground_truth_labels: A list of bools, indicating if each cancel is spoofing or not
        """

        assert len(historical_events) == len(ground_truth_labels), \
            "Event count and label count must match"
        self.events = historical_events
        self.labels = ground_truth_labels

    def tune(self, candidate_windows: List[int]) -> Dict[int, Dict[str, float]]:
        """
        Runs spoof detection for multiple window size and evaluates metrics.
        :param candidate_windows: List of window_ms values to test
        :return: Dict mapping window_ms to evaluation metrics (precison, recall, f1)
        """

        results = {}

        for win in candidate_windows:
            model = SimpleCancelWindow(window_ms=win)
            predictions = []

            for evt in self.events:
                model.register_cancel(
                    price = evt['price'],
                    side = evt['side'],
                    timestamp= evt['timestamp'],
                    size = evt['size']
                )
                #Optionally flush flags immediately for per-event detection
                flags = model.flush_flags()
                predicted = any(flag['price'] == evt['price'] and flag['side'] == evt['side'] for flag in flags)
                predictions.append(predicted)

            #Score against ground_truth
            precision = precision_score(self.labels, predictions)
            recall = recall_score(self.labels, predictions)
            f1 = f1_score(self.labels, predictions)


            results[win] = {
                'precision': round(precision, 4),
                'recall': round(recall, 4),
                'f1_score': round(f1, 4)


            } 

        return results