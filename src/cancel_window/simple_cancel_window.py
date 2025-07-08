from typing import Dict, Any, List
from .interface import CancelWindow #samefolder

class SimpleCancelWindow(CancelWindow):
    """
    Minimal stub so test and replay-runner import cleanly.
    Replace with real logic later.
    """
    def __init__(self, window_ms: int = 75):
        self.window_ms = window_ms
        self._flags: list[dict] = []

        #-----------------New shadow-book state ---------------------------------
        self.bids: dict[float, float] = {}  #price -> size
        self.asks: dict[float, float] = {}
        self.add_ts: dict[tuple[str, float], int ] = {} #("bid"/"asks", price) -> epoch-ms

    def process_l2_update(self, msg: dict) -> None:
        ts = msg["E"]       # event time
        bid_updates =msg.get("b", [])   #[["30000","1,2"],......]
        asks_updates = msg.get("a", [])
        
        #helper for each side
        def handle(side: str, book:dict, updates):
            for price_str, size_str in updates:
                price = float(price_str)
                size = float(size_str)
                key = (side, price)

                #Add / Modify
                if size > 0:
                    if price not in book:
                        self.add_ts[key] = ts
                    book[price] = size

                #Delete (Cancel)
                else:
                    if price in book:
                        dt = ts - self.add_ts.get(key, ts)
                        if dt < self.window_ms:
                            self._flags.append({
                                "timestamp": ts,
                                "type": "CANCEL_SPOOF",
                                "side": side,
                                "price": price,
                                "latency_ms": dt
                            })
                        #clean up
                        book.pop(price, None)
                        self.add_ts.pop(key, None)
        handle("bid", self.bids, bid_updates)
        handle("ask", self.asks, asks_updates)

    def process_trade(self, trade_msg: Dict[str, Any]) -> None:
        # TODO: add real logic
        pass

    def flush_flags(self) -> List[Dict[str, Any]]:
        out, self._flags = self._flags, []
        return out
    

    def set_window_ms(self, window_ms: int) -> None:
        self._window_ms = window_ms

    def snapshot_state(self) -> Dict[str, Any]:
        #Return minimal state for now
        return {"window_ms": self._window_ms, "flag_count":  len(self._flags)}
