from typing import List, Dict

class SignalConfidenceCalibrator:
    """
    Calibrates the confidence of trading signals based on historical performance(precision, recall, etc)

    """
    def __init__(self, base_confidence: float = 0.5):
        """
        :param base_confidence: Default confidence for incoming  signals (0.0 - 1.0)
        """
        self.base_confidence = base_confidence
        self.signal_history: List[dict] = []

    def update_signal_result(self, signal_id: str, was_correct: bool):
        """
        Logs  the result of a signal after execution.
        :param signal_id: Unique identifier for the signal
        :param was_correct: True if the signal was correct, False otherwise
        """

        self.signal_history.append({
            'signal_id': signal_id,
            'was_correct': was_correct
        })

    def compute_adjusted_confidence(self) -> float:
        """
        Computes the adjusted confidence based  on rolling signal success rate.
        :return: Adjusted confidence value (0.0 - 1.0)
        """

        if not self.signal_history:
            return self.base_confidence
        
        successes = sum(1 for s in self.signal_history if s['was_correct'])
        total_signals = len(self.signal_history)
        adjusted_confidence = successes / total_signals
        return round(adjusted_confidence, 4)
    

    def get_current_confidence(self) -> float:
        """
        Get the current confidence level based on historical performance.
        :return: Current confidence level (0.0 - 1.0)
        """
        return self.compute_adjusted_confidence() or self.base_confidence
    

    def reset(self):
        """
        Clear historical signal data.
        """
        self.signal_history.clear()


