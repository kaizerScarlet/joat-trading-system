from typing import List, Dict

class SignalConfidenceCalibrator:
    """
    Calibrates the confidence of trading signals based on historical performance(precision, recall, etc)

    """
    def __init__(self, base_confidence: float = 0.5, max_history: int = 100):
        """
        :param base_confidence: Default confidence for incoming  signals (0.0 - 1.0)
        """
        self.base_confidence = base_confidence
        self.max_history = max_history
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

        if len(self.signal_history) > self.max_history:
            self.signal_history.pop(0)

    def compute_adjusted_confidence(self) -> float:
        """
        Computes the adjusted confidence based  on rolling signal success rate.
        :return: Adjusted confidence value (0.0 - 1.0)
        """

        history = self.signal_history[-50:]  #Last 50 signals
        if not history:
            return self.base_confidence
        decay_factor = 0.95
        weighted_success = 0.0
        total_weight = 0.0

        for i, signal in enumerate(reversed(history)):
            weight = decay_factor ** i
            if signal['was_correct']:
                weighted_success += weight
            total_weight += weight

        confidence = weighted_success / total_weight
        return round(confidence, 4)

    def get_current_confidence(self) -> float:
        """
        Get the current confidence level based on historical performance.
        :return: Current confidence level (0.0 - 1.0)
        """
        return self.compute_adjusted_confidence()
    
    def get_confidence_breakdown(self) -> dict:
        recent = self.signal_history[-10:]
        streak = [s['was_correct'] for s in recent]
        return {
            'confidence': self.get_current_confidence(),
            'recent_streak': streak
        }


    def reset(self):
        """
        Clear historical signal data.
        """
        self.signal_history.clear()

    def get_last_signal(self) -> Dict:
        """get last signal for debugging"""
        return self.signal_history[-1] if self.signal_history else {}
    
    def get_summary(self) -> Dict[str, float]:
        """This gives you a quick snapshot for dashboards or audits:"""
        return {
            "total_signals": len(self.signal_history),
            "current_confidence": self.get_current_confidence(),
            "recent_accuracy": round(sum(s["was_correct"] for s in self.signal_history[-10:]) / 10, 4) if len(self.signal_history) >= 10 else None
        }




