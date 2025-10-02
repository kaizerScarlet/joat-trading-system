from typing import Protocol, runtime_checkable

@runtime_checkable
class LatencyModelProtocol(Protocol):
    def sample_ms(self) -> int:
        """Returns a simulated one-way latency in milliseconds, with jitter and tail risk."""
