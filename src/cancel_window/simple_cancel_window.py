from typing import Dict, Any, List, Tuple
from .interface import CancelWindow #samefolder
from collections import defaultdict
from datetime import datetime

class SimpleCancelWindow(CancelWindow):
    """
    Shadow-book tracker + fast-cancel / fill logic.
    Emits:
        1. CANCEL_SPOOF - size->0 within window_ms
        2. TRUE_FILL - trade size >= removed size inside window_ms
        3. PARTIAL_FILL - trade size < removed size " "
        4. ICERBERG_CANCEL - size is rudeced to zero over multiple orders
        5. HIGH_CANCEL_DENSITY - >= N cancels at the same (side, price) within cancel_density_window_ms
        6. CANCEL_DENSITY_SPIKE -> More than threshold cancels at same level rollwing window
    """
    # -----------------------------------------------------------------------------------------------#
    def __init__(self, window_ms: int = 75):
        self.window_ms = window_ms
        self._flags: List[Dict[str,Any]] = []

        #-----------------New shadow-book state ---------------------------------
        self.bids: Dict[float, float] = {}  #price -> size
        self.asks: Dict[float, float] = {}

        # when a level is first seen
        self.add_ts: Dict[tuple[str, float], int ] = {} #("bid"/"asks", price) -> epoch-ms

        # New -> cache of most-recent cancels so trades can match them
        # key -> ("bid"/"ask", price);  value -> (cancel_ts, removed_size)
        self.cancel_cache: Dict[Tuple[str, float], Tuple[int, float]] = {}

        #New -> Track size reductions (for iceberg detection)
        self.reduction_history: Dict[Tuple[str, float], List[float]] ={}

        #Track timestamps of cancels per level
        self.cancel_timestamps: Dict[Tuple[str, float], List[int]] = {}

        #Dynamic cancel Density Thresholds
        self.cancel_density_threshold = 3 #Example: 3 cancels in the last 100ms
        self.cancel_density_window_ms = 100 #Timewindow to evaluate density 

        #----------------------------NOT YET SEEN WHAT IT DOES-----------------------#
        self.cancel_events = []
        self.fill_events = []
        self.midprice = None
        self.orderbook = None   # to be injected/ set externally
        #---------------------------------------------------------------------------#



    # -------------------------------------------------------------------------------------------------#
    # L2 UPDATES
    # -------------------------------------------------------------------------------------------------#
    def process_l2_update(self, msg: Dict[str, Any]) -> None:
        ts = msg["E"]       # event time
        bid_updates =msg.get("b", [])   #[["30000","1,2"],......]
        asks_updates = msg.get("a", [])
        
        #helper for each side
        def _handle(side: str, book: Dict[float, float], updates):
            for price_str, size_str in updates:
                price = float(price_str)
                size = float(size_str)
                key = (side, price)

                #Add / Modify
                if size > 0:
                    prev_size = book.get(price)

                    # New order
                    if price not in book:
                        self.add_ts[key] = ts
                    else:
                        if prev_size is not None:
                            reduction = prev_size - size
                            if reduction > 0:
                                self.reduction_history.setdefault(key,[]).append(reduction)
                    
                    #Update book
                    book[price] = size

                # size == 0 -> Cancel
                #Delete (Cancel)
                else:
                    if price in book:
                        removed_size = book[price]
                        dt = ts - self.add_ts.get(key, ts)

                        # cache the cancel for a potential trade match
                        self.cancel_cache[key] = (ts, removed_size)
                        #Iceberg detection: multiple reductions before cancel
                        reductions = self.reduction_history.get(key, [])
                        if len(reductions) >= 2 and dt < self.window_ms:    #Iceberg flag
                            self._flags.append({
                                "timestamp": ts,
                                "type": "ICEBERG_CANCEL",
                                "side": side,
                                "price": price,
                                "reductions": reductions,
                                "latency_ms": dt,
                            })

                        elif dt < self.window_ms: #spoof flag
                            self._flags.append({
                                "timestamp": ts,
                                "type": "CANCEL_SPOOF",
                                "side": side,
                                "price": price,
                                "latency_ms": dt
                            })
                        # Record cancel timestamp
                        self.cancel_timestamps.setdefault(key, []).append(ts)
                        #check for high cancel density
                        recent_cancels = [
                            t for t in self.cancel_timestamps[key]
                            if ts -t <= self.cancel_density_window_ms
                        ]
                        if len(recent_cancels) >= self.cancel_density_threshold:
                            self._flags.append({
                                "timestamp": ts,
                                "type": "HIGH_CANCEL_DENSITY",
                                "side": side,
                                "price": price,
                                "count": len(recent_cancels),
                                "density_window_ms": self.cancel_density_window_ms,
                            })

                        # Clean up
                        book.pop(price, None)
                        self.add_ts.pop(key, None)
                        self.reduction_history.pop(key, None)

        _handle("bid", self.bids, bid_updates)
        _handle("ask", self.asks, asks_updates)
        
        #Detect excessive cancel density
        density = self.compute_cancel_density(100)  #you can parameterize this too
        for (side, price), count in density.items():
            if count >= 5: #Set a meaningful threshold
                self._flags.append({
                    "timestamp": msg["E"],
                    "type": "CANCEL_DENSITY_SPIKE",
                    "side": side,
                    "price": price,
                    "cancel_count": count,
                    "window_ms": 100
                })
    
    # --------------------------------------------------------------------------#
    #   TRADES
    # --------------------------------------------------------------------------#
    def process_trade(self, trade_msg: Dict[str, Any]) -> None:
        """
        Match trade to recently-cancelled level to flag true/partial fills.
        """
        ts     = trade_msg["T"]
        price  = float(trade_msg["p"])
        qty    = float(trade_msg["q"])
        side   = "bid" if trade_msg["m"] else "ask"  #side that was removed

        key = (side, price)
        
        #Did we see a cancel at this price recently?
        if key in self.cancel_cache:
            cancel_ts, removed_size = self.cancel_cache.pop(key)
            dt = ts - cancel_ts
            if dt < self.window_ms:
                flag_type = "TRUE_FILL" if qty >= removed_size else "PARTIAL_FILL"
                self._flags.append({
                    "timestamp": ts,
                    "type": flag_type,
                    "side": side,
                    "price": price,
                    "qty": qty,
                    "latency_ms": dt,
                })

            self.add_ts.pop(key, None)  # cleanup
            self.reduction_history.pop(key, None)
    # -----------------------------------------------------------------------------------------------
    # HELPER METHODS
    # -----------------------------------------------------------------------------------------------
    def flush_flags(self) -> List[Dict[str, Any]]:
        out, self._flags = self._flags, []
        return out
    

    def set_window_ms(self, window_ms: int) -> None:
        self.window_ms = window_ms


    def snapshot_state(self) -> Dict[str, Any]:
        #Return minimal state for now
        return {
            "window_ms": self.window_ms,
            "flag_count":  len(self._flags),
            "bids": len(self.bids),
            "asks": len(self.asks),
            "cancel_cache": len(self.cancel_cache),

        }
    
    def compute_cancel_density(self, window_ms: int = 100) -> Dict[Tuple[str, float], int]:
        """
        Compute how many cancels occured at each (side, price) level in the past window 'window-ms'
        """
        now = max((ts for timestamps in self.cancel_timestamps.values() for ts in timestamps), default=0)
        cutoff = now - window_ms
        cancel_density: Dict[Tuple[str, float], int] = {}

        for key, timestamps in self.cancel_timestamps.items():
            #count how many timestamps fall within the window
            recent_cancels = [ts for ts in timestamps if ts >= cutoff]
            if recent_cancels:
                cancel_density[key] = len(recent_cancels)
        
        return cancel_density
    
    def set_cancel_density_params(self, threshold: int, window_ms: int) -> None:
        self.cancel_density_threshold = threshold
        self.cancel_density_window_ms = window_ms


    #-------------------------------------------------------------
    # Register Cancel
    #---------------------------------------------------------

    def register_cancel(self, timestamp: datetime, price: float, side: str, size: float):
        """
        Registers a cancel event with metadata
        """
        self.cancel_events.append({
            'timestamp': timestamp,
            'price': price,
            'side': side.lower(),
            'size': size
        })


    def get_cancel_density(self, side:str) -> dict:
        """
        Returns a dictironary of {price: cancel_count} for the given side
        Helps quantify where cancel activity is concentrated
        """
        density = defaultdict(int)
        for event in self.cancel_events:
            if event['side'] == side:
                price = event['price']
                density[price] +=  1
        return dict(density)
    
    def get_normalized_cancel_density(self):
        """
        Compute normalized cancel density metrics over the current window.
        returns:
            dict: {
                'time_window_ms': int,
                'price_range': float,
                'num_cancels': int,
                'cancel_density_per_sec': float,
                'cancel_density_per_price': float,
                'normalized_score': float
            }
        """
        if not self.cancel_events:
            return{
                'time_window_ms': 0,
                'price_range': 0.0,
                'num_cancels': 0,
                'cancel_density_per_sec': 0.0,
                'cancel_density_per_price': 0.0,
                'normalized_score': 0.0
            }
        
        timestamps = [event['timestamp'] for event in self.cancel_events]
        prices = [event['price'] for event in self.cancel_events]

        time_window_ms = max(timestamps) - min(timestamps)
        price_range = max(prices) - min(prices)

        num_cancels = len(self.cancel_events)
        time_window_sec = time_window_ms / 1000.0 if time_window_ms > 0 else 1e-3
        price_range = price_range if price_range > 0 else 1e-3  # avoid division by zero

        cancel_density_per_sec = num_cancels / time_window_sec
        cancel_density_per_price = num_cancels / price_range 

        #Optional Composite score
        normalized_score = (cancel_density_per_sec + cancel_density_per_price) / 2

        return{
            'time_window_ms': time_window_ms,
            'price_range': price_range,
            'num_cancels': num_cancels,
            'cancel_density_per_sec': cancel_density_per_sec,
            'cancel_density_per_price': cancel_density_per_price,
            'normalized_score': normalized_score
        }
    
    def flush(self):
        self.cancel_events.clear()
        self.fill_events.clear()