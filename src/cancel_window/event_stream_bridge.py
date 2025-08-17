from cancel_window.simple_cancel_window import SimpleCancelWindow
from cancel_window.order_age_distribution import OrderAgeDistribution
from cancel_window.order_layering_detection import OrderLayeringDetection
from typing import Dict, Any

class EventStreamBridge:
    def __init__(self,
                 cancel_window: SimpleCancelWindow,
                 layering_detector: OrderLayeringDetection,
                 order_age_tracker: OrderAgeDistribution):
        self.cancel_window = cancel_window
        self.layering_detector = layering_detector
        self.order_age_tracker = order_age_tracker

    def process_l2_update(self, msg: Dict[str, Any]):
        ts = msg["E"]
        self.cancel_window.process_l2_update(msg)

        for side_key in ["b", "a"]:  # bid/ask
            updates = msg.get(side_key, [])
            side = "b" if side_key == "b" else "a"

            for price_str, size_str in updates:
                price = float(price_str)
                size = float(size_str)

                if size > 0:
                    # REGISTER NEW ORDER
                    self.layering_detector.register_order(ts, price, size, side)
                    self.order_age_tracker.register_event(ts, price, size, side)

                else:
                    # REGISTER CANCEL
                    event_type = "cancel"
                    distance_from_best = 0  # You can compute this with OrderBook if available
                    self.layering_detector.register_cancel(ts, event_type, price, size, side)
                    self.order_age_tracker.cancel_order(ts, event_type, price, size, distance_from_best, side)

    def process_trade(self, trade_msg: Dict[str, Any]):
        self.cancel_window.process_trade(trade_msg)

        ts = trade_msg["T"]
        price = float(trade_msg["p"])
        size = float(trade_msg["q"])
        side = "b" if trade_msg["m"] else "a"

        event_type = "fill"
        distance_from_best = 0  # Optional, update using OrderBook if needed

        self.layering_detector.register_fill(ts, event_type, price, size, side)
        self.order_age_tracker.fill_order(ts, event_type, price, size, distance_from_best, side)
