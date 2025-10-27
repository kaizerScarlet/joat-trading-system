import random
from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, Any
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
        max_slip = mid * (self.slippage_bps / 1e4)

        # Base price logic
        if spread_ratio < 0.001:
            base_price = best_ask if side.upper() == "BUY" else best_bid
            adjusted_price = base_price # Skip jitter in tight spreads
        else:
            offset = spread * (1 - fill_prob_target)
            base_price = best_ask - offset if side.upper() == "BUY" else best_bid + offset

            # Jitter logic
            tick_jitter = random.randint(-self.max_jitter_ticks, self.max_jitter_ticks)
            jitter = self.tick_size * tick_jitter
            jitter = max(min(jitter, max_slip), -max_slip)


            # Apply jitter directionally
            adjusted_price = base_price + jitter if side.upper() == "BUY" else base_price - jitter

        # Clamp to mid-relative slippage bounds
        adjusted_price = min(max(adjusted_price, mid - max_slip), mid + max_slip)
        
        # Final enforce before snapping (ensures absolute deviation <= max_slip)
        if side.upper() == "BUY":
            adjusted_price = max(adjusted_price, best_bid)
        else:
            adjusted_price = min(adjusted_price, best_ask)



        # Snap to tick size
        tick = Decimal(str(self.tick_size))
        adjusted_price = float(
            (Decimal(str(adjusted_price)) / tick).to_integral_value(rounding=ROUND_HALF_UP) * tick
        )

        return adjusted_price

    def get_debug_view(self, side: str, orderbook: OrderBookProtocol, fill_prob_target: float) -> Dict[str, Any]:
        best_bid = orderbook.get_best_price("bid")
        best_ask = orderbook.get_best_price("ask")
        mid = (best_bid + best_ask) * 0.5 if best_bid and best_ask else None
        spread = abs(best_ask - best_bid) if best_bid and best_ask else None
        return {
            "tick_size": self.tick_size,
            "max_jitter_ticks": self.max_jitter_ticks,
            "slippage_bps": self.slippage_bps,
            "side": side,
            "best_bid": best_bid,
            "best_ask": best_ask,
            "mid": mid,
            "spread": spread,
            "fill_prob_target": fill_prob_target
        }