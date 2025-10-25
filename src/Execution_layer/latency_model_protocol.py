from typing import Protocol, runtime_checkable

@runtime_checkable
class LatencyModelProtocol(Protocol):
    base_ms: float
    jitter_ms: float
    p_tail: float
    tail_multiplier: float

    def sample_ms(self) -> int:
        """Returns a simulated one-way latency in milliseconds, with jitter and tail risk."""
        ...
