from typing import Protocol, runtime_checkable

@runtime_checkable
class OrderBookProtocol(Protocol):
    def get_midprice(self) -> float:
        """Returns the last computed midprice or 0.0 if unavailable."""

    def get_level_size(self, price: float, side: str) -> float:
        """Returns the size available at a given price level and side."""

    def get_best_price(self, side: str) -> float:
        """Returns the best bid or ask price."""

    def get_estimated_volume(self, side: str) -> float:
        """Returns total volume on a given side of the book."""

    def get_top_liquidity(self, side: str, depth_levels: int = 1) -> float:
        """Returns size available in the top N levels."""

    def get_liquidity_within_bps(self, side: str, bps: float) -> float:
        """Returns total liquidity within X basis points of midprice."""

    def get_order_imbalance(self) -> float:
        """Returns order book imbalance score (0.0 to 1.0)."""

    def get_volatility_estimate(self) -> float:
        """Returns short-term volatility estimate based on midprice history."""

    def get_update_rate(self) -> float:
        """Returns update frequency (ticks/sec)."""

    def get_tick_size(self) -> float:
        """Returns the smallest tick size used for the symbol."""
