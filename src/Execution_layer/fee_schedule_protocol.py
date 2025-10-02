from typing import Protocol, runtime_checkable

@runtime_checkable
class FeeScheduleProtocol(Protocol):
    def maker_rate(self) -> float:
        """Returns maker fee rate as a decimal (e.g., 0.0008 for 8 bps)."""

    def taker_rate(self) -> float:
        """Returns taker fee rate as a decimal (e.g., 0.0010 for 10 bps)."""
