from typing import Dict, Any, List, Tuple, Optional
from .interface import CancelWindow #samefolder
from collections import defaultdict
from datetime import datetime
import time 
import math 
import uuid

from dynamic_risk_engine.cognitive_market_regime_classifier_protocol import CognitiveMarketRegimeClassifierProtocol, MarketRegime
from market_data.orderbook_protocol import OrderBookProtocol
from cancel_window.order_age_distribution_protocol import OrderAgeDistributionProtocol
from cancel_window.order_layering_detection_protocol import OrderLayeringDetectionProtocol
from cancel_window.order_laddering_detection_protocol import OrderLadderingDetectionProtocol
from cancel_window.synthetic_fill_detector import SyntheticFillDetection

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
    
    def get_debug_view(self) -> Dict[str, Any]:
         return {
            "current_window_ms": self.get_current_window(),
            "decay": self.decay
        }

    
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

    def get_debug_view(self) -> Dict[str, Any]:
        return {
            "threshold": self.get_threshold(),
            "decay": self.decay
        }

    

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
    
    def get_debug_view(self) -> Dict[str, Any]:
        return {
            "fill_ratio": self.get_ratio(),
            "decay": self.decay
        }


class CancelWindowTunerForLayering:
    def __init__(self, ema_alpha: float = 0.2, min_ms: int = 100, max_ms: int = 350):
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
        return int(self.ema_latency or self.min_ms)

    def get_debug_view(self) -> Dict[str, Any]:
        return {
            "ema_latency": self.ema_latency,
            "current_window_ms": self.current_window_ms(),
            "min_ms": self.min_ms,
            "max_ms": self.max_ms,
            "ema_alpha": self.ema_alpha
        }


