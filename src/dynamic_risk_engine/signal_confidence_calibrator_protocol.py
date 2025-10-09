from typing import Protocol, Dict, runtime_checkable

@runtime_checkable
class SignalConfidenceCalibratorProtocol(Protocol):
    def update_signal_result(self, signal_id: str, was_correct: bool) -> None:
        """Logs the result of a signal after execution."""

    def compute_adjusted_confidence(self) -> float:
        """Computes adjusted confidence based on rolling signal success rate."""

    def get_current_confidence(self) -> float:
        """Returns the current confidence level based on historical performance."""

    def get_confidence_breakdown(self) -> Dict[str, any]:
        """Returns current confidence and recent signal streak breakdown."""

    def reset(self) -> None:
        """Clears historical signal data."""

    def get_last_signal(self) -> Dict:
        """get last signal for debugging"""

    def get_summary(self) -> Dict[str, float]:
        """This gives you a quick snapshot for dashboards or audits:"""
