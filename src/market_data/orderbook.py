# Market_data/orderbook.py 
from collections import deque
import math
from typing import Optional
import time
import requests
import logging
from colorama import Fore, Style, init

init(strip=True)
logging.basicConfig(level=logging.ERROR)

logger = logging.getLogger("[OrderBook]")
# 1. Add the NullHandler: This consumes all logs without outputting them
logger.addHandler(logging.NullHandler())

# 2. Stop propagation: This prevents logs from being sent to the console/root logger
logger.propagate = False

class OrderBook:
    """
    Lightweight L2 Order Book Binance Symbols.
    Tracks bid/ask level and provides midprice, volatility,
    and liquidity metrics
    Supports depth updates and TRADE messages
    """
    def __init__(self):
        """
        Initialize the lightweight L2 OrderBook for a specific Binance trading symbol.
        tracks bid/ask levels and provides midprice, volatility,
        depth liquidity, and imbalance metrics
        """
        self.history_len = 500 # increased from 100 to 500 to prevent prevent narrow candle structure during low-volatility regimes.
        self.symbol = "SOLUSDT"
        self.bids = {} # Bid side: {price-> size} 
        self.asks = {} # Ask side: {price -> size}
        self.last_midprice = None
        self.price_history = deque(maxlen=self.history_len) #Rolling midpoint buffer for volatility estimate

        
        # NEW: Track imbalance history (matches price history length)
        self.imbalance_history = deque(maxlen=self.history_len)

        self.last_update_ts = None
        self._tick_size = None  # Cached tick size

        # Snapshot sync (Bug 1): tracks the lastUpdateId from REST snapshot
        self._last_update_id: int = 0
        self._snapshot_initialized: bool = False

        # Rolling update timestamps for accurate get_update_rate() (Bug 5)
        self._update_timestamps: deque = deque(maxlen=50)

        self.last_mark_price: Optional[float] = None
        self.last_mark_price_fetch_ts: Optional[float] = None  # NEW: Track fetch time
        self.mark_price_cache_duration = 5.0  # NEW: Cache for 5 seconds


        # Public attribute written directly by orchestration AND by update().
        # Kept in sync with last_mark_price so both access patterns work.
        self.mark_price: float = 0.0

        # ── Hot-path cache: updated on every depth tick so all accessors are O(1) ──
        self._best_bid: Optional[float] = None
        self._best_ask: Optional[float] = None

        # Incremental running totals — maintained in _update_depth() so that
        # get_estimated_volume(), get_bid_defense(), and get_ask_defense() never
        # have to sum the entire book.  O(1) update, O(1) read.
        self._bid_total: float = 0.0
        self._ask_total: float = 0.0

        # TTL cache for bid/ask defense (50ms) — both values updated together
        self._defense_bid_cache: float = 0.5
        self._defense_ask_cache: float = 0.5
        self._defense_cache_ts: float = 0.0
        self._defense_cache_ttl: float = 0.05  # 50 ms

        self.testnet = True #Change to False is production

        # Track Trade flow for heartbeat detection
        self.last_trade_ts = None
        self.trade_count = 0

        # Simple OHLC tracking (1-minute bars)
        self._current_bar = {
            'open': None,
            'high': None,
            'low': None,
            'close': None,
            'start_time': time.time()
        }

        self._completed_bars = deque(maxlen=100)

        # NEW: Internal Symbol Info Cache
        self._tick_size = 0.1  # Default fallback for SOLUSDT
        self._last_info_update = 0
        self._update_interval = 3600  # Refresh every hour
        
        # Tick size is set by the async initialisation path via set_tick_size().
        # _fetch_symbol_info_internal() is NOT called here because it makes a
        # blocking requests.get() that would stall the event loop at startup.
        # The orchestration layer calls set_tick_size() after symbol info is loaded.


    # ------------------------ Snapshot Init (Bug 1) ----
    async def initialize_snapshot(self, fetch_fn=None):
        """
        Sync orderbook from a REST snapshot before processing any diff events.
        Must be called once on startup, after WebSocket connection, before applying diffs.

        Binance protocol:
          1. Subscribe to @depth WebSocket stream
          2. Buffer events
          3. Fetch REST snapshot (GET /fapi/v1/depth?symbol=X&limit=1000)
          4. Discard buffered events with u <= snapshot lastUpdateId
          5. Apply subsequent events in order

        Args:
            fetch_fn: Optional async callable returning Binance depth snapshot dict.
                      If None, uses internal REST fetch.
        """
        import aiohttp
        # Pause the stale-event filter while we re-sync.
        # This prevents diffs that arrived before the snapshot ID from
        # being incorrectly discarded (or accepted) during the REST fetch window.
        self._snapshot_initialized = False
        if fetch_fn is not None:
            snapshot = await fetch_fn()
        else:
            base = "https://testnet.binancefuture.com" if self.testnet else "https://fapi.binance.com"
            url = f"{base}/fapi/v1/depth?symbol={self.symbol}&limit=1000"
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                    snapshot = await resp.json()

        self.bids = {float(p): float(q) for p, q in snapshot["bids"]}
        self.asks = {float(p): float(q) for p, q in snapshot["asks"]}
        # Seed running totals from snapshot
        self._bid_total = sum(self.bids.values())
        self._ask_total = sum(self.asks.values())
        self._last_update_id = snapshot["lastUpdateId"]
        self._snapshot_initialized = True
        logger.info("[OrderBook] Snapshot initialized for %s, lastUpdateId=%s", self.symbol, self._last_update_id)
        # Also seed best bid/ask from snapshot
        if self.bids:
            self._best_bid = max(self.bids.keys())
        if self.asks:
            self._best_ask = min(self.asks.keys())
        self._update_midprice()

    # ------------------------ Updates ------------
    def update(self, msg):
        """Process Binance depth@1000ms L2 Update AND trade messages
        Binance Websocket send different message types:
        - Depth updates: {'b': [...], 'a': [...], 'E': timestamp}
        - Trade updates: {'p': price, 'q': qty, 'E': timestamp, 'm': bool}
        """
        # =======================================
        # DEPTH UPDATE (bid/ask levels)
        # ======================================
        if 'b' in msg and 'a' in msg:
            self._update_depth(msg)
            return
        
        # ======================================
        # TRADE UPDATE (price/qty)
        # ======================================
        if 'p' in msg and 'q' in msg:
            self._update_trade(msg)
            return
        
        # ======================================
        # MARK PRICE UPDATE (futures specific)
        # =====================================
        if 'p' in msg and 'b' not in msg and 'a' not in msg:
            try:
                mark_price = float(msg.get('p', 0))
                if mark_price > 0:
                    # Keep both attributes in sync — orchestration reads .mark_price directly,
                    # get_mark_price() reads .last_mark_price.  Both must reflect live WS data.
                    self.last_mark_price = mark_price
                    self.mark_price = mark_price
                    now = time.time()
                    self.last_update_ts = now
                    self.last_mark_price_fetch_ts = now

                    # Optional: use mark price as midprice fallback
                    if self.last_midprice is None:
                        self.last_midprice = mark_price
                        self.price_history.append(mark_price)
            except (ValueError, TypeError):
                pass
            return

        # If we get here, unknown message format
        logger.debug("Unknown orderbook message format: %s", list(msg.keys()))



    def _update_depth(self, msg):
        """Process depth (L2) updates for bids and asks"""
        # Bug 1 fix: discard stale events that predate our REST snapshot
        event_last_update_id = msg.get("u", 0)
        if self._snapshot_initialized and event_last_update_id <= self._last_update_id:
            return  # stale diff — discard
        self._last_update_id = event_last_update_id

        bid_changed = False
        ask_changed = False

        for p, q in msg.get("b",[]):
            try:
                price = float(p)
                size = float(q)
                if price <= 0:
                    continue
                if size > 0:
                    old = self.bids.get(price, 0.0)
                    self.bids[price] = size
                    self._bid_total += size - old          # incremental update O(1)
                elif price in self.bids:
                    self._bid_total -= self.bids[price]    # subtract evicted level
                    del self.bids[price]
                    if price == self._best_bid:
                        bid_changed = True
                else:
                    continue
                if not bid_changed:
                    if size > 0 and (self._best_bid is None or price > self._best_bid):
                        self._best_bid = price
            except (ValueError, TypeError):
                continue

        for p, q in msg.get('a', []):
            try:
                price = float(p)
                size = float(q)
                if price <= 0:
                    continue
                if size > 0:
                    old = self.asks.get(price, 0.0)
                    self.asks[price] = size
                    self._ask_total += size - old          # incremental update O(1)
                elif price in self.asks:
                    self._ask_total -= self.asks[price]    # subtract evicted level
                    del self.asks[price]
                    if price == self._best_ask:
                        ask_changed = True
                else:
                    continue
                if not ask_changed:
                    if size > 0 and (self._best_ask is None or price < self._best_ask):
                        self._best_ask = price
            except (ValueError, TypeError):
                continue

        # Only do the expensive O(n) scan when the cached best was removed
        if bid_changed:
            self._best_bid = max(self.bids.keys(), default=None)
        if ask_changed:
            self._best_ask = min(self.asks.keys(), default=None)


        self.last_update_ts = time.time()  # <-- ADD THIS LINE
        self._update_timestamps.append(self.last_update_ts)  # Bug 5 fix: rolling window
        self._update_midprice()

    def _update_trade(self, msg):
        """
        Process trade messages for OHLC and heartbeat
        Trade message format:
            {
                'e': 'aggTrade'
                'E': 1234567890, # event time
                'p': 123.45,    #Price
                'q': '1.5',     #quantity
                'm': true,      # is buyer maker
            }
        """
        try:
            price = float(msg.get('p', 0))
            if price <= 0:
                return
            
            # Update trade timestamp
            self.last_trade_ts = time.time()
            self.trade_count += 1

            # Update OHLC bar
            self._update_ohlc(price)

            # Update price history(for volatility)
            self.last_midprice = price
            self.price_history.append(price)

        except (ValueError, TypeError) as e:
            logger.debug("Trade update error: %s", e)


    def _update_ohlc(self, price: float):
        """
        Maintain 10-second 'Stability Bars' for reactive Risk Management.
        Reduces lag in ATR and Volatility estimation.
        """
        now = time.time()
        # Widen stability by using 10-second intervals instead of 60-second
        STABILITY_INTERVAL = 10 

        if now - self._current_bar['start_time'] >= STABILITY_INTERVAL:
            if self._current_bar['close'] is not None:
                self._completed_bars.append({
                    'open': self._current_bar['open'],
                    'high': self._current_bar['high'],
                    'low': self._current_bar['low'],
                    'close': self._current_bar['close']
                })

            self._current_bar = {
                'open': price,
                'high': price,
                'low': price,
                'close': price,
                'start_time': now
            }
        else:
            if self._current_bar['open'] is None:
                self._current_bar['open'] = price
            self._current_bar['high'] = max(self._current_bar.get('high') or price, price)
            self._current_bar['low'] = min(self._current_bar.get('low') or price, price)
            self._current_bar['close'] = price
    
    def get_last_completed_bar(self) -> Optional[dict]:
        """
        Get most recent completed OHLC bar
        Returns: {'open': float, 'high': float, 'low': float, 'close': float}
        """
        if not self._completed_bars:
            return None
        return self._completed_bars[-1]
    
    def _fetch_mark_price_from_api(self) -> Optional[float]:
        """
        LEGACY: Synchronous REST fetch — DO NOT call from the asyncio event loop.
        This blocks for up to 3 seconds. Mark price is pushed via the WebSocket
        markPrice stream and stored in last_mark_price by update(). This method
        is only kept as a last-resort initialisation fallback and should not be
        called once the WS feed is live.
        """
        base_url = (
            "https://testnet.binancefuture.com/fapi/v1/premiumIndex"
            if self.testnet
            else "https://fapi.binance.com/fapi/v1/premiumIndex"
        )
        url = "%s?symbol=%s" % (base_url, self.symbol)
        try:
            import requests as _requests
            response = _requests.get(url, timeout=3)
            response.raise_for_status()
            data = response.json()
            mark_price = float(data.get('markPrice', 0))
            if mark_price > 0:
                logger.debug("[OrderBook] API mark price for %s: $%.4f", self.symbol, mark_price)
                return mark_price
            logger.warning("[OrderBook] Invalid mark price from API: %s", mark_price)
        except Exception as e:
            logger.warning("[OrderBook] Error fetching mark price: %s", e)
        return None


    def _update_midprice(self):
        """
        Compute mid price from cached best bid/ask — O(1) thanks to _best_bid/_best_ask.
        """
        best_bid = self._best_bid
        best_ask = self._best_ask

        if best_bid is not None and best_ask is not None:
            if best_ask <= best_bid:
                logger.warning(
                    "[OrderBook] Inverted book detected: bid=%s, ask=%s — skipping mid update",
                    best_bid, best_ask,
                )
                return
            mid = (best_bid + best_ask) / 2
            self.last_midprice = mid
            self.price_history.append(mid)

            # NEW: Automatically record imbalance whenever price updates
            self.imbalance_history.append(self.get_layered_imbalance())

    # ---------------------- Basic Accessors ----------------------------------------
    def get_midprice(self) -> float:
        """
        Returns the last computed midprice or 0.0 if unavailable.
        """
        return self.last_midprice or 0.0
    
    def get_resilient_midprice(self) -> float:
        """
        Returns a safe, real-time midprice using a robust fallback hierarchy.
        Optimized for SOLUSD to avoid stale 'Mark Price' lag.
        """
        # 1. Live midprice (Calculated from current L2 Bids/Asks)
        mid = self.get_midprice()
        if mid > 0:
            return mid

        # 2. Synthetic from best bid/ask (Explicit fallback)
        # This captures the very edge of the book if get_midprice() logic is too strict
        bid = self.get_best_price("bid")
        ask = self.get_best_price("ask")
        if bid > 0 and ask > 0:
            return (bid + ask) / 2

        # 3. Last Traded Price (More recent than Mark Price usually)
        # Use last_midprice if it was updated by a recent trade/snapshot
        if self.last_midprice and self.last_midprice > 0:
            return self.last_midprice

        # 4. Mark Price (Lowest priority due to the 5s cache lag)
        if self.last_mark_price and self.last_mark_price > 0:
            # We only log a warning here because Mark Price is cached and might be 5s old
            logger.warning("[OrderBook] Using stale Mark Price fallback: $%.2f", self.last_mark_price)
            return self.last_mark_price
        # 5. Ultimate Safety (Return 0.0 only as a last resort)
        logger.error("[OrderBook] CRITICAL: No price source available for Resilient Midprice")
        return 0.0
            
    def get_mark_price(self) -> float:
        """
        Returns the latest mark price.

        Priority:
          1. self.mark_price — set every second by the WS markPrice stream via update()
             or directly by StateSynchronizer.  Zero-latency, zero REST weight.
          2. self.last_midprice — live L2 mid.  Used only if mark_price not yet received.
          3. Blocking REST fetch — ONLY during cold-start before first WS message arrives.
             Once the stream is live this path is never reached.
        """
        # Fast path: WS has pushed a fresh mark price (within cache window)
        now = time.time()
        if (self.mark_price > 0
                and self.last_mark_price_fetch_ts is not None
                and (now - self.last_mark_price_fetch_ts) < self.mark_price_cache_duration):
            return self.mark_price

        # Second fast path: live L2 mid (no REST cost)
        mid = self.last_midprice
        if mid and mid > 0:
            return mid

        # Cold-start only: blocking REST fetch
        logger.warning(
            "[OrderBook] No WS mark price available — falling back to blocking REST fetch. "
            "This should only happen during cold-start."
        )
        fetched = self._fetch_mark_price_from_api()
        if fetched and fetched > 0:
            self.last_mark_price = fetched
            self.mark_price = fetched
            self.last_mark_price_fetch_ts = now
            return fetched

        fallback = self.get_resilient_midprice()
        if fallback > 0:
            logger.warning("[OrderBook] Mark price unavailable — using resilient midprice $%.4f", fallback)
        else:
            logger.warning("[OrderBook] Mark price unavailable — no fallback available")
        return fallback


    
    def get_level_size(self, price, side) -> float:
        """
        Returns the size available at a given price level and side.

        :param price: Price level to query
        :param side: 'bid' or 'ask'
        :return: Order size at that price
        """
        book = self.bids if side == 'bid' or side == 'b' else self.asks
        return book.get(price, 0.0)
    
    def get_best_price(self, side: str) -> float:
        """
        Returns the best bid or ask price.

        Fast path: uses the incrementally-maintained _best_bid / _best_ask cache
        (O(1), no iteration - kept accurate by _updated_depth()).


        Cause E fix: the previous implementation always called
        list(self.bid.keys()) + max() - O(n) on every call. with the health
        check calling this twice every 10 s and on_market_tick calling it each
        tick, this was a significant source of event-loop micro-stalls at 17k+
        iterations with a deep book.

        Fallback: if the cache hasn't been populated yet (e.g empty book at startup or immediately after a reconnect reset),
        fall back to the original snapshot-based scan. The snapshot avoids "dictionary changed
        size during iteration" if _update_depth() mutates the dict concurrently. 

        :param side: 'bid' or 'ask'
        :return: Best price on that side, 0.0 if book is empty
        """
        if side == 'bid' or side == 'b':
            best = self._best_bid
            if best is not None:
                return float(best)
            # Fallback: snapshot to avoid "dictionary changed size during iteration"
            bids_keys = list(self.bids.keys())
            return max(bids_keys, default=0.0)
        else:
            best = self._best_ask
            if best is not None:
                return float(best)
            # Fallback: snapshot to avoid "dictionary changed size during iteration"
            asks_keys = list(self.asks.keys())
            return min(asks_keys, default=0.0)
        

    # ------------------------- Liquidity Metrics --------------------------------
    def get_estimated_volume(self, side: str) -> float:
        """
        Total volume on a given side.  O(1) — reads the incremental running total
        maintained by _update_depth() instead of summing the entire book each call.
        """
        return self._bid_total if (side == 'bid' or side == 'b') else self._ask_total

    def get_top_liquidity(self, side: str, depth_levels: int = 1) -> float:
        """
        Returns size available in the top N levels.
        For depth_levels=1 uses cached best price for O(1) lookup.
        """
        if depth_levels == 1:
            if side == "bid":
                return self.bids.get(self._best_bid, 0.0) if self._best_bid is not None else 0.0
            else:
                return self.asks.get(self._best_ask, 0.0) if self._best_ask is not None else 0.0

        book = self.bids if side == "bid" else self.asks
        if not book:
            return 0.0
        levels = sorted(book.items(), key=lambda x: x[0], reverse=(side == "bid"))
        return sum(size for _, size in levels[:depth_levels])
    

    def get_liquidity_within_bps(self, side: str, depth_bps: float) -> float:
        """
        Returns total liquidity within X basis points of midprice.
        depth_bps=0 fast-path uses cached best price (O(1)).
        """
        mid = self.get_midprice()
        if mid <= 0:
            return 0.0
        if depth_bps < 0:
            return 0.0

        if depth_bps == 0:
            if side == "bid":
                return self.bids.get(self._best_bid, 0.0) if self._best_bid is not None else 0.0
            else:
                return self.asks.get(self._best_ask, 0.0) if self._best_ask is not None else 0.0

        threshold = mid * (depth_bps / 1e4)
        if side == "bid":
            return sum(size for price, size in self.bids.items() if (mid - price) <= threshold)
        else:
            return sum(size for price, size in self.asks.items() if (price - mid) <= threshold)

    # -------------------- Microstructure metrics ---------------------------------
    def get_order_imbalance(self, side: str, depth_levels: int = 5) -> float:
        """
        Order book imbalance = bid_vol / (bid_vol + ask_vol).
        Range [0, 1], > 0.5 means more bid-side liquidity.
        No dict() copy needed — asyncio is single-threaded and update() is sync.
        """
        bid_levels = sorted(self.bids.items(), key=lambda x: x[0], reverse=True)[:depth_levels]
        ask_levels = sorted(self.asks.items(), key=lambda x: x[0])[:depth_levels]

        bid_vol = sum(size for _, size in bid_levels)
        ask_vol = sum(size for _, size in ask_levels)

        denom = bid_vol + ask_vol
        if denom == 0:
            return 0.5
        if side == "ask" or side == 'a':
            return ask_vol / denom
        elif side == "bid" or side == 'b':
            return bid_vol / denom
        return 0.5
    
    def get_layered_imbalance(self, base_layers: list = [5.0, 15.0, 40.0]) -> float:
        """
        Calculates a weighted imbalance across multiple depth layers.
        Protects against top-of-book spoofing by looking at deeper 'walls'.
        Returns a score from 0 (heavy ask pressure) to 1 (heavy bid pressure).
        """
        # Cause D guard: book is empty during reconnect snapshot gap — return 0.5 neutral.
        if not self._snapshot_initialized:
            return 0.5

        mid = self.get_midprice()
        if mid <= 0: return 0.5
        
        # Volatility scaling: expand layers if the market is chaotic
        vol = self.get_volatility_estimate()
        vol_mult = max(1.0, min(2.5, vol * 1000))
        
        layer_scores = []
        # Weights: closer layers (index 0) matter more than deep layers
        weights = [0.5, 0.3, 0.2] 

        for bps in base_layers:
            dynamic_bps = bps * vol_mult
            threshold = mid * (dynamic_bps / 10000)
            
            # Aggregate volume within this specific BPS window
            b_vol = sum(s for p, s in self.bids.items() if (mid - p) <= threshold)
            a_vol = sum(s for p, s in self.asks.items() if (p - mid) <= threshold)
            
            # Calculate imbalance for this layer (0.5 is neutral)
            denom = b_vol + a_vol
            layer_imb = b_vol / denom if denom > 0 else 0.5
            layer_scores.append(layer_imb)

        # Return the weighted average of all layers
        return sum(s * w for s, w in zip(layer_scores, weights))

    def get_vamp(self, depth_bps: float = 5.0) -> float:
        """
        Calculates a Volatility-Adaptive VAMP.
        Expands the search window during high volatility to ensure 
        we don't lose anchor during fast moves.
        """
        # 1. Get current volatility (standard deviation of log returns)
        # Assuming volatility_estimate is normalized or representative of price %
        vol = self.get_volatility_estimate()
        
        # 2. Scale Depth: If vol increases, we look deeper.
        # multiplier example: 1.0 at low vol, up to 3.0 during spikes.
        vol_multiplier = max(1.0, min(3.0, vol * 1000)) 
        dynamic_depth = depth_bps * vol_multiplier
        
        bb, ba = self._best_bid, self._best_ask
        if bb is None or ba is None or bb >= ba:
            return self.last_midprice or 0.0

        # 3. Calculate range using dynamic depth
        bid_limit = bb * (1 - dynamic_depth / 10000)
        ask_limit = ba * (1 + dynamic_depth / 10000)

        bid_vol = sum(size for p, size in self.bids.items() if p >= bid_limit)
        ask_vol = sum(size for p, size in self.asks.items() if p <= ask_limit)

        total_vol = bid_vol + ask_vol
        if total_vol == 0:
            return (bb + ba) / 2

        return (bb * ask_vol + ba * bid_vol) / total_vol

    def get_bps_imbalance(self, depth_bps: float = 10.0) -> float:
        """
        A more realistic version of level-based imbalance.
        Uses a percentage of price to capture actual 'walls'.
        """
        mid = self.get_midprice()
        if mid <= 0: return 0.5
        
        threshold = mid * (depth_bps / 10000)
        bid_vol = sum(size for p, size in self.bids.items() if (mid - p) <= threshold)
        ask_vol = sum(size for p, size in self.asks.items() if (p - mid) <= threshold)
        
        denom = bid_vol + ask_vol
        return bid_vol / denom if denom > 0 else 0.5



    def get_volatility_estimate(self) -> float:
        """
        Estimate market volatility using rolling historical midprices with a 
        liquidity-aware floor to protect stop-loss placement.
        """
        if len(self.price_history) < 2:
            return 0.001 

        try:
            returns = [
                (self.price_history[i] - self.price_history[i-1]) / self.price_history[i-1]
                for i in range(1, len(self.price_history))
                if self.price_history[i-1] != 0
            ]
            
            if not returns:
                return 0.001

            variance = sum(r ** 2 for r in returns) / len(returns)
            stdev = variance ** 0.5

            # Use the resilient midprice for the denominator
            mid = self.get_resilient_midprice()
            
            # Ensure we have a valid spread to calculate the floor
            if mid > 0 and self._best_ask is not None and self._best_bid is not None:
                current_spread_pct = (self._best_ask - self._best_bid) / mid
                # Floor at 2x spread to avoid 'no-man's land' placement
                return max(stdev, current_spread_pct * 2.0, 0.001)
            
            return max(0.001, stdev)

        except Exception as e:
            logger.error(f"[OrderBook] Volatility calculation error: {e}")
            return 0.001
        

    def get_update_rate(self) -> float:
        """
        Accurate update frequency (Hz) using a rolling 50-event timestamp window.
        Bug 5 fix: old version divided total history count by stale elapsed time — wrong.
        """
        if len(self._update_timestamps) < 2:
            return 0.0
        window = time.time() - self._update_timestamps[0]
        if window < 0.01:
            return 0.0
        return (len(self._update_timestamps) - 1) / window
        
    def set_tick_size(self, tick_size: float) -> None:
        """Set tick size — call once during async initialisation (e.g. from exchangeInfo)."""
        self._tick_size = tick_size


    def _get_tick_size_from_binance(self, symbol: str) -> Optional[float]:
        """
        LEGACY synchronous REST fetch. Do NOT call from the asyncio event loop.
        Use BinanceExecutionAdapter.initialize_symbol_info() + set_tick_size() instead.
        Kept only for offline tooling / unit tests.
        """
        base_url = (
            "https://testnet.binancefuture.com/fapi/v1/exchangeInfo"
            if self.testnet
            else "https://fapi.binance.com/fapi/v1/exchangeInfo"
        )
        url = "%s?symbol=%s" % (base_url, symbol)
        try:
            import requests as _requests
            response = _requests.get(url, timeout=5)
            response.raise_for_status()
            data = response.json()
            filters = data["symbols"][0]["filters"]
            for f in filters:
                if f["filterType"] == "PRICE_FILTER":
                    tick_size = float(f["tickSize"])
                    logger.info("[OrderBook] Tick size for %s: %s", symbol, tick_size)
                    return tick_size
        except Exception as e:
            logger.warning("[OrderBook] Failed to fetch tick size for %s: %s", symbol, e)
        return None

    

    def get_midpoint_staleness(self) -> float:
        """
        Measures how long the midpoint has remained unchanged.
        Returns a normalized staleness score [0.0–1.0].
        """
        # No updates at all = maximum staleness
        if not self.last_update_ts:
            return 1.0
        
        # No price history = can't compute
        if not self.price_history:
            return 0.0
        
        # Single price = no changes to measure
        if len(self.price_history) < 2:
            return 0.0
        
        unchanged = sum(
            1 for i in range(1, len(self.price_history))
            if self.price_history[i] == self.price_history[i-1]
        )
        return unchanged / len(self.price_history)
    


    def get_quote_flicker_rate(self) -> float:
        """
        Estimates how frequently the midpoint price changes.
        High flicker rate signals instability or algo churn.
        """
        if len(self.price_history) < 2:
            return 0.0
        
        flickers = sum(
            1 for i in range(1, len(self.price_history))
            if self.price_history[i] != self.price_history[i-1]
        )
        return flickers / (len(self.price_history) - 1)
    


    def get_depth_retreat_score(self) -> float:
        """
        Measures how much liquidity retreats as price approaches.
        High score = passive defense, spoof unwind, or thin order book.

        FIX: Replaced fixed $5 near/far boundary with a bps-scaled threshold.
        At SOL=70k, $5 = 0.007bps — everything was classified as 'far', making
        the score perpetually ~1.0 and the DEPTH_FADE overlay always active.
        Now uses 10bps (~$70 at 70k) as the near/far split, consistent with
        other liquidity metrics in this class.
        """
        mid = self.get_midprice()
        if mid <= 0:
            return 0.0

        # 10bps near/far boundary — $70 at SOL=70k
        threshold = mid * (10.0 / 10000)

        near_bid = sum(size for price, size in self.bids.items() if mid - price < threshold)
        far_bid  = sum(size for price, size in self.bids.items() if mid - price >= threshold)
        near_ask = sum(size for price, size in self.asks.items() if price - mid < threshold)
        far_ask  = sum(size for price, size in self.asks.items() if price - mid >= threshold)

        total_far = far_bid + far_ask
        total_liq = near_bid + near_ask + total_far

        if total_liq == 0:
            return 0.0

        total_levels = len(self.bids) + len(self.asks)
        if total_levels <= 2:
            return 1.0

        return min(total_far / total_liq, 1.0)
    

    def get_slip_response_score(self) -> float:
        """
        Measures how quickly orders retreat after fills.
        High score = fear, spoof unwind, or reactive defense.
        """
        # Placeholder: simulate slip detection using volatility spike
        try:
            vol = self.get_volatility_estimate()
            if vol is None or not isinstance(vol, (float, int)) or math.isnan(vol):
                return 0.0    
            return min(1.0, vol * 20)
        except Exception:
            return 0.0

    def get_bid_aggression(self) -> float:
        """
        Measures how aggressively bids are placed near mid.
        High value = concentrated bid pressure close to the touch.

        FIX: Replaced fixed $3 window with a 5bps-scaled threshold, consistent
        with get_ask_defense(). At SOL=70k, $3 = 0.004bps — virtually nothing
        qualified as 'near', so this always returned ~0 making CROSS_SIDE_TENSION
        and SYNTHETIC_ACCUMULATION unreachable. 5bps = ~$35 at 70k, matching
        the ask_defense window.
        """
        mid = self.get_midprice()
        if mid <= 0:
            return 0.0
        threshold  = mid * (5.0 / 10000)   # 5bps — matches get_ask_defense default
        near_bids  = sum(size for price, size in self.bids.items() if mid - price <= threshold)
        total_bids = self._bid_total
        return near_bids / max(1e-6, total_bids)
    
    def get_ask_defense(self, depth_bps: float = 5.0) -> float:
        """
        Measures liquidity density (ask pressure/resistance) near mid using dynamic BPS.
        High values indicate a dense 'wall' of sell orders close to the mid-price.

        Uses a 50ms TTL cache: both bid and ask defense are computed together on a
        cache miss, so the second call within the same tick window is O(1).
        Uses the incremental _ask_total running total instead of sum(asks.values()).
        """
        # Cause D guard: during a WebSocket reconnect the book is cleared and
        # _snapshot_initialized is False until the REST snapshot re-seeds it.
        # Return 0.5 (neutral) rather than computing from an empty book which
        # would produce 0.0 and drive composite_score toward 1.0 (unfavourable),
        # triggering a spurious emergency tighten on every reconnect cycle.
        if not self._snapshot_initialized:
            return 0.5

        import time as _time
        now = _time.monotonic()
        if now - self._defense_cache_ts < self._defense_cache_ttl:
            return self._defense_ask_cache

        mid = self.get_midprice()
        if mid <= 0:
            return 0.0

        threshold = mid * (depth_bps / 10000)

        near_bids = sum(s for p, s in self.bids.items() if (mid - p) <= threshold)
        near_asks = sum(s for p, s in self.asks.items() if (p - mid) <= threshold)

        self._defense_bid_cache = near_bids / max(1e-6, self._bid_total)
        self._defense_ask_cache = near_asks / max(1e-6, self._ask_total)
        self._defense_cache_ts = now
        return self._defense_ask_cache

    def get_bid_defense(self, depth_bps: float = 5.0) -> float:
        """Measures liquidity density near mid using dynamic BPS.

        Uses the same 50ms TTL cache as get_ask_defense() — call either first,
        the other is a cache hit.
        """
        # Cause D guard: return 0.5 neutral during reconnect/snapshot gap.
        if not self._snapshot_initialized:
            return 0.5

        import time as _time
        now = _time.monotonic()
        if now - self._defense_cache_ts < self._defense_cache_ttl:
            return self._defense_bid_cache

        mid = self.get_midprice()
        if mid <= 0:
            return 0.0

        threshold = mid * (depth_bps / 10000)

        near_bids = sum(s for p, s in self.bids.items() if (mid - p) <= threshold)
        near_asks = sum(s for p, s in self.asks.items() if (p - mid) <= threshold)

        self._defense_bid_cache = near_bids / max(1e-6, self._bid_total)
        self._defense_ask_cache = near_asks / max(1e-6, self._ask_total)
        self._defense_cache_ts = now
        return self._defense_bid_cache
    
    def get_imbalance_momentum(self, lookback_periods: int = 10) -> float:
        """
        Robust Imbalance Momentum:
        Measures the velocity and acceleration of book pressure changes.

        Returns:
            float: Range [-1.0, 1.0].
                Positive (>0.05): Bid pressure is accelerating (Bullish/Spoofing Bid).
                Negative (<-0.05): Ask pressure is accelerating (Bearish/Spoofing Ask).

        Accesses deque directly by index — no full copy, no allocation.
        """
        n = len(self.imbalance_history)
        if n < lookback_periods:
            return self.get_layered_imbalance() - 0.5

        # Deques support O(1) indexed access from both ends
        current_imb = self.imbalance_history[-1]

        # Window SMA: sum the last lookback_periods entries
        recent_sum = sum(self.imbalance_history[i] for i in range(n - lookback_periods, n))
        window_sma = recent_sum / lookback_periods
        velocity = current_imb - window_sma

        # Acceleration: compare to prior window if enough history exists
        if n > lookback_periods:
            prev_start = n - lookback_periods - 1
            prev_sum = sum(self.imbalance_history[i] for i in range(prev_start, prev_start + lookback_periods))
            prev_sma = prev_sum / lookback_periods
            prev_velocity = self.imbalance_history[-2] - prev_sma
            acceleration = velocity - prev_velocity
            return (velocity * 0.7) + (acceleration * 0.3)

        return velocity
    

    def get_top_levels(self, side: str, depth_levels: int = 5) -> list:
        """Returns the top N price levels and sizes for the given side."""
        book = self.bids if side in ("bid", "b") else self.asks
        if not book:
            return []
        levels = sorted(book.items(), key=lambda x: x[0], reverse=(side in ("bid", "b")))
        return levels[:depth_levels]
    



    def get_nearest_support_resistance(self, side: str, base_window_bps: float = 50.0) -> Optional[float]:
        """Finds the largest volume cluster within a volatility-scaled window."""
        vol = self.get_volatility_estimate()
        # Expand window if market is chaotic
        dynamic_window = base_window_bps * max(1.0, vol * 1000)
        
        mid = self.get_midprice()
        limit = mid * (dynamic_window / 10000)
        
        book = self.bids if side == "bid" else self.asks
        # Only look at orders within the dynamic window
        # Single pass — no intermediate dict allocation
        best_price = None
        best_size  = -1.0
        for p, s in book.items():
            if abs(p - mid) <= limit and s > best_size:
                best_size  = s
                best_price = p
        return best_price
    


    def _fetch_symbol_info_internal(self) -> None:
        """
        Internal method to fetch exchange filters directly from Binance 
        without external dependencies.
        """
        try:
            # Avoid frequent API calls
            now = time.time()
            if now - self._last_info_update < self._update_interval:
                return

            # Fetch futures exchange info (matches your SOLUSDT target)
            url = "https://fapi.binance.com/fapi/v1/exchangeInfo"
            response = requests.get(url, timeout=10)
            data = response.json()

            for s in data.get('symbols', []):
                if s['symbol'] == self.symbol:
                    for f in s.get('filters', []):
                        if f['filterType'] == 'PRICE_FILTER':
                            self._tick_size = float(f['tickSize'])
                            logger.info(f"{Fore.GREEN}Updated internal tick_size: {self._tick_size}")
                            break
            
            self._last_info_update = now
        except Exception as e:
            logger.error(f"Internal symbol info fetch failed: {e}. Using fallback {self._tick_size}")

    def get_tick_size(self) -> float:
        """
        Public getter for the symbol tick size.

        Pure O(1) cached read — no REST call, no blocking, under any
        circumstance. _tick_size is initialised to 0.1 in __init__ as a safe
        default and overwritten once at startup via set_tick_size()
        (orchestration.run() -> initialize_symbol_info()). The value is
        stable for the lifetime of a trading session and never needs
        mid-session refresh.

        Cause K fix: the previous TTL-gated _fetch_symbol_info_internal()
        fallback used blocking requests.get() (up to 10s). OrderBook has no
        reference to exchange_client, so there is no way to trigger the async
        refresh path from here — and the original __init__ comment already
        establishes that OrderBook is constructed AFTER the event loop is
        running, so any blocking call here (even as a fallback) reproduces
        the exact freeze this fix removes. Returning the safe default and
        logging CRITICAL is the only option that is simultaneously fast,
        non-stalling, and correct in the only realistic failure case
        (a startup-ordering regression, which this log makes impossible to miss).
        """
        if self._tick_size and self._tick_size > 0:
            return self._tick_size

        logger.critical(
            "[ORDERBOOK] get_tick_size() returned an invalid cached value "
            "(_tick_size=%s) — set_tick_size() may not have run at startup. "
            "Returning safe default 0.1. Check startup initialisation order.",
            self._tick_size,
        )
        return 0.1