import random

class LatencyModel:
    """
    End-to-end one-way latency (decision->exchange). Milliseconds.
    Use lognormal-ish distribution for rare heavier tails.
    """
    def __init__(self, base_ms: float = 20.0, jitter_ms: float = 15.0, p_tail: float = 0.05, tail_multiplier: float = 3.0):
        self.base_ms = base_ms
        self.jitter_ms = jitter_ms
        self.p_tail = p_tail
        self.tail_multiplier = tail_multiplier

    def sample_ms(self) -> int:
        draw = random.uniform(-self.jitter_ms, self.jitter_ms)
        ms = max(0.0, self.base_ms + draw)
        if random.random() < self.p_tail:
            ms *= self.tail_multiplier
        return int(ms)

