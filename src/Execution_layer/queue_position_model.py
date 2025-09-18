from market_data.orderbook import OrderBook


class QueuePositionModel:
    """
    Naive queue estimate: compare our qty to visible top-of-book size.
    Returns (queue_fraction, approx_fill_prob_per_second)
    """
    def __init__(self, base_trade_rate: float = 1.0):
         #fallback if book doesnt provide activity
         self.base_trade_rate = base_trade_rate

    def estimate(self, side: str, our_qty: float, tob_qty: float, orderbook = OrderBook) -> tuple[float, float]:
        """
        :param side: "BUY" or "SELL"
        :param our_qty: how much we want to post
        :param tob_qty: visible top-of-book liquidity
        :param orderbook: optional Orderbook object
        :return: (queue_fraction, approx_fill_prob_per_second)
        """

        if tob_qty <= 0 or our_qty <= 0:
            return 1.0, 0.0  # unknown -> assume back of queue, no info on fill rate
        
        #Fraction of top-of-book we represent
        qfrac = min(1.0, our_qty / (tob_qty + 1e-9))

        # Activity-based fill intensity ---
        fill_rate = self.base_trade_rate
        if orderbook is not None:
             #Use observed update rate as proxy for consumption
             upd_rate = orderbook.get_update_rate() #Updates/sec
             imb = orderbook.get_order_imbalance() #0..1
             vol = orderbook.get_volatility_estimate()

             #crude heuristic: higher update rate + higher vol -> faster fills
             #imbalance tilt: if we're on the favoured side, more fills
             side_factor = imb if side.upper() == "SELL" else (1.0 - imb)

             fill_rate = max(0.1, upd_rate * (1 + 5 * vol) * (1 + side_factor))

        # Scale by our share of the queue
        p = min(1.0, qfrac * fill_rate)
        return qfrac, p