# ===== CancelWindowTuner (inline) ========
class CancelWindowTuner:
    def __init__(self, ema_alpha: float = 0.2, min_ms: int = 50, max_ms: int = 75):
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
        return int(self.ema_latency or self.min_ms)
    
    
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
        7. MULTILEVEL_LADDERING -> Placing multiple orders across several adjacent price levels on one side (bid or ask) in rapid succession to simulate strong or selling interest with the intent to fill them
        8. LADDER_CANCEL_ONLY
        9. FILL_NO_CANCEL_CACHE -> for stealth fills near top of book
        10. LADDER_TRUE_FILL
        11. LADDER_PARTIAL_FILL
        12. REPOSTING_BEHAVIOR -> Cancel at nearby price, then re-add at same / nearby price (spoofing or layering)
        13. LAYER_WIPE -> Canceling several prices at once in a singl direction (layer wipe)1
        14. BURST_CANCEL -> Very rapid cancels across multiple levels (cancel sweep)
        15. PING_CANCEL -> Orders placed for very short time (ping for liquidity)
    """
    # -----------------------------------------------------------------------------------------------#
    def __init__(self, tuner: CancelWindowTuner, order_layering:OrderLayeringDetectionProtocol,
                  order_ladder_tracker: OrderLadderingDetectionProtocol,
                  synthetic_fill_detector: SyntheticFillDetection,
                  order_age_tracker: OrderAgeDistributionProtocol, 
                  order_book: OrderBookProtocol, classifier: CognitiveMarketRegimeClassifierProtocol, market_type: str = "spot"):
        
        self.adaptive = True
        self.window_ms = None
        self.tuner = tuner if self.adaptive else None

        self.order_layering_tracker = order_layering
        self.order_age_tracker = order_age_tracker
        self.order_ladder_tracker = order_ladder_tracker
        self.synthetic_fill_detector = synthetic_fill_detector

        self._flags: List[Dict[str,Any]] = []

        #-----------------New shadow-book state ---------------------------------
        self.bids: Dict[float, float] = {}  #price -> size
        self.asks: Dict[float, float] = {}

        # when a level is first seen
        self.add_ts: Dict[tuple[str, float], int ] = {} #("bid"/"asks", price) -> epoch-ms

        #Order-ids for order tracking
        self.order_ids: Dict[Tuple[str, float], str] = {}


        # New -> cache of most-recent cancels so trades can match them
        # key -> ("bid"/"ask", price);  value -> (cancel_ts, removed_size)
        self.cancel_cache: Dict[Tuple[str, float], Tuple[int, float]] = {}

        #New -> Track size reductions (for iceberg detection)
        self.reduction_history: Dict[Tuple[str, float], List[float]] ={}

        #Track timestamps of cancels per level
        self.cancel_timestamps: Dict[Tuple[str, float], List[int]] = {}

        #New: track per-redution timestamps
        self.reduction_timestamps: Dict[Tuple[str, float], List[int]] = {}

        #Dynamic cancel Density Thresholds per side
        self.cancel_density_threshold_bid = AdaptiveThreshold(initial_threshold=3) #Example: 3 cancels in the last 100ms
        self.cancel_density_threshold_ask = AdaptiveThreshold(initial_threshold=3)

        self.cancel_density_window_ms = AdaptiveDensityWindow(initial_window_ms=75) #Timewindow to evaluate density 

        #----------------------------NOT YET SEEN WHAT IT DOES-----------------------#
        self.cancel_events = []
        self.fill_events = []
       
        self.regime_classifier = classifier # to be injected/ set externally
        self.orderbook = order_book   # to be injected/ set externally
        self.midprice = self.orderbook.get_midprice()    #injected externally by orderbook
        #---------------------------------------------------------------------------#

        #Add Iceberg Cancel Buffer
        self.iceberg_buffer = defaultdict(list) # (price, side) -> List(Dict)

        # For detecting multilevel laddering
        self.laddering_buffer = [] #For detecting multilevel laddering
        self.active_ladder = None

        self.cancel_density = {"bid": {}, "ask": {}}

        self.market_type = market_type


    def _next_id(self) -> str:
        """Generate Unique ID for orders"""
        return str(uuid.uuid4())



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
                        
                        #Tag order creation for age tracking
                        orderid = self._next_id()
                        self.order_ids[key] = orderid

                        self.order_age_tracker.register_event(orderid=orderid,
                                                            timestamp=ts,
                                                            price=price,
                                                            size=size,
                                                            side=side,
                                                            #distance_from_best=abs(self.orderbook.get_best_price(side) - price)
                                                            )
                        self.order_layering_tracker.register_order(orderid=orderid,
                                                                   timestamp=ts,
                                                                    price=price, size=size,
                                                                    side=side,
                                                                    #distance_from_best=abs(self.orderbook.get_best_price(side) - price)
                                                                    )
                    else:
                        if prev_size is not None:
                            reduction = prev_size - size
                            if reduction > 0:
                                #Tracks if there was a reduction for the iceberg detection
                                self.reduction_history.setdefault(key,[]).append(reduction)
                                self.reduction_timestamps.setdefault(key,[]).append(ts)
                                #Also register each reduction as a small cancel event for iceberg logic
                                self.register_cancel(ts, price, side, reduction)
                    #Update book
                    book[price] = size

                    #Track new laddering levels
                    if prev_size is None:
                        self.laddering_buffer.append({
                            'side': side,
                            'price': price,
                            'timestamp': ts,
                        })
                        self.laddering_buffer = [e for e in self.laddering_buffer if ts - e['timestamp'] <= self.get_window_ms()]
                        recent_levels =[e['price'] for e in self.laddering_buffer if e['side'] == side]
                        if len(set(recent_levels)) >= 3:
                            orderid = self.order_ids.get(key)
                            if not orderid:
                                orderid = self._next_id()
                                self.order_ids[key] = orderid

                            self._flags.append({
                                'type': 'MULTILEVEL_LADDERING',
                                'orderid': orderid,
                                'side': side,
                                'size': size,
                                'price': price,
                                'prices': sorted(set(recent_levels)),
                                'timestamp': ts,
                                'context': {
                                    "window_ms": self.get_window_ms(),
                                    "cancel_density": self.get_cancel_density(side),
                                }
                            })
                            #Pass along to OrderAgeDistribution to tag
                            self.order_age_tracker.cancel_order(orderid=orderid, timestamp=ts, event_type='MULTILEVEL_LADDERING', price=price, size=size, distance_from_best=abs(self.orderbook.get_best_price(side) - price), side=side)
                            self.order_ladder_tracker.register_event(orderid=orderid, timestamp=ts, event_type='MULTILEVEL_LADDERING', price=price, size=size, side=side)
                            
                            self.active_ladder = {
                                'side': side,
                                'price': price,
                                'prices': set(recent_levels),
                                'timestamp': ts,
                                'size': size,
                                'filled': False
                            }

                # size == 0 -> Cancel
                # size == 0 -> Cancel
                else:
                    removed_size = book.get(price, 0.0)  # fallback if price not in book

                    if price in book:
                        removed_size = book[price]

                        # Use last reduction timestamp instead of first add_ts
                        last_reduction_ts = self.reduction_timestamps.get(key, [self.add_ts.get(key)])[-1]
                        if last_reduction_ts is None:
                            return  # skip this cancel if timestamp missing

                        dt = ts - last_reduction_ts

                        # --- Adaptive tuner update -------
                        if self.adaptive and dt >= 0:
                            self.tuner.update(dt)
                            self.window_ms = self.tuner.current_window_ms()

                        # --- Register the cancel BEFORE cleanup ---
                        self.register_cancel(ts, price, side, removed_size)

                        # cache the cancel for a potential trade match
                        self.cancel_cache[key] = (ts, removed_size)

                        # record cancel density
                        self.cancel_density.setdefault(side, {}).setdefault(price, []).append(ts)

                        # --- Spoof cancel detection (short-lived orders) ---
                        if dt < self.get_window_ms():
                            spoof_score = self._quantitative_iceberg_spoof(side, price, dt, removed_size, ts)
                            orderid = self.order_ids.get(key)
                            if not orderid:
                                orderid = self._next_id()
                                self.order_ids[key] = orderid

                            self._flags.append({
                                "timestamp": ts,
                                "orderid": orderid,
                                "type": "CANCEL_SPOOF",
                                "side": side,
                                "size": size,
                                "price": price,
                                "latency_ms": dt,
                                "score": round(spoof_score, 3),
                                "context": {
                                    "window_ms": self.get_window_ms(),
                                    "cancel_density": self.get_cancel_density(side)
                                }
                            })
                            # pass along to OrderAgeDistribution
                            self.order_age_tracker.cancel_order(
                                orderid=orderid,
                                timestamp=ts,
                                event_type="CANCEL_SPOOF",
                                price=price,
                                size=size,
                                distance_from_best=abs(self.orderbook.get_best_price(side) - price),
                                side=side
                            )

                        # --- Record cancel timestamp ---
                        self.cancel_timestamps.setdefault(key, []).append(ts)

                        # --- Ladder cancel tagging ---
                        if self.active_ladder and key[0] == self.active_ladder["side"] and price in self.active_ladder["prices"]:
                            orderid = self.order_ids.get(key)
                            if not orderid:
                                orderid = self._next_id()
                                self.order_ids[key] = orderid

                            self._flags.append({
                                "orderid": orderid,
                                "type": "LADDER_CANCEL_ONLY",
                                "side": side,
                                "size": size,
                                "price": price,
                                "timestamp": ts,
                                "context": {
                                    "window_ms": self.get_window_ms(),
                                    "Cancel Density": self.get_cancel_density(side)
                                }
                            })
                            self.order_age_tracker.cancel_order(
                                orderid=orderid,
                                timestamp=ts,
                                event_type="LADDER_CANCEL_ONLY",
                                price=price,
                                size=size,
                                distance_from_best=abs(self.orderbook.get_best_price(side) - price),
                                side=side
                            )

                            self.order_ladder_tracker.register_event(
                                orderid=orderid,
                                timestamp=ts,
                                event_type="LADDER_CANCEL_ONLY",
                                price=price,
                                size=size,
                                side=side
                            )

                        # --- Cleanup AFTER iceberg and spoof detection ---
                        book.pop(price, None)
                        self.add_ts.pop(key, None)
                        self.reduction_history.pop(key, None)
                        self.reduction_timestamps.pop(key, None)
                        self.order_ids.pop(key, None)



        _handle("bid", self.bids, bid_updates)
        _handle("ask", self.asks, asks_updates)


        if self.active_ladder and ts - self.active_ladder['timestamp'] > 300:
            self.active_ladder = None
        

        # ✅ Automatically evaluate cancel density after every update
        self._detect_cancel_density_spike(ts)
    
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
            cancel_ts, removed_size = self.cancel_cache[key]
            if cancel_ts is None:
                return # Cancel timestamp missing for key at ts
            dt = ts - cancel_ts

            if self.adaptive and dt >= 0:
                self.tuner.update(dt)
                self.window_ms = self.tuner.current_window_ms()
            
            #Spot logic (unchanged)
            if self.market_type == "spot":
                if dt < self.get_window_ms():
                    flag_type = "TRUE_FILL" if qty >= removed_size else "PARTIAL_FILL"
                    orderid = self.order_ids.get(key)
                    if not orderid:
                        orderid = self._next_id()
                        self.order_ids[key] = orderid

                    self._flags.append({
                        'orderid': orderid,
                        "timestamp": ts,
                        "type": flag_type,
                        "side": side,
                        "price": price,
                        "qty": qty,
                        "latency_ms": dt,
                        "context": {
                                        "window_ms": self.get_window_ms(),
                                        "Cancel Density": self.get_cancel_density(side)
                                    }
                    })
                    #Pass along to OrderAgeDistribution to tag
                    self.order_age_tracker.fill_order(orderid=orderid, timestamp=ts, event_type=flag_type, price=price, size=qty, distance_from_best=abs(self.orderbook.get_best_price(side) - price), side=side)

                else:
                    #Fallback detection: fill seen at meaningful price w/o cancel
                    best_price = self.orderbook.get_best_price('ask' if side == 'bid' else 'bid')
                    spread = abs(best_price - price)
                    if spread < 2 * self.orderbook.get_tick_size(): # Near top of book
                        orderid = self.order_ids.get(key)
                        if not orderid:
                            orderid = self._next_id()
                            self.order_ids[key] = orderid

                        self._flags.append({
                            'orderid': orderid,
                            'timestamp': ts,
                            'type': 'FILL_NO_CANCEL_CACHE',
                            'side': side,
                            'price': price,
                            'qty': qty,
                            "context": {
                                        "window_ms": self.get_window_ms(),
                                        "Cancel Density": self.get_cancel_density(side)
                                    }
                        })
                        #Pass along to OrderAgeDistribution to tag
                        self.order_age_tracker.fill_order(orderid=orderid, timestamp=ts, event_type='FILL_NO_CANCEL_CACHE', price=price, size=qty, distance_from_best=abs(self.orderbook.get_best_price(side) - price), side=side)
            
                self.fill_events.append({
                    'timestamp': ts,
                    'price': price,
                    'qty': qty,
                    'side': side
                })

                #Fill  follow-up for laddering
                if self.active_ladder and price in self.active_ladder['prices'] and side == self.active_ladder['side']:
                    self.active_ladder['filled'] = True
                    fill_type = "LADDER_TRUE_FILL" if qty >= self.orderbook.get_level_size(price, side) else 'LADDER_PARTIAL_FILL'
                    orderid = self.order_ids.get(key)
                    if not orderid:
                        orderid = self._next_id()
                        self.order_ids[key] = orderid

                    self._flags.append({
                        'orderid': orderid,
                        'timestamp': ts,
                        'type': fill_type,
                        'side': side,
                        'price': price,
                        'qty': qty,
                        "context": {
                                        "window_ms": self.get_window_ms(),
                                        "Cancel Density": self.get_cancel_density(side)
                                    }
                    })
                    #Pass along to OrderAgeDistribution to tag
                    self.order_age_tracker.fill_order(orderid=orderid, timestamp=ts, event_type=fill_type, price=price, size=qty, distance_from_best=abs(self.orderbook.get_best_price(side) - price), side=side)

                    #Pass along to OrderLadderingDetection to tag
                    self.order_ladder_tracker.register_event(orderid=orderid, timestamp=ts, event_type=fill_type, price=price, size=qty, side=side)

                if self.active_ladder and ts -self.active_ladder['timestamp'] > 300:
                    self.active_ladder =  None

            # Futurres Logic (Synthetic fill estimation)
            else:
                fill_ratio = qty / (removed_size + 1e-6)
                depth_depleted = self.orderbook.get_level_size(price, side) == 0.0
                volatility = self.orderbook.get_volatility_estimate()

                confidence = 0.0
                confidence += 0.3 if dt < self.get_window_ms() else 0.0
                confidence += 0.3 if depth_depleted else 0.0
                confidence += 0.2 if fill_ratio >= 1.0 else 0.1 if fill_ratio >= 0.5 else 0.0
                confidence += 0.2 * (1.0 - volatility)
                confidence = round(min(confidence, 1.0), 3)

                if  fill_ratio >= 1.0:
                    fill_type = "SYNTHETIC_TRUE_FILL"
                elif fill_ratio >= 0.5:
                    fill_type = "SYNTHETIC_PARTIAL_FILL"
                else:
                    fill_type = "SYNTHETIC_WEAK_FILL"
                

                orderid = self.order_ids.get(key)
                if not orderid:
                    orderid = self._next_id()
                    self.order_ids[key] = orderid

                
                # Emit core synthetic fill
                self._flags.append({
                    "orderid": orderid,
                    "timestamp": ts,
                    "type": fill_type,
                    "side": side,
                    "price": price,
                    "qty": qty,
                    "fill_ratio": round(fill_ratio, 3),
                    "confidence": confidence,
                    "context": {
                        "cancel_ts": cancel_ts,
                        "removed_size": removed_size,
                        "depth_depleted": depth_depleted,
                        "window_ms": self.get_window_ms(),
                        "cancel_density": self.get_cancel_density(side)
                    }
                })
                self.order_age_tracker.fill_order(orderid=orderid, timestamp=ts, event_type=fill_type, size=qty, distance_from_best=abs(self.orderbook.get_best_price(side) - price), side=side)
                self.synthetic_fill_detector.register_event(orderid=orderid, timestamp=ts, event_type=fill_type, price=price, size=qty, side=side)
                #Tag ladder fill activate ladder matches
                if self.active_ladder and price in self.active_ladder["prices"] and side == self.active_ladder["side"]:
                    self.active_ladder["filled"] = True
                    ladder_fill_type = "SYNTHETIC_LADDER_FILL"
                    self._flags.append({
                        "orderid": orderid,
                        "timestamp": ts,
                        "type": ladder_fill_type,
                        "side":side,
                        "price": price,
                        "size": qty,
                        "fill_ratio": round(fill_ratio, 3),
                        "confidence": confidence,
                        "context": {
                            "ladder_prices": sorted(self.active_ladder["prices"]),
                            "cancel_ts": cancel_ts,
                            "removed_size": removed_size,
                            "depth_depleted": depth_depleted,
                            "window_ms": self.get_window_ms(),
                            "cancel_density": self.get_cancel_density(side)
                        }
                    })
                    self.order_ladder_tracker.register_event(orderid=orderid, timestamp=ts, event_type=ladder_fill_type, price=price, size=qty, side=side)
                    self.order_age_tracker.fill_order(orderid=orderid, timestamp=ts, event_type=ladder_fill_type, price=price, size=qty, distance_from_best=abs(self.orderbook.get_best_price(side) - price), side=side)
                
                #Tag layered fill if order was part of layering
                if self.order_layering_tracker.is_layered_order(orderid=orderid):
                    layer_fill_type = "SYNTHETIC_LAYER_FILL"
                    self._flags.append({
                        "orderid": orderid,
                        "timestamp": ts,
                        "type": layer_fill_type,
                        "side":side,
                        "price": price,
                        "size": qty,
                        "fill_ratio": round(fill_ratio, 3),
                        "confidence": confidence,
                        "context": {
                            "ladder_prices": sorted(self.active_ladder["prices"]),
                            "cancel_ts": cancel_ts,
                            "removed_size": removed_size,
                            "depth_depleted": depth_depleted,
                            "window_ms": self.get_window_ms(),
                            "cancel_density": self.get_cancel_density(side),
                        }
                        
                    })
                    self.order_layering_tracker.register_fill(orderid=orderid, timestamp=ts, event_type=layer_fill_type, price=price, size=qty, side=side)
                    self.order_age_tracker.fill_order(orderid=orderid, timestamp=ts, event_type=layer_fill_type, price=price, size=qty, distance_from_best=abs(self.orderbook.get_best_price(side) - price), side=side)

                
            return #Exit after successful cancel match
            
        # ==== Fallback: No Cancel Match ===
        else:
            best_price = self.orderbook.get_best_price('ask' if side == "bid" else "bid")
            spread = abs(best_price - price)
            tick_size = self.orderbook.get_tick_size()
            depth_depleted = self.orderbook.get_level_size(price, side) == 0.0

            if spread < 2 * tick_size or depth_depleted:
        
                orderid = self.order_ids(key)
                if not orderid:
                    orderid = self._next_id()
                    self.order_ids[key] = orderid

                self._flags.append({
                    "orderid": orderid,
                    "timestamp": ts,
                    "type": "SYNTHETIC_FILL_NO_CANCEL",
                    "side": side,
                    "price": price,
                    "qty": qty,
                    "context": {
                        "spread": spread,
                        "depth_depleted": depth_depleted,
                        "window_ms": self.get_window_ms(),
                        "cancel_density": self.get_cancel_density(side)
                    }
                })
                self.order_age_tracker.fill_order(orderid=orderid, timestamp=ts, event_type="SYNTHETIC_FILL_NO_CANCEL", price=price, size=qty, distance_from_best=spread, side=side)
                self.synthetic_fill_detector.register_event(orderid=orderid, timestamp=ts, event_type="SYNTHETIC_FILL_NO_CANCEL", price=price, size=qty, side=side)
            self.fill_events.append({
                "timestamp": ts,
                "price": price,
                "qty": qty,
                "side": side
            })
                    
            # === Ladder context fallback ===
            if self.active_ladder and price in self.active_ladder["prices"]:
                self._flags.append({
                    "orderid": orderid,
                    "timestamp": ts,
                    "type": "SYNTHETIC_LADDER_FILL_EXPIRED",
                    "side": side,
                    "price": price,
                    "qty": qty,
                    "context": {
                        "ladder_prices": sorted(self.active_ladder["prices"]),
                        "spread": spread,
                        "depth_depleted": depth_depleted
                }
             })
                self.order_age_tracker.fill_order(orderid=orderid, timestamp=ts, event_type="SYNTHETIC_LADDER_FILL_EXPIRED", price=price, size=qty, distance_from_best=abs(self.orderbook.get_best_price(side) - price), side=side)
                self.order_ladder_tracker.register_event(orderid=orderid, timestamp=ts, event_type="SYNTHETIC_LADDER_FILL_EXPIRED", price=price, size=size, side=side)

            # === Layering fallback ===
            already_tagged_as_layered = any(f["type"] == "SYNTHETIC_LAYER_FILL" and f["orderid"] == orderid for f in self._flags)
            if self.order_layering_tracker.is_layered_order(orderid) and not already_tagged_as_layered:
                self._flags.append({
                    "orderid": orderid,
                    "timestamp": ts,
                    "type": "SYNTHETIC_LAYER_FILL",
                    "side": side,
                    "price": price,
                    "qty": qty,
                    "context": {
                        "spread": spread,
                        "depth_depleted": depth_depleted
                    }
                })
                self.order_layering_tracker.register_fill(orderid=orderid, timestamp=ts, event_type=layer_fill_type, price=price, size=qty, side=side)
                self.order_age_tracker.fill_order(orderid=orderid, timestamp=ts, event_type=layer_fill_type, price=price, size=qty, distance_from_best=abs(self.orderbook.get_best_price(side) - price), side=side)



        self.add_ts.pop(key, None)  # cleanup
        self.reduction_history.pop(key, None)
        self.order_ids.pop(key, None)
        self.reduction_timestamps.pop(key, None)


        #Keep cancel_cache until it ages out (> window), dont pop immediately
        self._expire_cancel_cache()

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
        return flags
    

    def set_window_ms(self):
        self.window_ms = self.tuner.current_window_ms()

    def get_window_ms(self) -> int:
        self.window_ms = self.tuner.current_window_ms()
        return self.window_ms


    def snapshot_state(self) -> Dict[str, Any]:
        #Return minimal state for now
        return {
            "window_ms": self.get_window_ms(),
            "flag_count":  len(self._flags),
            "bids": len(self.bids),
            "asks": len(self.asks),
            "cancel_cache": len(self.cancel_cache),
            "flags": self._flags[:],
            "cancel_density": self.compute_cancel_density()
            

        }
    
    def compute_cancel_density(self) -> Dict[Tuple[str, float], int]:
        """
        Compute how many cancels occured at each (side, price) level in the past window 'self.get_window_ms()'
        """
        now = max((ts for timestamps in self.cancel_timestamps.values() for ts in timestamps), default=0)
        if now == 0:
            """Sanity check - no cancels recorded yet"""
            return {}
        #Regime aware window override
        window_ms = self.get_window_ms()
        if hasattr(self, 'regime_classifier') and self.regime_classifier:
            regime = self.regime_classifier.get_current_regime()
            stability = self.regime_classifier.get_regime_stability()
            #Optional: blend with default window if regime is unstable
            default_window = window_ms
            regime_window = int(window_ms * (1.0 +  (1.0 - stability) * 0.5)) #Widen window if unstable
            window_ms = regime_window

        cutoff = now - window_ms
        cancel_density: Dict[Tuple[str, float], int] = {}

        for key, timestamps in self.cancel_timestamps.items():
            #count how many timestamps fall within the window
            recent_cancels = [ts for ts in timestamps if ts >= cutoff]
            if recent_cancels:
                cancel_density[key] = len(recent_cancels)
        
        return cancel_density
    
    def set_cancel_density_params(self, initial_threshold: int = 3, initial_window_ms: int = 75) -> None:
        self.cancel_density_threshold_bid = AdaptiveThreshold(initial_threshold=initial_threshold) #Example: 3 cancels in the last 100ms
        self.cancel_density_threshold_ask = AdaptiveThreshold(initial_threshold=initial_threshold)

        self.cancel_density_window_ms = AdaptiveDensityWindow(initial_window_ms=initial_window_ms) #Timewindow to evaluate density 



    #-------------------------------------------------------------
    # Register Cancel
    #---------------------------------------------------------

    def register_cancel(self, timestamp: int, price: float, side: str, size: float) -> None:
        """
        Registers a cancel event with metadata (used in L2 updates).
        Handles iceberg detection, density, and spoofing logic.
        """
        # --- Store cancel event ---
        event = {
            'price': price,
            'side': side,
            'timestamp': timestamp,
            'size': size,
        }

        key = (side, price)
        self.cancel_events.append(event)
        self.cancel_timestamps.setdefault(key, []).append(timestamp)

        # --- Buffer cancels for iceberg detection ---
        self.iceberg_buffer[key].append(event)
        # Prune stale entries outside the active window
        self.iceberg_buffer[key] = [
            e for e in self.iceberg_buffer[key]
            if timestamp - e['timestamp'] <= self.get_window_ms()
        ]

        # --- Count events and reductions ---
        num_events = len(self.iceberg_buffer[key])
        num_reductions = len(self.reduction_history.get(key, []))

        # --- Iceberg detection trigger conditions ---
        # Trigger if:
        #  (a) final cancel (size == 0) AND 2+ reductions
        #  OR
        #  (b) ≥3 buffered cancel/reduction events (for direct register_cancel() tests)
        if (size == 0.0 and num_reductions >= 2) or num_events >= 3:
            self._detect_iceberg_cancel(key)

        # --- Suppress noise for single-reduction scenarios ---
        # Skip the remaining detection logic if not enough reductions
        if num_reductions < 2:
            return

        # --- Additional spoof / density detection logic ---
        self.detect_ping_cancel(timestamp, price, side, size)
        self.detect_reposting_behavior(timestamp, price, side, size)
        self.detect_layer_wipe(timestamp, price, side, size)
        self.detect_burst_cancel(timestamp, price, side, size)

    def _detect_cancel_density_spike(self, timestamp: int):
        """
        Evaluate cancel density and emit CANCEL_DENSITY_SPIKE flags if thresholds are breached.
        Called automatically after each L2 update.
        """
        

        density = self.compute_cancel_density()
        for (side, price), count in density.items():
            threshold = self.cancel_density_threshold_bid if side == "bid" else self.cancel_density_threshold_ask
            threshold.update(self.orderbook.get_estimated_volume(side), self.orderbook.get_volatility_estimate())
           

            if count >= threshold.get_threshold():
                key = (side, price)

                orderid = self.order_ids.get(key)
                if not orderid:
                    orderid = self._next_id()
                    self.order_ids[key] = orderid

                self._flags.append({
                    "timestamp": timestamp,
                    "orderid": orderid,
                    "type": "CANCEL_DENSITY_SPIKE",
                    "side": side,
                    "price": price,
                    "cancel_count": count,
                    "window_ms": self.cancel_density_window_ms.get_current_window(),
                    "context": {
                        "window_ms": self.get_window_ms(),
                        "Cancel Density": self.get_cancel_density(side)
                    }
                })



    def detect_burst_cancel(self, timestamp:int, price:float, side: str, size: float):
        """Very rapid cancels across multiple levels (like a cancel sweep)"""
        window_ms = self.get_window_ms()      #Rolling burst window
        recent = [e for e in self.cancel_events if timestamp - e['timestamp'] <= window_ms]

        vol = self.orderbook.get_estimated_volume(side)
        volty = self.orderbook.get_volatility_estimate()
        threshold = self.cancel_density_threshold_bid if side == "bid" else self.cancel_density_threshold_ask
        threshold.update(vol, volty)

        if len(recent) >= threshold.get_threshold():
            key = (side, price)

            orderid = self.order_ids.get(key)
            if not orderid:
                orderid = self._next_id()
                self.order_ids[key] = orderid

            self._flags.append({
                'orderid': orderid,
                'type': 'BURST_CANCEL',
                'timestamp': timestamp,
                'cancel_count': len(recent),
                'price': price,
                'side': side,
                'size': size,
                'window_ms': window_ms,
               
            })
            #Pass along to OrderAgeDistribution to tag
            self.order_age_tracker.cancel_order(orderid=orderid, timestamp=timestamp, event_type='BURST_CANCEL', price=price, size=size, distance_from_best=abs(self.orderbook.get_best_price(side) - price), side=side)

    def detect_ping_cancel(self, timestamp: int, price: float, side: str, size: float):
        "Tracks orders placed for a very short time (ping for liquidity)"
        cancels_at_price = [
            e for e in self.cancel_events if e['price'] == price and e['side'] == side
        ]
        vol = self.orderbook.get_estimated_volume(side)
        volty = self.orderbook.get_volatility_estimate()
        threshold = self.cancel_density_threshold_bid if side == "bid" else self.cancel_density_threshold_ask
        threshold.update(vol, volty)

        if len(cancels_at_price) >= threshold.get_threshold():
            deltas = [
                cancels_at_price[i+1]['timestamp'] - cancels_at_price[i]['timestamp']
                for i in range(len(cancels_at_price)-1)
            ]
            if any(delta < self.get_window_ms() for delta in deltas): #Arbitary ping delta
                key = (side, price)
                orderid = self.order_ids.get(key)
                if not orderid:
                    orderid = self._next_id()
                    self.order_ids[key] = orderid

                self._flags.append({
                    'orderid': orderid,
                    'type': 'PING_CANCEL',
                    'timestamp': timestamp,
                    'cancel_count': len(cancels_at_price),
                    'price': price,
                    'side': side,
                    'size': size,
                    'window_ms': self.get_window_ms()

                })
                #Pass along to OrderAgeDistribution to tag
                self.order_age_tracker.cancel_order(orderid=orderid, timestamp=timestamp, event_type='PING_CANCEL', price=price, size=size, distance_from_best=abs(self.orderbook.get_best_price(side) - price), side=side)

    def detect_reposting_behavior(self, timestamp: int, price: float, side:str, size: float):
        """Tracks cancel at price and re-add at same/ nearby price (spoofing/layering)"""
        book = self.bids if side == 'bid' else self.asks
        if (side, price) in self.cancel_cache and price in book:
            key = (side, price)
            orderid = self.order_ids.get(key)
            if not orderid:
                orderid = self._next_id()
                self.order_ids[key] = orderid

            self._flags.append({
                'orderid': orderid,
                'type': 'REPOSTING_BEHAVIOUR',
                'timestamp': timestamp,
                'price': price,
                'side': side,
                'size': size,
            })
            #Pass along to OrderAgeDistribution to tag
            self.order_age_tracker.cancel_order(orderid=orderid, timestamp=timestamp, event_type='REPOSTING_BEHAVIOUR', price=price, size=size, distance_from_best=abs(self.orderbook.get_best_price(side) - price), side=side)

    def detect_layer_wipe(self, timestamp: int, price: float, side:str, size:float):
        """Cancelling several price at once in a single direction(layer wipe)"""
        price_levels = self.bids.keys() if side == 'bid' else self.asks.keys()
        cancel_levels = [price for (s, price), _ in self.cancel_cache.items() if s == side]
        active_levels = set(price_levels).intersection(cancel_levels)

        vol = self.orderbook.get_estimated_volume(side)
        volty = self.orderbook.get_volatility_estimate()
        threshold = self.cancel_density_threshold_bid if side == "bid" else self.cancel_density_threshold_ask
        threshold.update(vol, volty)
        
        if len(active_levels) >= threshold.get_threshold(): #arbitary threshold
            key = (side, price)
            orderid = self.order_ids.get(key)
            if not orderid:
                orderid = self._next_id()
                self.order_ids[key] = orderid

            self._flags.append({
                'orderid': orderid,
                'type': 'LAYER_WIPE',
                'timestamp': timestamp,
                'price': price,
                'side': side,
                'size': size,
                'price_levels': list(active_levels),
            })
            #Pass along to OrderAgeDistribution to tag
            self.order_age_tracker.cancel_order(orderid=orderid, timestamp=timestamp, event_type='LAYER_WIPE', price=price, size=size, distance_from_best=abs(self.orderbook.get_best_price(side) - price), side=side)


            #Pass along to OrderLayeringDetection to tag
            self.order_layering_tracker.register_cancel(orderid=orderid, timestamp=timestamp, event_type='LAYER_WIPE', price=price, size=size, side=side)

    def _detect_iceberg_cancel(self, key: Tuple[float, str]) -> None:
        """
        Detect iceberg cancels: multiple reductions followed by full cancel.
        Uses score gated flagging and emits a single, rich ICEBERG_CANCEL event.
        """
        #Ensure Consistent key usage: (side, price)
        side, price = key
        events = self.iceberg_buffer.get(key, [])
        #Require at least two meaningingful reductions before a cancel
        if len(events) < 3:
            return

        total_size = sum(e['size'] for e in events)
        first_ts = events[0]['timestamp']
        last_ts = events[-1]['timestamp']
        dt = last_ts - first_ts
        side = events[-1]['side']
        price = events[-1]['price']

        # Skip if Cancel happens outside the spoof window
        if dt > 2 * self.get_window_ms():
            return

        # Get recorded reductions if present (reduction_history uses (side, price) keys).
        reductions = self.reduction_history.get((side, price), [])

        iceberg_score = self._quantitative_iceberg_spoof(
            side=side,
            price=price,
            dt=dt,
            total_size=total_size,
            ts=last_ts,
        )

        if iceberg_score >= 0.30:  # Score gate
            orderid = self.order_ids.get(key)
            if not orderid:
                orderid = self._next_id()
                self.order_ids[key] = orderid

            flag = {
                'orderid': orderid,
                'type': 'ICEBERG_CANCEL',
                'price': price,
                'side': side,
                'size': total_size,
                'count': len(events),
                'score': round(iceberg_score, 3),
                'timestamp': last_ts,
                # attach reductions if available for richer context (tests expect this)
                'reductions': reductions if reductions else None,
                # latency_ms: how long between first reduction and final cancel
                'latency_ms': dt,
                'context': {
                    'window_ms': self.get_window_ms(),
                    'cancel_density': self.get_cancel_density(side),
                }
            }
            # Clean None reductions key if there were none
            if flag['reductions'] is None:
                del flag['reductions']

            self._flags.append(flag)

            # Pass along to OrderAgeDistribution to tag — use last_ts (not dt)
            self.order_age_tracker.cancel_order(
                orderid=orderid,
                timestamp=last_ts,
                event_type='ICEBERG_CANCEL',
                price=price,
                size=total_size,
                distance_from_best=abs(self.orderbook.get_best_price(side) - price),
                side=side
            )

            # Clear buffer to avoid double reporting
            self.iceberg_buffer[key].clear()


    def get_cancel_density(self, side:str) -> dict:
        """
        :param side: str
        :Returns a dictironary of {price: cancel_count} for the given side
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
    def update_midprice(self, mid_price: Optional[float] = None):

        """Update mid price for cancel impact scoring 
            If mid_price is provided (as tests do), use it, otherwise pull from the OrderBook.
        """
        if mid_price is not None:
            self.mid_price = float(mid_price)
        else:
            if hasattr(self.orderbook, "get_midprice"):
                self.mid_price = self.orderbook.get_midprice()
            # fallback: return cached if mock orderbook has no method
        return self.mid_price

    
    def compute_cancel_impact_score(self, price: float, side: str) -> float:
        """Compute the impact score of cancels at a given price level and side.
        The higher the score, the more market-impacting the cancel is.
        """

        # --- Step 1: Normalize Cancel Density -----
        density = self.get_cancel_density(side)
        total_cancels = sum(density.values()) or 1e-9
        norm_density =(density.get(price, 0) / total_cancels)**1.5

        # ------ Step 2: Distance from Midprice -----
        mp = self.update_midprice()
        if mp is None:
            dist_from_mid = 0.5 # Neutral
        else:
            max_rel_dist = 0.02 #2%
            # Guard mp == 0 to avoid division warnings in synthetic tests.
            rel_dis = abs(price - mp) / (mp if mp else 1e-9)
            dist_from_mid = max(0.0, 1.0 - min(1.0, rel_dis / max_rel_dist)) # mapped to [0,1]

        # ------Step 3: Recent Fills at that Price ----
        recent_fills = [f for f in self.fill_events if f['price'] == price and f['side'] == side]
        fill_score = min(len(recent_fills) / 2, 1.0)    #normalize

        # ------Step 4: Inverse Book Depth at Price ----
        """Still need to implement the orderbook.get_level_size(price, size)"""
        try:
            size_at_price = self.orderbook.get_level_size(price, side) or 1e-9
        except Exception:
            size_at_price = 1e-9

        inv_book_depth = min(1.0 / size_at_price, 1.0)

        # -----Step 5: Regime-Aware Weights ----
        if hasattr(self, 'regime_classifier') and self.regime_classifier:
            stability = self.regime_classifier.get_regime_stability()
            base_weights = self.regime_classifier.get_scoring_weights()
            default_weights = (0.5, 0.2, 0.1, 0.2) #Default weights
            w1, w2, w3, w4 = tuple(
                stability * bw + (1.0 - stability) * dw
                for bw, dw in zip(base_weights, default_weights)
            )
        # -----Weighted Combination -------
        else:
            w1, w2, w3, w4 = 0.5, 0.2, 0.1, 0.2

        score = (
            w1 * norm_density +
            w2 * dist_from_mid +
            w3 * fill_score +
            w4 * inv_book_depth

        )
        return round(score, 4)
    
    # ------------------------------------------
    # Quantitative iceberg /spoof scoring helper
    # --------------------------------------

    def _quantitative_iceberg_spoof(self, side, price, dt, total_size, ts):
        """
        Score cancels probabilistically instead of binary flags
        """
        # Base score: bigger reduction and shorter dt -> higher score
        size_score = min(1.0, total_size / 10.0) #Scale by typical level size
        dt_score = max(0.0, 1.0 - dt / max(1, self.get_window_ms()))
        #Distance from midprice: cancels closer to mid are more impactful
        if self.midprice is not None:
            dist = abs(price - self.midprice) / max(1e-9, self.midprice)
            dist_score = max(0.0, 1.0 - dist / 0.02)
        else:
            dist_score = 0.5
        score = 0.6 * size_score + 0.3 * dt_score + 0.1 * dist_score
        return score


    def _expire_cancel_cache(self):
        """
        Prune stale entries from the cancel cache to avoid memory bloat and false matches.
        This method is called after trade processing to ensure fills have a fair chance to match recent cancels.

        Strategy:
        - Uses regime stability to dynamically widen the expiry window.
        - In stable regimes, cancels expire faster (2x window).
        - In unstable regimes, cancels persist longer (up to 4x window).
        - Ensures behavioral continuity without accumulating irrelevant noise.
        """
        current_time = int(time.time() * 1000)

        # Get regime stability (default to 1.0 if classifier is missing)
        stability = self.regime_classifier.get_regime_stability() if self.regime_classifier else 1.0

        # Compute expiry multiplier: wider window if regime is unstable
        multiplier = 2.0 + (1.0 - stability) * 2.0  # ranges from 2.0 to 4.0

        # Final expiry window in milliseconds
        expiry_window = int(self.get_window_ms() * multiplier)

        # Prune cancel_cache entries older than expiry_window
        self.cancel_cache = {
            k: (ts, sz) for k, (ts, sz) in self.cancel_cache.items()
            if current_time - ts <= expiry_window
        }


    def get_debug_view(self) -> Dict[str, Any]:
        return {
            "window_ms": self.get_window_ms(),
            "midprice": self.midprice,
            "flag_count": len(self._flags),
            "recent_flags": self._flags[-5:],
            "cancel_cache_size": len(self.cancel_cache),
            "cancel_density_bid": self.get_cancel_density("bid"),
            "cancel_density_ask": self.get_cancel_density("ask"),
            "normalized_cancel_density": self.get_normalized_cancel_density(),
            "cancel_impact_sample": {
                k: self.compute_cancel_impact_score(k[1], k[0])
                for k in list(self.cancel_cache.keys())[-3:]
            },
            "laddering_buffer_size": len(self.laddering_buffer),
            "active_ladder": self.active_ladder,
            "cancel_events_sample": self.cancel_events[-3:],
            "fill_events_sample": self.fill_events[-3:]
        }
        
        
    def reset(self):
        self.bids.clear()
        self.asks.clear()
        self.add_ts.clear()
        self.cancel_cache.clear()
        self.reduction_history.clear()
        self.cancel_timestamps.clear()
        self.reduction_timestamps.clear()
        self._flags.clear()
        self.iceberg_buffer.clear()
        self.laddering_buffer.clear()
        self.active_ladder = None
        self.cancel_events.clear()
        self.fill_events.clear()
        self.order_ids.clear()


