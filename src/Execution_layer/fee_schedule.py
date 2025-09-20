class FeeSchedule:
    """
    Store fees in basis points (bps). Keep venue truth here but apply in the coordinator.
    """
    def __init__(self, maker_bps: float = 10.0, taker_bps: float = 10.0):
        self.maker_bps = maker_bps
        self.taker_bps = taker_bps

    def maker_rate(self) -> float:
        return self.maker_bps / 1e4

    def taker_rate(self) -> float:
        return self.taker_bps / 1e4