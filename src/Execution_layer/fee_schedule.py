class FeeSchedule:
    """
    Store fees in basis points (bps). Keep venue truth here but apply in the coordinator.
    """
    def __init__(self, maker_bps: float = 10.0, taker_bps: float = 10.0):
        self.maker_bps = maker_bps
        self.taker_bps = taker_bps

    def maker_rate(self) -> float:
        """Returns maker fee rate as a decimal (e.g., 0.00010 for 10 bps)."""
        return self.maker_bps / 1e4

    def taker_rate(self) -> float:
        """Returns taker fee rate as a decimal (e.g., 0.0010 for 10 bps)."""
        return self.taker_bps / 1e4