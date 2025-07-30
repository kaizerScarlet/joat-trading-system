from typing import Dict, Any, List, Tuple
from .interface import CancelWindow #samefolder
from collections import defaultdict
from datetime import datetime
import time 
import math 

# ====== adaptive_density_tuner.py
class AdaptiveDensityWindow:
    def __init__(self, initial_window_ms: int = 100, decay: float = 0.1):
        self.current_window = initial_window_ms
        self.decay = decay 

    def update(self, ts: float, recent_cancel_rate: float):
        #assume cancel rate is in cancels per second
        ideal_window = max(25, min(500, 1000) / (recent_cancel_rate + 1e-6))
        self.current_window = (1 - self.decay) * self.current_window + self.decay * ideal_window

    def get_current_window(self) -> int:
        return int(self.current_window)
    
# ======Adaptive Threshold ============
class AdaptiveThreshold:
    def __init__(self, initial_threshold: int = 3, decay: float = 0.1):
        self.threshold = initial_threshold
        self.decay = decay 

    def update(self, volume: float, volatility: float):
        #Simple heuristic: increase threshold when volume or volatility is high
        factor = 1 + 0.5 * math.tanh(volume * volatility)
        adjusted = max(2, min(10, factor * self.threshold))
        self.threshold = (1 - self.decay) * self.threshold + self.decay *adjusted

    def get_threshold(self) -> int:
        return int(self.threshold)
    

# ========== adaptive_fill_threshold ============
class FillThresholdTuner:
    def __init__(self, initial_ratio: float = 0.9, decay: float = 0.05):
        self.ratio = initial_ratio 
        self.decay = decay 

    def update(self, avg_trade_size: float, volatility: float):
        #Reduce threshold slightly in high volatility to allow more fills
        adjustment = max(0.7, min(0.98, self.ratio - 0.1 * math.tanh(volatility)))
        self.ratio = (1 - self.decay) * self.ratio + self.decay * adjustment 

    def get_ratio(self) -> float :
        return self.ratio

# ===== CancelWindowTuner (inline) ========
class CancelWindowTuner:
    def __init__(self, ema_alpha: float = 0.2, min_ms: int = 25, max_ms: int = 150):
        self.ema_latency = None
        self.ema_alpha = ema_alpha
        self.min_ms = min_ms
        self.max_ms = max_ms 

    def update(self, latency_ms: float):
        if self.ema_latency is None:
            self.ema_latency = latency_ms
        else:
            self.ema_latency = (
                self.ema_alpha * latency_ms + (1 - self.ema_alpha) * self.ema_latency
            )
        self.ema_latency = max(self.min_ms, min(self.ema_latency, self.max_ms))
    
    def current_window_ms(self) -> int :
        return int(self.ema_latency or 75)
    
