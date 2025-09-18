class SlippageModel:
    """
    Very simple impact model:
    - Market orders pay spread/2 + impact proportional to qty vs top-of-book liquidity.
    - Limit orders: expected fill price nudged toward mid by a tiny mean-reversion term.
    Hook into your OrderBook for better depth-aware modelling later.
    """
    def __init__(self, impact_coeff: float = 0.5):
        self.impact_coeff = impact_coeff  # multiplier on qty/liquidity

    def expected_market_slip(self, side: str, mid: float, spread: float, qty: float, top_liquidity: float) -> float:
        half_spread = spread * 0.5
        impact = 0.0 if top_liquidity <= 0 else self.impact_coeff * (qty / top_liquidity) * spread
        # BUY moves up, SELL moves down (cost is positive)
        return half_spread + impact

    def expected_limit_price(self, side: str, base_price: float, mid: float, micro_revert_bps: float = 0.5) -> float:
        # Small pull toward mid to avoid needlessly crossing
        k = micro_revert_bps / 1e4
        if side == "BUY":
            return max(base_price - k * (base_price - mid), 0.0)
        else:
            return max(mid - k * (mid - base_price), 0.0)