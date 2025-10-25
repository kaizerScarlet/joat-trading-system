from typing import Protocol, runtime_checkable

@runtime_checkable
class SlippageModelProtocol(Protocol):
    impact_coeff: float
    def expected_market_slip(
        self,
        side: str,
        mid: float,
        spread: float,
        qty: float,
        top_liquidity: float
    ) -> float:
        """
        Estimates market order slippage cost:
        - spread/2 + impact based on qty vs top liquidity.
        """

    def expected_limit_price(
        self,
        side: str,
        base_price: float,
        mid: float,
        micro_revert_bps: float
    ) -> float:
        """
        Estimates limit order price nudged toward mid by a micro-reversion term.
        
        """
