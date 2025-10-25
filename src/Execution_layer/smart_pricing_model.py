import random
from market_data.orderbook_protocol import OrderBookProtocol

class SmartRepricingModel:
    def __init__(self, tick_size: float = 0.01, max_jitter_ticks: int = 2, slippage_bps: float = 5.0):
        self.tick_size = tick_size
        self.max_jitter_ticks = max_jitter_ticks
        self.slippage_bps = slippage_bps # Convert bps to fraction

    def optimize_price(self, side: str, orderbook:OrderBookProtocol, fill_prob_target: float = 0.6) -> float:
        """
        Computes an optimized limit price based on spread, fill probability, jitter, and slippage cap.
        Returns a tick-aligned price.
        """
        best_bid = orderbook.get_best_price("bid")
        best_ask = orderbook.get_best_price("ask")
        mid = (best_bid + best_ask) * 0.5 if best_bid and best_ask else None

        if not mid or not best_bid or not best_ask:
            return best_ask if side.upper() == "BUY" else best_bid  # fallback

        spread = abs(best_ask - best_bid)
        spread_ratio = spread / mid

        # Base price logic
        if spread_ratio < 0.001:
            base_price = best_ask if side.upper() == "BUY" else best_bid
        else:
            offset = spread * (1 - fill_prob_target)
            base_price = best_ask - offset if side.upper() == "BUY" else best_bid + offset

        # Jitter logic
        tick_jitter = random.randint(-self.max_jitter_ticks, self.max_jitter_ticks)
        jitter = self.tick_size * tick_jitter

       # Slippage cap (bps relative to mid)
        max_slip = mid * self.slippage_bps
        jitter = max(min(jitter, max_slip), -max_slip)

        # Apply jitter directionally
        adjusted_price = base_price + jitter if side.upper() == "BUY" else base_price - jitter

        # Final enforce before snapping (ensures absolute deviation <= max_slip)
        if side.upper() == "BUY":
            adjusted_price = min(max(adjusted_price, best_ask - max_slip), best_ask + max_slip)
        else:
            adjusted_price = min(max(adjusted_price, best_bid - max_slip), best_bid + max_slip)


        # Snap to tick size
        adjusted_price = round(adjusted_price / self.tick_size) * self.tick_size

        return adjusted_price