# ===== Main Class ======

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
    def __init__(self):
        
        self.adaptive = True
        self.window_ms = None
        self.tuner = CancelWindowTuner() if self.adaptive else None

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
        self.cancel_density_threshold = AdaptiveThreshold(initial_threshold=3) #Example: 3 cancels in the last 100ms
        self.cancel_density_window_ms = AdaptiveDensityWindow(initial_window_ms=75) #Timewindow to evaluate density 

        #----------------------------NOT YET SEEN WHAT IT DOES-----------------------#
        self.cancel_events = []
        self.fill_events = []
        self.midprice = None
        self.orderbook = None   # to be injected/ set externally
        #---------------------------------------------------------------------------#

        #Add Iceberg Cancel Buffer
        self.iceberg_buffer = defaultdict(list) # (price, side) -> List(Dict)




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

                        #---Adaptive tuner update -------
                        if self.adaptive and dt >= 0:
                            self.tuner.update(dt)
                            self.window_ms = self.tuner.current_window_ms()

                        # cache the cancel for a potential trade match
                        self.cancel_cache[key] = (ts, removed_size)
                        #Iceberg detection: multiple reductions before cancel
                        reductions = self.reduction_history.get(key, [])
                        if len(reductions) >= 2 and dt < self.get_window_ms():    #Iceberg flag
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
                            if ts - t <= self.cancel_density_window_ms.get_current_window()
                        ]

                        recent_cancel_rate = len(recent_cancels) / (self.cancel_density_window_ms.get_current_window() / 1000)
                        self.cancel_density_window_ms.update(ts, recent_cancel_rate)

                        vol = self.orderbook.get_estimated_volume(side)
                        volty = self.orderbook.get_volatility_estimate()
                        self.cancel_density_threshold.update(vol, volty)


                        if len(recent_cancels) >= self.cancel_density_threshold.get_threshold():
                            self._flags.append({
                                "timestamp": ts,
                                "type": "HIGH_CANCEL_DENSITY",
                                "side": side,
                                "price": price,
                                "count": len(recent_cancels),
                                "density_window_ms": self.cancel_density_window_ms.get_current_window(),
                            })

                        # Clean up
                        book.pop(price, None)
                        self.add_ts.pop(key, None)
                        self.reduction_history.pop(key, None)

        _handle("bid", self.bids, bid_updates)
        _handle("ask", self.asks, asks_updates)
        
        #Detect excessive cancel density
        density = self.compute_cancel_density()  #you can parameterize this too
        for (side, price), count in density.items():
            if count >= self.cancel_density_threshold.get_threshold(): #Set a meaningful threshold
                self._flags.append({
                    "timestamp": msg["E"],
                    "type": "CANCEL_DENSITY_SPIKE",
                    "side": side,
                    "price": price,
                    "cancel_count": count,
                    "window_ms": self.cancel_density_window_ms.get_current_window()
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

            if self.adaptive and dt >= 0:
                self.tuner.update(dt)
                self.window_ms = self.tuner.current_window_ms()

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
        #return current flags and clears them (destructive)
        #Use in streaming or batch mode, where flags should be consumed once
        out, self._flags = self._flags, []
        return out
    
    def get_flags(self) -> list[dict]:
        #returns current flags only (Non-destructive)
        #Use to inspect flags multiple times or during testing/debugging
        flags = self._flags[:]
        self._flags.clear()
        return flags
    

    def set_window_ms(self) -> None:
        self.window_ms = self.tuner.current_window_ms()

    def get_window_ms(self) -> int:
        return self.tuner.current_window_ms()


    def snapshot_state(self) -> Dict[str, Any]:
        #Return minimal state for now
        return {
            "window_ms": self.get_window_ms(),
            "flag_count":  len(self._flags),
            "bids": len(self.bids),
            "asks": len(self.asks),
            "cancel_cache": len(self.cancel_cache),
            "flags": self.get_flags(),
            "cancel_density": self.compute_cancel_density()
            

        }
    
    def compute_cancel_density(self) -> Dict[Tuple[str, float], int]:
        """
        Compute how many cancels occured at each (side, price) level in the past window 'self.get_window_ms()'
        """
        now = max((ts for timestamps in self.cancel_timestamps.values() for ts in timestamps), default=0)
        cutoff = now - self.get_window_ms()
        cancel_density: Dict[Tuple[str, float], int] = {}

        for key, timestamps in self.cancel_timestamps.items():
            #count how many timestamps fall within the window
            recent_cancels = [ts for ts in timestamps if ts >= cutoff]
            if recent_cancels:
                cancel_density[key] = len(recent_cancels)
        
        return cancel_density
    
    def set_cancel_density_params(self, initial_threshold: int, initial_window_ms: int) -> None:
        self.cancel_density_threshold = AdaptiveThreshold(initial_threshold=3) #Example: 3 cancels in the last 100ms
        self.cancel_density_window_ms = AdaptiveDensityWindow(initial_window_ms=75) #Timewindow to evaluate density 



    #-------------------------------------------------------------
    # Register Cancel
    #---------------------------------------------------------

    def register_cancel(self, timestamp: int, price: float, side: str, size: float) -> None:
        """
        Registers a cancel event with metadata
        """
        #Store Cancel
        event = {
            'price': price,
            'side': side,
            'timestamp': timestamp,
            'size': size}
        self.cancel_events.append(event)
        #Buffer cancels for ice detection
        key = (price, side)
        self.iceberg_buffer[key].append(event)

        #Prune Old Ones
        self.iceberg_buffer[key] = [
            e for e in self.iceberg_buffer[key]
            if timestamp - e["timestamp"] <= self.get_window_ms()
        ]

        #Trigger detection
        self._detect_iceberg_cancel(key)

    def _detect_iceberg_cancel(self, key: Tuple[float, str]) -> None:
        events = self.iceberg_buffer[key]
        if len(events) <3:
            return
        total_size = sum(e['size'] for e in events)
        unique_ts = len(set(e['timestamp'] for e in events))

        if total_size >= 10.0 and unique_ts > 1:
            self._flags.append({
                "type": "ICEBERG_CANCEL",
                "price": key[0],
                "side": key[1],
                "size": total_size,
                "count": len(events),
                "timestamp": events[-1]["timestamp"]


            })

            #Clear to avoid double reporting
            self.iceberg_buffer[key].clear()


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

    #revist to ensure if this is complete
    def update_book(self, mid_price: float):
        """Update mid price for cancel impact scoring """
        self._mid_price = mid_price

    
    def compute_cancel_impact_score(self, price: float, side: str) -> float:
        """Compute the impact score of cancels at a given price level and side.
        The higher the score, the more market-impacting the cancel is.
        """

        # --- Step 1: Normalize Cancel Density -----
        density = self.get_cancel_density(side)
        total_cancels = sum(density.values()) or 1e-9
        norm_density = density.get(price, 0) / total_cancels

        # ------ Step 2: Distance from Midprice -----
        if self.midprice is None:
            dist_from_mid = 0.5 # Neutral
        else:
            max_rel_dist = 0.02 #2%
            rel_dis = abs(price - self.midprice) / self.midprice
            dist_from_mid = max(0.0, 1.0 - min(rel_dis / max_rel_dist)) # mapped to [0,1]

        # ------Step 3: Recent Fills at that Price ----
        recent_fills = [f for f in self.fill_events if f['price'] == price and f['side'] == side]
        fill_score = min(len(recent_fills) / 5, 1.0)    #normalize

        # ------Step 4: Inverse Book Depth at Price ----
        """Still need to implement the orderbook.get_level_size(price, size)"""
        size_at_price = self.orderbook.get_level_size(price, side) or 1e-9
        inv_book_depth = min(1.0 / size_at_price, 1.0)

        # -----Weighted Combination -------
        w1, w2, w3, w4 = 0.6, 0.2, 0.1, 0.1
        score = (
            w1 * norm_density +
            w2 * dist_from_mid +
            w3 * fill_score +
            w4 * inv_book_depth

        )
        return round(score, 4)