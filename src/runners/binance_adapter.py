#execution/ binance_adapter.py
from Execution_layer.symbol_info_manager import SymbolInfoManager, SymbolFilters

import json
import re
import traceback
import asyncio
import time
import hmac
import hashlib
import urllib.parse
from typing import Optional, Callable, Dict, Any, List, Tuple
import aiohttp
from dynamic_risk_engine.throttle_cooldown_manager_protocol import ThrottleCooldownManagerProtocol
import logging
from colorama import Fore, Style, init

init(strip=True)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("[Binance_Adapter]")

# 1. Add the NullHandler: This consumes all logs without outputting them
#logger.addHandler(logging.NullHandler())

# 2. Stop propagation: This prevents logs from being sent to the console/root logger
#logger.propagate = False



DEFAULT_RECV_WINDOW = 60000 #ms 60 seconds instead of 5
DEFAULT_SYMBOL = "SOLUSDT"


class CachedBalanceProvider:
    """
    Single source of truth for account balance across all callers.

    Without this, every component that needs the balance — health check,
    diagnostics, position sizer, drawdown manager — fires its own
    /fapi/v2/account call (weight 5 each). At 10-second polling intervals
    across 3-4 callers this adds up to 100-200 weight/min from monitoring
    alone before any trading activity.

    This class replaces all of those with:
      - One REST call to /fapi/v2/balance (weight 1, not 5) every 30 s max.
      - Zero-cost push updates from the WebSocket ACCOUNT_UPDATE event
        (balance is sent by Binance automatically on every fill).

    Every module that previously called get_account_balance() directly
    should call exchange_client.balance_cache.get() instead.
    """

    def __init__(self, adapter: "BinanceExecutionAdapter", ttl_seconds: float = 30.0):
        self._adapter = adapter
        self._ttl = ttl_seconds
        self._cached: float = 0.0
        self._last_fetch: float = 0.0
        self._lock = asyncio.Lock()

    async def get(self) -> float:
        """Return cached balance, hitting REST only when the TTL has expired."""
        now = time.time()
        if self._last_fetch > 0 and now - self._last_fetch < self._ttl:
            return self._cached
        async with self._lock:
            now = time.time()
            if self._last_fetch > 0 and now - self._last_fetch < self._ttl:
                return self._cached  # another coroutine refreshed while we waited
            try:
                self._cached = await self._adapter.get_account_balance()
                self._last_fetch = time.time()
                logger.debug("[BALANCE_CACHE] REST refresh: $%.2f", self._cached)
            except Exception as e:
                logger.warning("[BALANCE_CACHE] REST refresh failed, using stale value: %s", e)
                # Cause C fix: set _last_fetch to a partial TTL backoff so the
                # next get() waits 10s before retrying.  Without this, every
                # subsequent get() call immediately tries the REST API again
                # (since _last_fetch stays at 0), turning a single API failure
                # into a continuous retry storm that saturates the semaphore.
                self._last_fetch = time.time() - self._ttl + 10.0
            
            return self._cached

    def update_from_ws(self, balance: float) -> None:
        """Called from handle_user_event on ACCOUNT_UPDATE — zero REST cost."""
        if balance > 0:
            self._cached = balance
            self._last_fetch = time.time()
            logger.debug("[BALANCE_CACHE] WS push update: $%.2f", balance)

    @property
    def cached_value(self) -> float:
        """Last known balance without triggering a refresh. Safe to call anywhere."""
        return self._cached

    def invalidate(self, soft: bool = False) -> None:
        """Force next get() to hit the REST API.
 
        Args:
            soft: If True, schedule a refresh within the next 5 s rather than
                  immediately.  Use this from auto-resume paths where a fresh
                  balance is needed soon but not instantly — avoids adding an
                  immediate REST call to an already-saturated semaphore.
                  If False (default), forces the very next get() to REST.
                  Only use False when accuracy is critical (e.g. post-withdrawal).
        """
        if soft:
            # Cause K fix: soft invalidation — sets _last_fetch to (ttl - 5s)
            # so the cache looks "about to expire" and the next scheduled get()
            # (within 5s) triggers a fresh REST call, rather than forcing it
            # immediately and competing with other concurrent REST callers.
            self._last_fetch = time.time() - self._ttl + 5.0
        else:
            self._last_fetch = 0.0

class BinanceExecutionAdapter:
    """
    Async Binance REST adapter (signed) for order placement, cancellation and status.
    Integration notes:
        - This adapter does NOT open a user-data websocket by itself.
        You should run your existing Binance WS runner (listenKey) and when it recieves
        ORDER_TRADE_UPDATE or execution reports, call adapter.handle_user_event(payload)
        so the adapter can invoke on_fill_callback(...) for fills.
        -It consults a ThrottleCooldownManager (if Provided) before making requests and 
        records weight/order/cancel/trade events back into it
    """


    def __init__(
            self,
            throttle: ThrottleCooldownManagerProtocol,
            symbol: str = "SOLUSDT",
            api_key: str = None,
            api_secret: str = None,
            base_url: str ="https://fapi.binance.com",
            session: Optional[aiohttp.ClientSession] = None,
            market_type: str = "futures",
            **kwargs
    ):
        #if "testnet" not in base_url.lower():
        #    raise RuntimeError("Adapter locked to BINANCE FUTURES TESTNET only")

        self.api_key : str = api_key
        # Pre-encode once — used by every signed request
        self._api_secret_bytes: bytes = api_secret.encode("utf-8") if api_secret else b""
        self.api_secret : str = api_secret
        assert market_type in ("spot", "futures", "perpetual")
        self.market_type = market_type
        # Boolean fast-path used in hot loops instead of repeated `in` tuple checks
        self._is_futures: bool = market_type in ("futures", "perpetual")
        self.base_url : str = base_url.rstrip("/")

        self.session : Optional[aiohttp.ClientSession] = session #May be none at init
        self._closed : bool = False
        self._lock : asyncio.Lock = asyncio.Lock() #serialize signed request creation if needed

        #Optional integration objects
        self.throttle = throttle
        self.on_fill_callback: Optional[Callable[[Dict[str, Any]], None]] = None

        self._recv_window = kwargs.get("default_recv_window", DEFAULT_RECV_WINDOW)
        self.default_symbol = symbol

        # Approximate weight cost mapping (for our throttle manager)
        self._endpoint_weight = {
            # Trading critical path
            "/fapi/v1/order": 1,
            "/fapi/v1/openOrders": 1,
            "/fapi/v1/allOpenOrders": 1,
            "/fapi/v2/positionRisk": 5,
            "/fapi/v2/account": 5,
            "/fapi/v2/balance": 1,   # Cheap balance-only endpoint (weight 1 vs 5 for /account)

            # Algo order endpoints (SL/TP placement — used on every fill)
            "/fapi/v1/algoOrder": 1,
            "/fapi/v1/algoOrder/cancel": 1,
            "/fapi/v1/openAlgoOrders": 1,
            "/fapi/v1/algoOrderHistory": 1,
            # Listen key / user data stream
            "/fapi/v1/listenKey": 1,
            # Exchange info (heavy — only fetched once but weight is significant)
            "/fapi/v1/exchangeInfo": 40,
            # Time sync
            "/fapi/v1/time": 1,
            # Cause H fix: endpoints called by background monitors that were missing
            # and defaulting to weight=1.  Correct weights ensure ThrottleCooldownManager
            # counts actual consumption and throttles before Binance responds with
            # 429/418 under cascade REST load.
            "/fapi/v1/userTrades": 5,
            "/fapi/v1/income": 30,
            "/fapi/v2/positionSide/dual": 1,
            "/fapi/v1/leverageBracket": 1,
        }

        # Pre-built endpoint maps — avoids creating a new dict on every _get_endpoint() call
        self._futures_endpoints: Dict[str, str] = {
            "place": "/fapi/v1/order",
            "cancel": "/fapi/v1/order",
            "status": "/fapi/v1/order",
            "positions": "/fapi/v2/positionRisk",
            "account": "/fapi/v2/account",
        }
        self._spot_endpoints: Dict[str, Optional[str]] = {
            "place": "/api/v3/order",
            "cancel": "/api/v3/order",
            "status": "/api/v3/order",
            "positions": None,
            "account": "/api/v3/account",
        }

        # Pre-computed exponential backoff values (index = attempt number)
        self._backoffs: tuple = (1.0, 2.0, 4.0, 8.0, 16.0)

        # Semaphore: cap concurrent outbound REST calls to 8.
        # Without this, a burst of parallel callers (SL/TP placement, order
        # status polls, health checks) can saturate the connector pool and
        # produce spurious "connection reset" errors under load.
        #
        # Cause C fix: split into two priority classes so background monitors
        # (SLTP monitor, orphan clean, health check) cannot starve the critical
        # trading path (has_open_position, place_order, etc.).
        # _rest_semaphore       - trading/critical path (6 slots)
        # _monitor_rest_semaphore - background monitor calls (2 slots)
        # Total concurrent REST calls is still capped at 8.
        self._rest_semaphore: asyncio.Semaphore = asyncio.Semaphore(6)
        self._monitor_rest_semaphore: asyncio.Semaphore = asyncio.Semaphore(2)

        # Cause B/C/E fix: shared circuit-breaker state for IP bans (HTTP 418).
        # Without this, each coroutine independently discovers the ban, backs
        # off, and retries - 7+ concurrent callers synchronously thrashing
        # against the ban (release -> hit ban -> fail -> release -> retry)
        # which extends the ban duration with every cycle.
        # _ip_banned_until is a monotonic timestamp; while time.monotonic() is
        # less than this value, ALL callers (new and already-waiting) fail
        # fast with no network call, giving Binance's ban timer a real chance
        # to expire instead of being continuously reset.
        self._ip_banned_until: float = 0.0
        self._ip_ban_lock: asyncio.Lock = asyncio.Lock()

        #Optional: Carry venue fee truth here; applied in coordiantor
        self.fee_schedule = None #will be populated by sync_fees()

        # ADD THIS: Initialize time Offset
        self.time_offset_ms = 0 # Add this line

        # Initialize symbol info manager
        self.symbol_info_manager = SymbolInfoManager(self)
        self._symbol_info: Optional[SymbolFilters] = None

        # Shared cached balance — all callers use this instead of get_account_balance() directly
        self.balance_cache = CachedBalanceProvider(self, ttl_seconds=30.0)
    @property
    def recv_window(self) -> int:
        """Read-only: prevents accidental narrowing of the recvWindow (Cause E)."""
        return self._recv_window
        
    async def initialize_symbol_info(self, symbol: str):
        """
        Fetch and cache symbol trading rules from Binance
        MUST be called before placing orders
        """
        try:
            self._symbol_info = await self.symbol_info_manager.get_symbol_info(symbol)
            
            # ----------------------------------------------------------------
            # PROFITABILITY FIX: Raise the floor from $15.0 to $5.0.
            # Small trades lose money to fees and tick-size rounding.
            # ----------------------------------------------------------------
            PROFIT_FLOOR = 5.0
            original_min = float(self._symbol_info.min_notional)
            self._symbol_info.min_notional = max(original_min, PROFIT_FLOOR)

            logger.info(
                "%s[BINANCE ADAPTER] Symbol info initialized for %s\n"
                "  Min Notional: $%s (Exchange: $%s)\n"
                "  Tick Size: %s\n"
                "  Step Size: %s",
                Fore.GREEN, symbol,
                self._symbol_info.min_notional, original_min,
                self._symbol_info.tick_size,
                self._symbol_info.step_size,
            )
            return self._symbol_info
        except Exception as e:
            logger.error("%s[BINANCE ADAPTER] Failed to initialize symbol info: %s", Fore.RED, e)
            raise

    async def _request(self, method: str, path: str, signed: bool = False, params: Optional[Dict] = None, max_retries: int = 3) -> Dict[str, Any]:
        """Generic request method for public (unsigned) endpoints with retry on transient errors."""
        
        # Cause B/C/E fix: same shared ban check as _signed_request(). The IP
        # ban applies to ALL requests regardless of signed/unsigned - public
        # endpoints (sync_server_time, etc.) must also fail fast.
        _now = time.monotonic()
        if _now < self._ip_banned_until:
            _remaining = self._ip_banned_until - _now
            raise RuntimeError(
                "Binance IP ban (HTTP 418) active - %.0fs remaining. "
                "Request blocked before network call. " % _remaining

            )
        
        # Cause K fix: unsigned requests previously bypassed throttle entirely.
        # sync_server_time() and other public-endpoint calls were invisible to
        # the throttle manager's weight tracking.
        weight = self._endpoint_weight.get(path, 1)
        if self.throttle:
            if self.throttle.is_throttled():
                raise RuntimeError("Request throttled: would exceed limit")
 

        session = await self._get_session()
        url = self.base_url + path
        headers = {}

        if signed:
            headers["X-MBX-APIKEY"] = self.api_key

        if params:
            url = url + "?" + urllib.parse.urlencode(params)

        last_error: Optional[Exception] = None
        for attempt in range(max_retries):
            try:
                async with session.request(method, url, headers=headers) as resp:
                    if resp.status >= 400:
                        text = await resp.text()
                        raise RuntimeError("Binance API Error %d: %s" % (resp.status, text))
                    result = await resp.json()
                    # Cause K fix: record weight on success, same pattern as _signed_request.

                    if self.throttle:
                        self.throttle.record_order(volume=0.0, weight=weight)
                    return result
                
            except aiohttp.ClientError as net_err:
                err_name = type(net_err).__name__
                err_detail = str(net_err) or "<no detail>"
                last_error = net_err
                if attempt < max_retries - 1:
                    backoff = self._backoffs[attempt]
                    logger.warning(
                        "%s[API/_request] Network error (%s: %s) on attempt %d/%d — retrying in %.0fs",
                        Fore.YELLOW, err_name, err_detail, attempt + 1, max_retries, backoff,
                    )
                    try:
                        if self.session and not self.session.closed:
                            await self.session.close()
                    except Exception:
                        pass
                    self.session = None
                    session = await self._get_session()
                    await asyncio.sleep(backoff)
                else:
                    raise RuntimeError(
                        "Binance network error after %d attempts (%s: %s)" % (max_retries, err_name, err_detail)
                    ) from net_err
        raise RuntimeError(
            "Binance API Error: all %d attempts failed for %s%s" % (
                max_retries, path, (" — last error: %s" % last_error) if last_error else ""
            )
        )


    def _set_base_url(self):
        """Market Mode Awareness - Preserve testnet if provided"""
        # Check if we're already using testnet
        is_testnet = "testnet" in self.base_url.lower()
        
        if self.market_type in ("futures", "perpetual"):
            if is_testnet:
                # Keep testnet URL
                if "fapi" not in self.base_url and "binancefuture" not in self.base_url:
                    self.base_url = "https://testnet.binancefuture.com"
                # else: already correct testnet URL, keep it
            else:
                # Use mainnet
                self.base_url = "https://fapi.binance.com"
        else:  # spot
            if is_testnet:
                self.base_url = "https://testnet.binance.vision"
            else:
                self.base_url = "https://api.binance.com"


    # Lines 202-210: _set_base_url() simplified for mainnet
    #def _set_base_url(self):
    #    """Market Mode Awareness - Mainnet production URLs"""
    #    if self.market_type in ("futures", "perpetual"):
    #        self.base_url = "https://fapi.binance.com"
    #    else:
    #        self.base_url = "https://api.binance.com"


    
    def _get_endpoint(self, action: str) -> str:
        """End point Routing: When placing, modifying, or cancelling orders, dynamically choose endpoints"""
        is_futures = self.market_type in ("futures", "perpetual")
        mapping = self._futures_endpoints if is_futures else self._spot_endpoints
        return mapping[action]

    # ------------------ Low-Level helpers --------------------------
    
    def _sign(self, data: str) -> str:
        """Create a Binance HMAC SHA256 signature"""
        return hmac.new(self._api_secret_bytes, data.encode("utf-8"), hashlib.sha256).hexdigest()
    
    def _sign_params(self, params: dict) -> str:
        """
        Takes a dict of params, URL-encodes it and returns HMAC-SHA256 signature
        """
        query_string = urllib.parse.urlencode(params)
        return self._sign(query_string)
    
    # Add time sync helpers for binance server time (Location: BinanceExecutionAdapter)
    async def sync_server_time(self, force: bool = False) -> int:
        """
        Query Binance server time and compute local offset in milliseconds.
        Stores offset in self.time_offset_ms and returns it.

        Args:
            force: If True, bypass the 60s TTL and always fetch fresh server time. 
            Pass force=True from the -1021 retry path so that each retry uses a genuinely
            fresh offset rather than the stale one that just caused the rejection.
            
        Cause G fix: TTL-gated (60s) for the periodic heartbeat calls.
        Cause C fix: force=True bypasses TTL for -1021 recovery; on failure, 
                    _last_time_sync_ts is cleared so the TTL doesn't block 
                    the next sync attempt for 60s after a failed sync.
        """

        # Fast path: offset was synced recently
        _now = time.time()
        _last_sync = getattr(self, "_last_time_sync_ts", 0.0)
        _SYNC_TTL = 60.0
        
        if not force and _now - _last_sync < _SYNC_TTL and self.time_offset_ms != 0:
            logger.debug(
                "%s[TIME SYNC] Reusing cached offset %d ms (synced %.0fs ago)",
                Fore.GREEN, self.time_offset_ms, _now - _last_sync,
            )
            return self.time_offset_ms
        

        try:
            # Use correct endpoint based on market type
            if self.market_type in ("futures", "perpetual"):
                endpoint = "/fapi/v1/time" 
            else:
                endpoint = "/api/v3/time" 

            # Using your existing _request method for public endpoints
            resp = await self._request('GET', endpoint, signed=False)
            server_ts = int(resp.get('serverTime', 0))
            local_ms = int(time.time() * 1000)
            
            # Calculate and store the drift
            offset = server_ts - local_ms
            self.time_offset_ms = offset 
            self._last_time_sync_ts = time.time()

            
            logger.debug("%s[TIME SYNC] Server time synced, Offset: %d ms", Fore.GREEN, offset)
            return offset
        
        except Exception as e:
            # Preserve existing offset if present, otherwise default to 0
            self.time_offset_ms = getattr(self, 'time_offset_ms', 0)
            
            # Cause C fix: clear _last_time_sync_ts on failure so the TTL
            # doesn't block the next sync attempt for 60s. Without this,
            # a failed sync would prevent any retry for the full TTL window.
            self._last_time_sync_ts = 0.0
            logger.warning("%s[TIME SYNC] Could not sync server time: %s", Fore.RED, e)
            return self.time_offset_ms
    
    async def fetch_trading_fees(self) -> dict:
        """
        Fetch current maker/taker commission rates from Binance Futures account.
        Returns rates in basis points (bps).
        
        Raises:
            RuntimeError: If fees cannot be retrieved from Binance API.
        """
        try:
            response = await self._signed_request("GET", "/fapi/v1/commissionRate", {"symbol": self.default_symbol})
            
            maker_bps = response.get("makerCommissionRate")
            taker_bps = response.get("takerCommissionRate")
            
            if maker_bps is None or taker_bps is None:
                raise RuntimeError(
                    "Binance API response missing commission data. "
                    f"Response: {response}"
                )
            
            # Convert from decimal string (e.g., 0.0002) to bps (e.g., 2.0 bps)
            maker_bps = float(maker_bps) * 1000  # Convert to bps
            taker_bps = float(taker_bps) * 1000  # Convert to bps
            
            logger.info(
                "%s[Binance Adapter] ✅ Fees retrieved: Maker=%sbps (%.4%%%), Taker=%sbps (%.4%%%)",
                Fore.GREEN, maker_bps, maker_bps / 1e4, taker_bps, taker_bps / 1e4,
            )
            
            return {
                "maker_bps": maker_bps,
                "taker_bps": taker_bps
            }
            
        except Exception as e:
            logger.error(
                "%s[Binance Adapter] ❌ CRITICAL: Failed to fetch trading fees\n"
                "  Error: %s: %s\n"
                "  Cannot proceed without accurate fee data.",
                Fore.RED, type(e).__name__, e,
            )
            raise RuntimeError(
                "Failed to retrieve trading fees from Binance: %s" % e
            ) from e

    async def sync_fees(self):
        """
        Synchronize fee schedule with live Binance account data.
        
        Raises:
            RuntimeError: If fees cannot be retrieved.
        """
        fees = await self.fetch_trading_fees()
        self.fee_schedule = fees
        return fees


    def get_fee_schedule(self) -> dict:
        """
        Get current fee schedule.
        
        Raises:
            RuntimeError: If fees have not been synced yet.
        """
        if self.fee_schedule is None:
            raise RuntimeError(
                "Fee schedule not initialized. "
                "Call sync_fees() before trading."
            )
        return dict(self.fee_schedule)

    def _now_ms(self) -> int:
        """Returns local time adjusted by the calculated server offset."""
        return int(time.time() * 1000) + self.time_offset_ms
    
    async def _monitor_signed_request(self, method: str, path: str, params: Optional[Dict] = None, max_retries: int = 2) -> Dict:
        """
        Cause C Fix: background-priority wrapper around _signed_request().

        Background monitors (SL/TP monitor, orphan cleanup, health check) must
        use this instead of _signed_request() directly. It acquires the 
        _monitor_rest_semaphore (2 slots) BEFORE entering _signed_request which
        acquires the _rest_semaphore (6 slots). This means background REST calls
        can never starve the 6 trading-paths slots - at worst they hold 2 of the 8
        total outbound sockets, leaving 6 always available for on_new_alpha().

        Cause G fix: max_retries defaults to 2 (not 3) so background calls have a
        worst-case backoff of 1+2+3s instead of 1+2+4=7s. This prevents a degraded connection
        from keeping the monitor semaphore slots locked for longer than 30s on_new_alpha() watchdog budget.

        Drop-in replacement: same signature and return type as _signed_request().


        """
        async with self._monitor_rest_semaphore:
            return await self._signed_request(method, path, params, max_retries)
    
    def is_ip_banned(self) -> bool:
        """
        True if a Binance IP ban (HTTP 418) is currently active.
        
        Cause I fix: callers like _trading_task() should check this BEFORE 
        calling has_open_position()/on_new_alpha() so the trading loop can 
        pause entirely during a ban instead of firing a REST call every 
        iteration that's guaranteed to fail-fast and do nothing productive.
        """
        return time.monotonic() < self._ip_banned_until

    def is_in_post_ban_grace_period(self, grace_seconds: float = 15.0) -> bool:
        """
        Fix: True while still actively banned OR within `grace_seconds` after
        a ban has just lifted.

        is_ip_banned() alone only covers the active-ban window. Diagnostic
        evidence (orphaned algo orders returning -2011 "Unknown order sent"
        on cancel, shortly after a ban lifted, despite appearing in a fresh
        get_open_algo_orders() listing seconds earlier) shows the same class
        of risk — stale/phantom exchange state — persists for a short window
        immediately after recovery too. Binance's own order/algo-order book
        can lag behind what a freshly-unblocked REST call reports. Callers
        that make protection-critical decisions from exchange state
        (verifying SL/TP still exists, classifying "orphaned" orders) should
        treat this grace period the same as an active ban: defer rather than
        act on data that might not have caught up yet.
        """
        if self._ip_banned_until <= 0:
            return False  # never been banned
        if self.is_ip_banned():
            return True
        return (time.monotonic() - self._ip_banned_until) < grace_seconds
        
        
    def get_ban_remaining_seconds(self) -> float:
        """
        Seconds remaining on the active ban, or 0.0 if no ban is active.
        """
        remaining = self._ip_banned_until - time.monotonic()
        return max(0.0, remaining)

    def get_monitor_semaphore(self) -> asyncio.Semaphore:
        """
        Returns the lower-priority semaphore for background monitoring REST calls.

        Cause C fix: background loops (SL/TP monitor, orphan cleanup, health check)
        must use this semaphore via:
            async with self.exchange_client.get_monitor_semaphore():
            
        instead of going through _signed_request directly without a slot, which previously
        allowed monitor calls to saturate the 8-slot pool and starve the critical on_new_alpha() trading path.
        """

        return self._monitor_rest_semaphore
    
    
    async def _get_session(self) -> aiohttp.ClientSession:
        """
        Return a long-lived, SSL-verified ClientSession with a connection pool.

        Connection reuse rationale:
          - A bare aiohttp.ClientSession() with no connector opens a fresh TCP
            handshake + TLS negotiation on every request (~100-200 ms overhead).
          - TCPConnector maintains a per-host keep-alive pool so subsequent
            requests reuse the open TCP connection.
          - limit_per_host=10 caps concurrent sockets to a single host.
          - use_dns_cache=True avoids repeated DNS lookups.
          - certifi CA bundle gives us Mozilla-curated SSL roots — prevents MITM.
        """
        
        if self.session is None or self.session.closed:
            import ssl as _ssl
            import certifi as _certifi
            _ssl_ctx = _ssl.create_default_context(cafile=_certifi.where())
            _connector = aiohttp.TCPConnector(
                ssl=_ssl_ctx,
                limit=20,
                limit_per_host=10,
                use_dns_cache=True,
                ttl_dns_cache=30,
                keepalive_timeout=60,
                enable_cleanup_closed=True,
            )
            self.session = aiohttp.ClientSession(
                connector=_connector,
                connector_owner=True,
            )
        return self.session

    async def _signed_request(self, method: str, path: str, params: Optional[Dict] = None, max_retries: int = 3) -> Dict:
        # Cause B/C/E fix: fast-fail on a shared ban state BEFORE doing anything
        # else (before _get_session(), before the semaphore). This is what 
        # actually stops the thrashing pattern - every one of the 6-8 concurrent 
        # callers checks this on every call, so none of them even attempt a 
        # request while a ban is active, regardless of how many are queued.
        _now = time.monotonic()
        if _now < self._ip_banned_until:
            _remaining = self._ip_banned_until - _now
            raise RuntimeError(
                "Binance IP ban (HTTP 418) active - %.0fs remaining. "
                "Request blocked before network call to avoid extending the ban. " %_remaining
            )
            
        session = await self._get_session()

        # Copy params before adding timestamp/recvWindow so we can log the clean payload later
        log_params = params.copy() if params else {}

        weight = self._endpoint_weight.get(path, 1)
        if self.throttle:
            if self.throttle.is_throttled():
                raise RuntimeError("Request throttled: would exceed limit")
            # self.throttle.record_order(volume=0.0, weight=weight)
            # Cause L fix: record_order() is called AFTER a successful response
            # (See inside the success branch below) so weight is counted exactly
            # once per logical operation, not once per attempt on retry.

        headers = {"X-MBX-APIKEY": self.api_key}

        last_error: Optional[Exception] = None

        for attempt in range(max_retries):
            backoff: Optional[float] = None
            needs_time_sync: bool = False


            try:
                # Semaphore: at most 8 concurrent REST calls at once (6 trading + 2 monitor).
                # The inner _lock only prevents response-body interleaving on the
                # shared session; the semaphore prevents saturation of the TCP pool.
                #
                # Cause C fix: _lock now only wraps the response body read, NOT the
                # full network round-trip.  Previously, if asyncio.wait_for() cancelled
                # on_new_alpha() while it was inside session.request(), the CancelledError
                # would propagate through __aexit__ of the _lock context manager and
                # release it correctly — but the session.request() coroutine itself was
                # still completing in the background, meaning the connection slot stayed
                # occupied.  By separating the network I/O from the lock we ensure the
                # lock is never held across an await that the watchdog can cancel.
                async with self._rest_semaphore:

                    # --- Build signed URL (fast path, no lock needed — each attempt gets own copy) ---
                    # Cause H fix: timestamp is computed INSIDE the semaphore, just
                    # before signing. Previously it was computed before acquiring the 
                    # semaphore, so any semaphore wait > (recvWindow - latency) made 
                    # the request arrive at Binance with a stale timestamp, triggering
                    # -1021 regardless of clock synchronisation status.

                    params_copy = params.copy() if params else {}
                    params_copy["timestamp"] = self._now_ms()
                    params_copy["recvWindow"] = self.recv_window

                    query = urllib.parse.urlencode(params_copy, doseq=True)
                    signature = self._sign(query)
                    url = "%s%s?%s&signature=%s" % (self.base_url, path, query, signature)


                    async with self._lock:
                        async with session.request(method, url, headers=headers) as resp:
                            text = await resp.text()
 
                        # --- Rate limit / IP ban ---
                        if resp.status == 418:
                           
                            
                            # Cause B/C/D/E fix: set the SHARED ban state so every 
                            # other concurrent caller (already queued on the semaphore, or about to start)
                            # fails fast at the top of _signed_request() with zero network cost - this is
                            # what actually stops the thrashing pattern described 
                            # in Causes B and E, where each coroutine independently
                            # discovers the ban and retries, extending it further.
                            #
                            # Escalating the ban duration: Binance's documented minimum 
                            # is 2 minutes for a first offense. If we hit another 
                            # 418 while a previous ban window is still fresh (within 
                            # the last 10 minutes), double the wait, capped at 1 hour,
                            # since repeated bans indicate escalting severity.
                            _prior_ban_recent = (time.monotonic() - getattr(self, "_last_ban_ts", 0.0)) < 600.0
                            
                            _ban_duration = 240.0 if _prior_ban_recent else 120.0
                            _ban_duration = min(_ban_duration, 3600.0)
                            
                            self._ip_banned_until = time.monotonic() + _ban_duration
                            self._last_ban_ts = time.monotonic()
                            
                            logger.critical(
                                "%s[API] IP BAN (HTTP 418) - ALL REST callers blocked for %.0fs. "
                                "This is a hard exchange-level ban; existing positions may be "
                                "unprotected (SL/TP cannot be verified or replaced) until it clears.",
                                Fore.RED, _ban_duration
                            )
                            
                            
                            raise RuntimeError(
                                "Binance IP ban (HTTP 418) — all requests blocked for %.0fs. "
                                "Reduce REST call volume before retrying." % _ban_duration
                            )

                        elif resp.status == 429:
                            backoff = self._backoffs[min(attempt, len(self._backoffs) - 1)]
                            logger.warning(
                                "%s[API] Rate limit (HTTP 429) on attempt %d/%d — backing off %.0fs",
                                Fore.YELLOW, attempt + 1, max_retries, backoff,
                            )

                        # --- Timestamp drift ---
                        elif resp.status >= 400 and "-1021" in text and "Timestamp" in text:
                            logger.warning(
                                "%s[TIMESTAMP ERROR] Clock drift on attempt %d/%d: %s",
                                Fore.YELLOW, attempt + 1, max_retries, text,
                            )
                            needs_time_sync = True
                            backoff = 0.5
 
                        # --- Other 4xx / 5xx ---
                        elif resp.status >= 400:
                            # Fix: -2011 on a DELETE (cancel) and -2013 on a
                            # DELETE/GET mean the target order is simply gone —
                            # filled, expired, or never persisted. That's the
                            # expected, benign outcome of a cancel racing a
                            # fill, not an actionable failure — downstream
                            # callers already treat it that way. Logging it at
                            # ERROR here, before any caller gets a chance to
                            # interpret it, floods errors.log with noise for
                            # something that isn't actually a problem.
                            try:
                                _body = json.loads(text)
                                _code = _body.get("code", 0)
                            except Exception:
                                _code = 0

                            _is_benign = (
                                method.upper() in ("DELETE", "GET")
                                and _code in (-2011, -2013)
                            )
                            _log_fn = logger.debug if _is_benign else logger.error
                            _log_fn(
                                "%s%s\n%s!!! BINANCE API REJECTION !!!\n"
                                "%s  Path:   %s\n%s  Params: %s\n"
                                "%s  HTTP:   %d\n%s  Body:   %s\n%s%s",
                                Fore.RED, "=" * 54,
                                Fore.RED, Fore.RED, path, Fore.RED, log_params,
                                Fore.RED, resp.status, Fore.RED, text,
                                Fore.RED, "=" * 54,
                            )
                            raise RuntimeError("Binance API Error %d: %s" % (resp.status, text))
 
                        # --- Success ---
                        else:
                            # Cause L fix: record weight exactly once, on success.
                            if self.throttle:
                                self.throttle.record_order(volume=0.0, weight=weight)

                            # Prefer resp.json() (aiohttp native, also works with test mocks
                            # that implement async json()); fall back to json.loads(text)
                            # for any edge case where only text() is available.
                            if hasattr(resp, 'json') and callable(resp.json):
                                try:
                                    return await resp.json(content_type=None)
                                except TypeError:
                                    # Mock's json() doesn't accept content_type kwarg
                                    return await resp.json()
                            return json.loads(text)
 
            except asyncio.CancelledError:
                # Cause C fix: re-raise immediately so the watchdog's cancellation
                # of on_new_alpha() propagates correctly.  Without this, the broad
                # except clauses below could catch CancelledError on Python versions
                # where it inherits from BaseException but not Exception — keeping
                # the coroutine alive past the watchdog timeout.
                raise
            except aiohttp.ClientError as net_err:
                err_name = type(net_err).__name__
                err_detail = str(net_err) or "<no detail>"
                if attempt < max_retries - 1:
                    backoff = self._backoffs[min(attempt, len(self._backoffs) - 1)]
                    logger.warning(
                        "%s[API] Network error (%s: %s) on attempt %d/%d — "
                        "reconnecting session and retrying in %.0fs",
                        Fore.YELLOW, err_name, err_detail, attempt + 1, max_retries, backoff,
                    )
                    try:
                        if self.session and not self.session.closed:
                            await self.session.close()
                    except Exception:
                        pass
                    self.session = None
                    session = await self._get_session()
                    last_error = net_err
                else:
                    raise RuntimeError(
                        "Binance network error after %d attempts (%s: %s)" % (max_retries, err_name, err_detail)
                    ) from net_err
 

            # ----------------------------------------------------------------
            # Release the lock BEFORE any sleep so SL/TP monitor and other
            # concurrent callers are not blocked during backoff waits.
            # ----------------------------------------------------------------
            if needs_time_sync:
                # Cause C fix: force=True bypasses the 60s TTL so we always
                # get a fresh offset on -1021 retries rather than reusing the
                # same stale offset that just caused the rejection
                await self.sync_server_time(force=True)  # done outside the lock

            if backoff is not None:
                if attempt < max_retries - 1:
                    await asyncio.sleep(backoff)
                    continue
                break

        raise RuntimeError(
            "Binance API Error: all %d attempts failed for %s%s" % (
                max_retries, path, (" — last error: %s" % last_error) if last_error else ""
            )
        )
    
    
    
    async def _load_symbol_filters(self, symbol: str) -> Dict[str, Any]:
        """
        Fetch symbol trading rules (filters) from Binance Futures exchangeInfo.
        """
        endpoint = "/fapi/v1/exchangeInfo" if self.market_type in ("futures", "perpetual") else "/api/v3/exchangeInfo"
        resp = await self._request("GET", endpoint, signed=False)
        for s in resp["symbols"]:
            if s["symbol"] == symbol.upper():
                return {f["filterType"]: f for f in s["filters"]}
        raise ValueError(f"Symbol {symbol} not found in exchangeInfo")

    async def _validate_binance_order(
        self, 
        symbol: str, 
        side: str, 
        qty: float,
        price: Optional[float], 
        order_type: str
    ) -> None:
        """
        ✅ IMPROVED: Validate order using live Binance symbol rules
        No more hardcoded values!
        """
        # Ensure symbol info is loaded
        if self._symbol_info is None or self._symbol_info.symbol != symbol.upper():
            await self.initialize_symbol_info(symbol)
        
        info = self._symbol_info
        
        # Validate quantity
        qty_valid, qty_msg = info.validate_quantity(qty, order_type)
        if not qty_valid:
            raise ValueError(f"[QTY VALIDATION] {qty_msg}")
        
        # Validate price (for LIMIT orders)
        if price is not None and order_type != "MARKET":
            price_valid, price_msg = info.validate_price(price)
            if not price_valid:
                raise ValueError(f"[PRICE VALIDATION] {price_msg}")
            
            # Validate notional
            notional_valid, notional_msg = info.validate_notional(qty, price)
            if not notional_valid:
                raise ValueError(f"[NOTIONAL VALIDATION] {notional_msg}")
        
        logger.debug(
            "%s[VALIDATION] ✅ Order passed all checks\n"
            "  Symbol: %s | Side: %s | Type: %s\n"
            "  Qty: %s | Price: %s\n"
            "  Notional: $%.2f",
            Fore.GREEN, symbol, side, order_type, qty, price, qty * (price or 0),
        )

    def round_price(self, price: float, symbol: Optional[str] = None) -> float:
        """
        Round price to valid tick_size for the symbol
        
        Args:
            price: Raw price value
            symbol: Trading pair (uses default if None)
        
        Returns:
            Rounded price compliant with Binance tick_size
        """
        if self._symbol_info is None:
            logger.warning("[ROUND PRICE] Symbol info not loaded, using raw price")
            return round(price, 2)
        
        return self._symbol_info.round_price(price)
    
    def round_quantity(
        self, 
        qty: float, 
        order_type: str = "LIMIT",
        symbol: Optional[str] = None
    ) -> float:
        """
        Round quantity to valid step_size for the symbol
        
        Args:
            qty: Raw quantity value
            order_type: "LIMIT" or "MARKET" (affects step_size used)
            symbol: Trading pair (uses default if None)
        
        Returns:
            Rounded quantity compliant with Binance step_size
        """
        if self._symbol_info is None:
            logger.warning("[ROUND QTY] Symbol info not loaded, using raw qty")
            return round(qty, 6)
        
        return self._symbol_info.round_quantity(qty, order_type)
    
    def get_min_order_qty(
        self, 
        price: float, 
        order_type: str = "LIMIT"
    ) -> float:
        """
        Get minimum order quantity that satisfies both LOT_SIZE and MIN_NOTIONAL
        
        Args:
            price: Order price (current market price for MARKET orders)
            order_type: "LIMIT" or "MARKET"
        
        Returns:
            Minimum valid quantity
        """
        if self._symbol_info is None:
            logger.error("[MIN QTY] Symbol info not loaded!")
            return 0.01  # Dangerous fallback
        
        return self._symbol_info.get_min_order_qty(price, order_type)

    # -----------------------Public API -------------------------------

    async def place_order(
            self,
            symbol: Optional[str] = None,
            side: str = "BUY",
            type: str = "MARKET",
            quantity: Optional[float] = None,
            price: Optional[float] = None,
            time_in_force: Optional[str]=None,
            reduce_only: bool = False,
            close_position: bool = False,
            position_side: str = "BOTH",
            working_type: str = "CONTRACT_PRICE",
            new_client_order_id: Optional[str] = None,
            self_trade_prevention_mode: Optional[str] = None,
            price_protect: Optional[bool] = None,
            good_till_date: Optional[int] = None,
            price_match: Optional[str] = None,
            **extra: Any,
        ) -> Dict[str, Any]:
            """
            Place an order (async) compatible with both SPOT and FUTURES (perpetual) Binance APIs.
            
            ✅ FIXED: This method now ONLY places entry orders.
            SL/TP are placed separately via place_stop_loss_order() and place_take_profit_order()

            Args:
                symbol (str): Trading pair, e.g. "SOLUSDT".
                side (str): "BUY" or "SELL".
                type (str): Binance order type ("MARKET", "LIMIT", "STOP_MARKET", etc.)
                quantity (float): Order size in base units.
                price (float, optional): Limit price (for LIMIT or STOP_LIMIT orders).
                time_in_force (str): GTC/IOC/FOK; only for limit-type orders.
                reduce_only (bool): True for futures reduce-only orders.
                close_position (bool): True to close open futures position.
                position_side (str): "LONG", "SHORT", or "BOTH".
                working_type (str): "MARK_PRICE" or "CONTRACT_PRICE" (futures).
                new_client_order_id (str, optional): Custom order ID.
                **extra: Extra keyword arguments for adapter integration.
                
            Returns:
                Dict[str, Any]: Binance API JSON response.
            """
            symbol = (symbol or self.default_symbol).upper()

            # ENSURE SYMBOL INFO IS LOADED
            if self._symbol_info is None or self._symbol_info.symbol != symbol:
                await self.initialize_symbol_info(symbol)
            

            # ROUND VALUES TO BINANCE REQUIREMENTS
            original_quantity = quantity # Store original for logging

            if quantity is not None:
                quantity = self.round_quantity(quantity, type)
                if quantity != original_quantity:
                    logger.debug("[ROUNDING] QTY adjusted: %s -> %s", original_quantity, quantity)
            
            if price is not None:
                original_price = price
                price = self.round_price(price)
                if price != original_price:
                    logger.debug("[Rounding] Price adjusted: %s -> %s", original_price, price)
            # VALIDATE AGAINST LIVE RULES (Once !)
            try:
                await self._validate_binance_order(symbol, side, quantity, price, type)
            except ValueError as e:
                logger.error("%s[ORDER REJECTED] %s", Fore.RED, e)
                raise

            # CHECK MIN NOTIONAL (with Safety buffer)
            if price and quantity:
                notional = quantity * price
                min_notional = self._symbol_info.min_notional

                # Add 5% safety buffer
                safe_min = min_notional * 1.05

                if notional < safe_min:
                    # Auto-adjust quantity to meet minimum
                    new_qty = self.get_min_order_qty(price, type)
                    logger.warning(
                        "%s[AUTO-ADJUST] NOTIONAL $%.2f < $%.2f\n Adjust qty: %s -> %s",
                        Fore.YELLOW, notional, safe_min, quantity, new_qty,
                    )
                    quantity = new_qty
                    original_quantity = new_qty #Update for logging

            logger.info(
                "\n%s%s\n%s[BINANCE API] place_order()\n%s%s\n"
                "%s  Symbol: %s\n%s  Side: %s\n%s  Type: %s\n"
                "%s  Quantity: %s\n%s  Price: %s\n%s  Time In Force: %s\n"
                "%s  Working Type: %s\n%s  Position Side: %s\n"
                "%s  Reduce Only: %s\n%s  Self Trade Prevention: %s\n"
                "%s  Price Protect: %s\n%s%s",
                Fore.LIGHTCYAN_EX, "=" * 70,
                Fore.LIGHTCYAN_EX, Fore.LIGHTCYAN_EX, "=" * 70,
                Fore.LIGHTCYAN_EX, symbol,
                Fore.LIGHTCYAN_EX, side,
                Fore.LIGHTCYAN_EX, type,
                Fore.LIGHTCYAN_EX, original_quantity,
                Fore.LIGHTCYAN_EX, price if price else "MARKET",
                Fore.LIGHTCYAN_EX, time_in_force,
                Fore.LIGHTCYAN_EX, working_type,
                Fore.LIGHTCYAN_EX, position_side,
                Fore.LIGHTCYAN_EX, reduce_only,
                Fore.LIGHTCYAN_EX, self_trade_prevention_mode,
                Fore.LIGHTCYAN_EX, price_protect,
                Fore.LIGHTCYAN_EX, "=" * 70,
            )

            # --------------------- Sanity checks ------------------------
            assert side in ("BUY", "SELL"), "side must be BUY or SELL"
            assert type in ("MARKET", "LIMIT", "STOP_MARKET", "TAKE_PROFIT_MARKET", "STOP_LIMIT", "TAKE_PROFIT_LIMIT"), \
                f"Unsupported order type: {type}"

            endpoint = "/fapi/v1/order"  # default to futures

            # Format to exact step/tick decimal precision to avoid float noise
            # e.g. 0.18000000000000002 -> "0.18"
            def _precision(step: float) -> int:
                from decimal import Decimal
                return max(0, -Decimal(str(step)).as_tuple().exponent)

            if quantity and self._symbol_info:
                step = (self._symbol_info.market_step_size
                        if type == "MARKET"
                        else self._symbol_info.step_size)
                formatted_qty = f"{quantity:.{_precision(step)}f}"
            else:
                formatted_qty = str(quantity) if quantity else None

            if price and self._symbol_info:
                formatted_price = f"{price:.{_precision(self._symbol_info.tick_size)}f}"
            else:
                formatted_price = str(price) if price else None


            # --------------------- Payload build ------------------------
            payload: Dict[str, Any] = {
                "symbol": symbol,
                "side": side,
                "type": type,
            }

            if self_trade_prevention_mode:
                payload['selfTradePreventionMode'] = self_trade_prevention_mode

            if price_protect is not None:
                payload["priceProtect"] = price_protect

            if good_till_date:
                payload["goodTillDate"] = good_till_date
            
            if price_match:
                payload['priceMatch'] = price_match

            # Optional custom client order ID
            if new_client_order_id:
                payload["newClientOrderId"] = new_client_order_id

            # Limit / Market handling - USING FORMATTED STRINGS FOR QUANTITY/PRICE
            if type == "MARKET":
                payload["quantity"] = formatted_qty
            elif type == "LIMIT":
                payload.update({
                    "quantity": formatted_qty,
                    "price": formatted_price,
                    "timeInForce": time_in_force,
                })
            elif type in ("STOP_MARKET", "TAKE_PROFIT_MARKET"):
                # Note: stopPrice would be set here if this was a stop/TP order
                # But we now use separate methods for those
                payload.update({
                    "quantity": formatted_qty,
                    "closePosition": close_position,
                })
            elif type in ("STOP_LIMIT", "TAKE_PROFIT_LIMIT"):
                payload.update({
                    "quantity": formatted_qty,
                    "price": formatted_price,
                    "timeInForce": time_in_force,
                })

            # --------------------- Futures-specific fields ------------------------
            if self._is_futures:
                payload.update({
                    "reduceOnly": reduce_only,
                    "positionSide": position_side,
                    "workingType": working_type,
                })

            # Merge any additional fields passed from ExecutionCoordinator
            payload.update(extra)

            logger.debug("%s[PAYLOAD] %s", Fore.CYAN, json.dumps(payload, indent=2))

            # --------------------- Throttle & Request ------------------------
            if self.throttle:
                if self.throttle.is_throttled():
                    logger.error("%s[THROTTLE] ❌ Request blocked", Fore.LIGHTRED_EX)
                    raise RuntimeError("Throttled: trade limit reached")
                # Use the original quantity for throttle recording (pre-override value)
                self.throttle.record_order(volume=original_quantity or 0.0)
                logger.debug("%s[THROTTLE] ✅ Passed", Fore.GREEN)

            # --------------------- Send Signed Request ------------------------
            # ====================================================================
            # SEND ENTRY ORDER (ONLY - SL/TP handled separately now)
            # ====================================================================

            try:
                logger.info("%s[API REQUEST] Sending signed request to Binance...", Fore.LIGHTMAGENTA_EX)

                # Filter out None values before sending to API
                final_payload = {k: v for k, v in payload.items() if v is not None}
                response = await self._signed_request("POST", endpoint, final_payload) # Use final_payload

                logger.info(
                    "%s%s\n%s[API SUCCESS] ✅ Order placed!\n%s%s\n%sResponse:\n%s\n%s%s",
                    Fore.GREEN, "=" * 70,
                    Fore.GREEN, Fore.GREEN, "=" * 70,
                    Fore.GREEN, json.dumps(response, indent=2),
                    Fore.GREEN, "=" * 70,
                )
            except Exception as e:
                # NOTE: Do NOT use type(e).__name__ here — the parameter named 'type'
                # shadows Python's built-in type() function, causing TypeError when called.
                # Use e.__class__.__name__ instead.
                #
                # Fix: _signed_request() already logs path/params/HTTP status/body
                # at ERROR before raising — no need to repeat those here. This log
                # is kept (unlike the simpler cancel/query methods) because it adds
                # information _signed_request() doesn't have: the fully-formatted
                # order payload actually sent, and a traceback pinpointing where in
                # place_order() itself the failure was caught.
                try:
                    payload_str = json.dumps(final_payload, indent=2)
                except Exception:
                    payload_str = str(final_payload)
                logger.error(
                    "%s[API ERROR] ❌ place_order() failed: %s: %s\n"
                    "  Payload: %s\n%s",
                    Fore.LIGHTRED_EX, e.__class__.__name__, e,
                    payload_str,
                    traceback.format_exc(),
                )

                raise

            # ==============================================================
            # NORMALIZE RESPONSE (no SL/TP here - handled separately)
            # ==============================================================

            # Optional: normalize response for Coordinator (uniform format)
            normalized = {
                "orderId": str(response.get("orderId")),
                "clientOrderId": response.get("clientOrderId"),
                "symbol": symbol,
                "side": side,
                "type": type,
                "status": response.get("status", "NEW"),
                # Use original quantity for logs if it's not None, otherwise use the sent quantity
                "price": float(response.get("price", price or 0.0)),
                "origQty": float(response.get("origQty", original_quantity or quantity or 0.0)),
                "executedQty": float(response.get("executedQty", 0.0)),
                "timestamp": response.get("transactTime", self._now_ms()),
                "marketType": getattr(self, "market_type", "spot"),
                "raw": response,
            }

            logger.info("%s[NORMALIZED] OrderID: %s | Status: %s", Fore.GREEN, normalized['orderId'], normalized['status'])

            return normalized

    # ✅ FIX: Add standalone stop-loss order method
    async def place_stop_loss_order(
        self,
        symbol: str,
        side: str,  # "BUY" to close short, "SELL" to close long
        price: float,
        qty: float,
        reduce_only: bool = True,
        position_side: str = "BOTH",
        working_type: str = "MARK_PRICE",
        price_protect: bool = True,
        mark_price: Optional[float] = None,
    ) -> Tuple[str, str]:
        """
        Place a standalone stop-loss order (STOP_MARKET).
 
        Args:
            symbol: Trading pair (e.g., "SOLUSDT")
            side: Exit side - "SELL" for long positions, "BUY" for short positions
            price: Stop trigger price
            qty: Quantity to close
            reduce_only: Must be True for protective stops
            position_side: "BOTH" for one-way mode, "LONG"/"SHORT" for hedge mode
            working_type: "MARK_PRICE" (safer) or "CONTRACT_PRICE" (faster)
            price_protect: Enable price protection against bad fills
            mark_price: Current mark price for -2021 validation. If supplied,
                        used directly (zero REST cost); if None, validation is
                        skipped. Callers should pass orderbook.get_mark_price()
                        rather than leaving this None.
 
        Cause H fix: removed the /fapi/v1/premiumIndex preflight REST call that
        fired on every SL placement (1 extra weight per call, up to 360+ weight
        /minute from SL/TP updates alone at 1/sec heartbeat cadence).
        The orderbook mark_price is updated every second via WebSocket — always
        fresher than a REST call and costs zero weight.
        """
        info = await self.symbol_info_manager.get_symbol_info(symbol)
        formatted_price = info.round_price(price)
        formatted_qty = info.round_quantity(qty, order_type="MARKET")
 
        # -2021 guard using the caller-supplied mark price (zero REST cost).
        if mark_price and mark_price > 0:
            try:
                side_upper = side.upper()
                if side_upper == "SELL" and formatted_price >= mark_price:
                    raise ValueError(
                        f"Stop-loss price ${formatted_price} is at or above current mark price "
                        f"${mark_price:.4f} — would immediately trigger (-2021). "
                        f"Caller should place a market exit instead."
                    )
                elif side_upper == "BUY" and formatted_price <= mark_price:
                    raise ValueError(
                        f"Stop-loss price ${formatted_price} is at or below current mark price "
                        f"${mark_price:.4f} — would immediately trigger (-2021). "
                        f"Caller should place a market exit instead."
                    )
            except ValueError:
                raise
        
        payload = {
            "symbol": symbol.upper(),
            "side": side.upper(),
            "algoType": "CONDITIONAL",  # Required for conditional orders
            "type": "STOP_MARKET",  # Algo Order API uses 'type', not 'orderType'
            "triggerPrice": formatted_price,
            "quantity": formatted_qty,
            "reduceOnly": reduce_only,
            "positionSide": position_side,
            "workingType": working_type,
            "priceProtect": price_protect,
        }
        
        endpoint = "/fapi/v1/algoOrder"
        
        try:
            response = await self._signed_request("POST", endpoint, payload)
            algo_id = str(response.get("algoId"))
            order_id = str(response.get("orderId", ""))  # regular exchange orderId for WS matching
 
            logger.info(
                "%s✅ Stop-Loss placed: algoId=%s orderId=%s | Side %s | Trigger $%s | Qty %s",
                Fore.GREEN, algo_id, order_id, side, formatted_price, formatted_qty,
            )
            return algo_id, order_id  # (algoId for REST ops, orderId for WS matching)
            
        except Exception:
            # Fix: _signed_request() already logs the full rejection detail
            # (path, params, HTTP status, body) at the appropriate level before
            # raising — logging again here just duplicates it in errors.log
            # with less detail, for every single failure.
            raise

    # ✅ FIX: Add standalone take-profit order method
    async def place_take_profit_order(
        self,
        symbol: str,
        side: str,  # "BUY" to close short, "SELL" to close long
        price: float,
        qty: float,
        reduce_only: bool = True,
        position_side: str = "BOTH",
        working_type: str = "MARK_PRICE",
        price_protect: bool = True,
        mark_price: Optional[float] = None,
    ) -> Tuple[str, str]:
        """
        Place a standalone take-profit order (TAKE_PROFIT_MARKET).
        
        Args:
            symbol: Trading pair (e.g., "SOLUSDT")
            side: Exit side - "SELL" for long positions, "BUY" for short positions
            price: Take-profit trigger price
            qty: Quantity to close
            reduce_only: Must be True for protective TPs
            position_side: "BOTH" for one-way mode, "LONG"/"SHORT" for hedge mode
            working_type: "MARK_PRICE" (safer) or "CONTRACT_PRICE" (faster)
            price_protect: Enable price protection against bad fills
            mark_price: Current mark price for -2021 validation. If supplied,
                        used directly (zero REST cost); if None, validation is
                        skipped. Callers should pass orderbook.get_mark_price()
                        rather than leaving this None.

        Cause D fix: place_stop_loss_order had a mark-price crossing guard;
        place_take_profit_order had none. A TP computed against a stale or
        re-anchored price could be sent already past mark, either instantly
        filling (and then being misread as "invalid" by status polling) or
        getting rejected — both cases wasted a REST call during exactly the
        moments (IP ban recovery, high volatility) when REST budget matters
        most. This mirrors the SL guard so bad geometry is caught locally
        before it reaches the exchange.

        Returns:
            str: Order ID of the created take-profit order
        """
        # Format values to Binance precision
        info = await self.symbol_info_manager.get_symbol_info(symbol)

        formatted_price = info.round_price(price) 
        formatted_qty = info.round_quantity(qty, order_type="MARKET")

        # -2021 guard using the caller-supplied mark price (zero REST cost).
        if mark_price and mark_price > 0:
            side_upper = side.upper()
            if side_upper == "SELL" and formatted_price <= mark_price:
                raise ValueError(
                    f"Take-profit price ${formatted_price} is at or below current mark price "
                    f"${mark_price:.4f} — would immediately trigger (-2021) or fill instantly "
                    f"instead of protecting the position. Caller should recompute against a "
                    f"fresher price or place a market exit instead."
                )
            elif side_upper == "BUY" and formatted_price >= mark_price:
                raise ValueError(
                    f"Take-profit price ${formatted_price} is at or above current mark price "
                    f"${mark_price:.4f} — would immediately trigger (-2021) or fill instantly "
                    f"instead of protecting the position. Caller should recompute against a "
                    f"fresher price or place a market exit instead."
                )

        payload = {
            "symbol": symbol.upper(),
            "side": side.upper(),
            "algoType": "CONDITIONAL",  # Required for conditional orders
            "type": "TAKE_PROFIT_MARKET",  # Algo Order API uses 'type', not 'orderType'
            "triggerPrice": formatted_price,
            "quantity": formatted_qty,
            "reduceOnly": reduce_only,
            "positionSide": position_side,
            "workingType": working_type,
            "priceProtect": price_protect,
        }
        
        endpoint = "/fapi/v1/algoOrder"
        
        try:
            response = await self._signed_request("POST", endpoint, payload)
            algo_id = str(response.get("algoId"))
            order_id = str(response.get("orderId", ""))

            logger.info(
                "%s✅ Take-Profit placed: algoId=%s orderId=%s | Side %s | Trigger $%s | Qty %s",
                Fore.GREEN, algo_id, order_id, side, formatted_price, formatted_qty,
            )
            return algo_id, order_id
        
        except Exception:
            # Fix: same rationale as place_stop_loss_order — _signed_request()
            # already logs the full rejection detail before raising.
            raise
    
    async def cancel_algo_order(self, symbol: str, order_id: str):
        """
        Cancel an algo order (stop-loss or take-profit) by algo ID.
        
        Args:
            symbol: Trading pair
            algo_id: The algo order ID to cancel
            
        Returns:
            dict: Cancellation response
        """
        payload = {
            "symbol": symbol.upper(),
            "algoId": order_id,
        }
        
        endpoint = "/fapi/v1/algoOrder"
        
        try:
            response = await self._signed_request("DELETE", endpoint, payload)
            logger.info("%s🗑️ Algo order %s cancelled", Fore.YELLOW, order_id)
            return response
            
        except Exception:
            # Fix: same rationale — _signed_request() already logs the full
            # rejection detail (and, as of the benign-code fix above, logs it
            # at DEBUG rather than ERROR for -2011/-2013 on this exact
            # cancel path, since that specific outcome just means the order
            # is already gone, not a real failure).
            raise


    # ✅ FIX: Add cancel by ID helper
    async def cancel_order_by_id(self, symbol: str, order_id: str):
        """
        Cancel order by ID (wrapper for coordinator compatibility). for both regular and algo orders
        
        Args:
            symbol: Trading pair
            order_id: Order ID to cancel (as string)
            
        Returns:
            Dict: Cancellation response
        """
        # Try regular order cnacellation first
        try:
            return await self.cancel_order(symbol=symbol, orderId=int(order_id))
        except Exception as e:
            #If regular cancellation fails, try algo order cancellation
            logger.warning("Regular cancel failed, trying algo cancel: %s", e)
            return await self.cancel_algo_order(symbol, order_id)
    
    # ====================================================================
    # ADDITIONAL HELPER: GTD Integration
    # ====================================================================
    def _determine_entry_tif_and_gtd(self, order_type: str, urgency_high: bool, 
                                    is_sliced: bool) -> tuple[Optional[str], int]:
        """
        DEAD METHOD — do not call.

        resolve_time_in_force() and _determine_gtd() live on ExecutionCoordinator,
        not on BinanceExecutionAdapter. Calling this would raise AttributeError.
        TIF/GTD resolution is handled by ExecutionCoordinator._determine_entry_tif_and_gtd()
        before the order reaches the adapter.

        Kept here to avoid import errors from any legacy callers; raises immediately
        so the bug surfaces loudly instead of silently producing wrong orders.
        """
        raise NotImplementedError(
            "_determine_entry_tif_and_gtd() is not implemented on BinanceExecutionAdapter. "
            "Call ExecutionCoordinator._determine_entry_tif_and_gtd() instead."
        )
        
    async def modify_order(self, symbol: str, orig_order_id: Optional[int] = None, orig_client_order_id: Optional[str] = None,
                           new_price: Optional[float] = None, new_qty: Optional[float] = None,
                           new_client_order_id: Optional[str] = None, max_wait_ms: int = 2000) -> Dict[str, Any]:
        
        """
        Attempt to modify an existing order by cancelling it and placing a replacement.
        This is required on Binance (no single modify endpoint). Returns a dict summarizing the result.

        State-machine approach — avoids the fixed 0.15 s sleep-poll loop:
          - On each REST status check the poll interval grows (50 ms → 100 ms → 200 ms)
            so we drain the first result quickly but don't spam the exchange if it's slow.
          - We stop as soon as the order reaches a terminal state or the wall-clock
            budget (max_wait_ms) is exhausted — no wasted CPU on a fixed tick.
        """
        # 1) Cancel original (best-effort)
        try:
            await self.cancel_order(symbol=symbol, orderId=orig_order_id, origClientOrderId=orig_client_order_id)
        except Exception:
            pass

        # 2) Poll order status with exponential backoff until terminal or timeout.
        #    State machine states: PENDING → FILLED | CANCELLED | TIMEOUT
        poll_start_ms = int(time.time() * 1000)
        last_status = None
        # Poll intervals in ms: start fast, grow quickly (50, 100, 200, 400, …)
        poll_interval_ms = 50
        _MAX_POLL_INTERVAL_MS = 400

        while True:
            elapsed_ms = int(time.time() * 1000) - poll_start_ms
            if elapsed_ms >= max_wait_ms:
                break
            try:
                if orig_order_id:
                    st = await self.get_order_status(symbol=symbol, orderId=orig_order_id)
                elif orig_client_order_id:
                    st = await self.get_order_status(symbol=symbol, origClientOrderId=orig_client_order_id)
                else:
                    st = None
                last_status = st
                if st:
                    s = str(st.get('status', '')).lower()
                    if s in ('filled', 'partially_filled', 'partial_filled'):
                        return {'status': 'filled', 'order': st}
                    if s in ('canceled', 'cancelled', 'rejected', 'expired'):
                        break  # terminal — proceed to replacement

            except Exception:
                pass

            # Sleep for current poll interval (capped at budget remaining)
            remaining_ms = max_wait_ms - (int(time.time() * 1000) - poll_start_ms)
            sleep_ms = min(poll_interval_ms, remaining_ms)
            if sleep_ms > 0:
                await asyncio.sleep(sleep_ms / 1000.0)
            poll_interval_ms = min(poll_interval_ms * 2, _MAX_POLL_INTERVAL_MS)
        #3) Place replacement order if symbol is not filled
        place_payload = {'symbol':symbol, 'type':'LIMIT'}
        if new_qty is not None:
            place_payload['quantity'] = new_qty
        
        if new_price is not None:
            place_payload['price'] = new_price
            place_payload['timeInForce'] = 'GTC'

        if new_client_order_id:
            place_payload['newClientOrderId'] = new_client_order_id

        try:
            new_order = await self.place_order(**place_payload)
            return {'status':'replaced','new_order':new_order, 'last_status': last_status}
        except Exception as e:
            return {'status': 'failed', 'reason':str(e), 'last_status': last_status}


    async def cancel_order(self, symbol: Optional[str] = None, orderId: Optional[int] = None, origClientOrderId: Optional[str] = None) -> Dict:
        """
        Cancel an order. Provide orderID or origClientOrderId
        """
        payload = {"symbol": (symbol or self.default_symbol).upper()}
        if orderId:
            payload["orderId"] = orderId
        if origClientOrderId:
            payload["origClientOrderId"] = origClientOrderId

        resp = await self._signed_request("DELETE", "/fapi/v1/order", payload)

        #We count cancels in throttle Manager
        if self.throttle:
            self.throttle.record_cancel()
        return resp
    
    # --------------------------------------------------------
    # Futures-specific helpers
    # --------------------------------------------------------

    async def get_open_positions(self, symbol: str = None) -> List[Dict]:
        """
        Get open positions.
        For futures, this calls get_position_risk and filters for non-zero positions.
        
        Returns:
            List of position dicts with keys:
            - symbol: str
            - size: float (positionAmt, signed)
            - side: str ("BUY" or "SELL")
            - entry_price: float (entryPrice)
            - leverage: int
            - mark_price: float
            - unrealized_pnl: float
        """
        if self._is_futures:
            positions = await self.get_position_risk(symbol)

            # Filter to only positions with non-zero size
            open_positions = []
            for pos in positions:
                amt = float(pos.get("positionAmt", 0))
                if abs(amt) > 0.0001:  # Consider positions > 0.0001
                    open_positions.append({
                        "symbol": pos.get("symbol"),
                        "size": amt,
                        "side": "BUY" if amt > 0 else "SELL",
                        "entry_price": float(pos.get("entryPrice", 0)),
                        "leverage": int(pos.get("leverage", 1)),
                        "mark_price": float(pos.get("markPrice", 0)),
                        "unrealized_pnl": float(pos.get("unRealizedProfit", 0))
                    })
            
            return open_positions
        else:
            # Spot doesn't have positions
            return []


    async def modify_order_sl_tp(
        self,
        position_id: str,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
        position_side: str = "BOTH"
    ) -> Dict[str, Any]:
        """
        Modify Stop-Loss / Take-Profit for an open futures position.

        Args:
            position_id (str): Symbol, e.g. "SOLUSDT".
            stop_loss (float): New stop loss price.
            take_profit (float): New take profit price.
            position_side (str): "LONG", "SHORT", or "BOTH".

        Returns:
            dict: Binance API response(s).
        """
        if not self._is_futures:
            raise RuntimeError("modify_order_sl_tp is only valid for futures/perpetual markets")

        results = {}

        # --- Cancel existing SL/TP first if needed ---
        try:
            open_orders = await self.get_open_orders(symbol=position_id)
            for o in open_orders:
                if o["type"] in ("STOP_MARKET", "TAKE_PROFIT_MARKET"):
                    await self.cancel_order(symbol=position_id, orderId=o["orderId"])
        except Exception as e:
            logger.warning("[BinanceAdapter] Warning: Could not cancel old SL/TP orders: %s", e)

        # --- Recreate Stop Loss order ---
        if stop_loss:
            info = await self.symbol_info_manager.get_symbol_info(position_id)
            sl_payload = {
                "symbol": position_id,
                "side": "SELL",  # Assuming we close long; reversed below if short
                "type": "STOP_MARKET",
                "stopPrice": info.round_price(stop_loss),
                "closePosition": True,
                "positionSide": position_side,
                "workingType": "CONTRACT_PRICE",
            }
            if position_side == "SHORT":
                sl_payload["side"] = "BUY"

            results["stop_loss"] = await self._signed_request("POST", "/fapi/v1/order", sl_payload)

        # --- Recreate Take Profit order ---
        if take_profit:
            info = await self.symbol_info_manager.get_symbol_info(position_id)
            tp_payload = {
                "symbol": position_id,
                "side": "SELL",
                "type": "TAKE_PROFIT_MARKET",
                "stopPrice": info.round_price(take_profit),
                "closePosition": True,
                "positionSide": position_side,
                "workingType": "CONTRACT_PRICE",
            }
            if position_side == "SHORT":
                tp_payload["side"] = "BUY"

            results["take_profit"] = await self._signed_request("POST", "/fapi/v1/order", tp_payload)

        return results



    

    async def get_order_status(self, symbol: str = None, orderId: Optional[int] = None, origClientOrderId: Optional[str] = None, is_algo_id: bool = False) -> Optional[Dict[str, Any]]:
        """
        Query order status by either orderId or origClientOrderId.
        Automatically tries both regular order and algo order endpoints.
        
        Args:
            symbol: Trading symbol (required)
            orderId: Binance order ID (can be regular order ID or algo ID)
            origClientOrderId: Client order ID (our internal ID)
            is_algo_id: Cause I fix - if True, skip the regular-order-endpoint 
                call entirely and go straight to query_algo_order(). Set this 
                when the caller already knows orderId is an algo ID (e.g.
                checking sl_order_id/tp_order_id) to avoid wasting 1 REST call on
                a lookup that will always 404.
        
        Returns:
            Order dict if found (either regular or algo order), None if not found

        Raises:
            ValueError: if neither orderId nor origClientOrderId provided
            RuntimeError: For other API errors
        """
        if not orderId and not origClientOrderId:
            raise ValueError("Must provide either OrderID or origClientOrderId")
        
        symbol = (symbol or self.default_symbol).upper()
        
        # Cause I fix: skip the regular endpoint entirely when the caller
        # already knows this is an algo ID.
        if is_algo_id and orderId:
            algo_resp = await self.query_algo_order(symbol, str(orderId))
            if algo_resp:
                status_map = {
                    "NEW": "NEW", "WORKING": "NEW",
                    "CANCELLED": "CANCELED", "EXPIRED": "EXPIRED", "FILLED": "FILLED",
                }
                return {
                    "orderId": algo_resp.get("algoId"),
                    "symbol": algo_resp.get("symbol"),
                    "status": status_map.get(algo_resp.get("algoStatus"), algo_resp.get("algoStatus")),
                    "type": algo_resp.get("orderType"),
                    "side": algo_resp.get("side"),
                    "price": algo_resp.get("triggerPrice"),
                    "origQty": algo_resp.get("quantity"),
                    "executedQty": "0",
                    "time": algo_resp.get("createTime"),
                    "updateTime": algo_resp.get("updateTime"),
                    "_isAlgoOrder": True,
                }
            return None
            
        # Try regular order endpoint first
        payload = {"symbol": symbol}
        if orderId:
            payload["orderId"] = orderId
        if origClientOrderId:
            payload["origClientOrderId"] = origClientOrderId

        endpoint = self._get_endpoint("status")

        try:
            resp = await self._signed_request("GET", endpoint, payload)

            # Defensive check: ensure resp is a dict
            if not isinstance(resp, dict):
                logger.error(
                    f"{Fore.RED}[GET ORDER STATUS] Unexpected response type: {type(resp)}\n"
                    f" Symbol: {symbol}\n"
                    f" Expected dict, got: {resp}"
                )
                raise RuntimeError(f"Unexpected response type from order status endpoint: {type(resp)}")

            logger.info(
                "%s[GET ORDER STATUS] Found regular order\n"
                " Symbol: %s\n Order ID: %s\n Client Order ID: %s\n Status: %s\n Executed: %s/%s",
                Fore.GREEN, symbol,
                resp.get('orderId'), resp.get('origClientOrderId'),
                resp.get('status'), resp.get('executedQty'), resp.get('origQty'),
            )
        
            return resp

        except Exception as e:
            error_msg = str(e).lower()

            # If order not found in regular endpoint, try algo order endpoint
            if any(phrase in error_msg for phrase in [
                "order does not exist",
                "unknown order",
                "invalid order",
                "-2013"  # Binance error code for order not found
            ]):
                # Try algo order endpoint if we have an orderId
                if orderId:
                    logger.info(
                        "%s[GET ORDER STATUS] Regular order not found, trying algo order\n"
                        "  Symbol: %s\n  Order ID: %s",
                        Fore.CYAN, symbol, orderId,
                    )
                    try:
                        algo_resp = await self.query_algo_order(symbol, str(orderId))
                        if algo_resp:
                            # Convert algo order response to regular order format for compatibility
                            # Map algoStatus to status
                            status_map = {
                                "NEW": "NEW",
                                "WORKING": "NEW", 
                                "CANCELLED": "CANCELED",
                                "EXPIRED": "EXPIRED",
                                "FILLED": "FILLED"
                            }
                            return {
                                "orderId": algo_resp.get("algoId"),
                                "symbol": algo_resp.get("symbol"),
                                "status": status_map.get(algo_resp.get("algoStatus"), algo_resp.get("algoStatus")),
                                "type": algo_resp.get("orderType"),
                                "side": algo_resp.get("side"),
                                "price": algo_resp.get("triggerPrice"),
                                "origQty": algo_resp.get("quantity"),
                                "executedQty": "0",  # Algo orders don't have partial fills
                                "time": algo_resp.get("createTime"),
                                "updateTime": algo_resp.get("updateTime"),
                                "_isAlgoOrder": True  # Mark as algo order
                            }
                    except Exception as algo_e:
                        logger.debug("Algo order query also failed: %s", algo_e)
                
                # Neither regular nor algo order found
                logger.info(
                    "%s[GET ORDER STATUS] Order not found (tried both endpoints)\n"
                    " Symbol: %s\n Client Order ID: %s\n Order ID: %s",
                    Fore.CYAN, symbol, origClientOrderId, orderId,
                )
                return None
            
            # Other errors: _signed_request() already logged the full
            # rejection detail before raising — just propagate.
            raise

    
    
    async def get_account_trades(
            self,
            symbol: str,
            orderId: Optional[int] = None,
            start_time: Optional[int] = None,
            end_time: Optional[int] = None,
            limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """
            Get account trade history
            
            Args:
                symbol: Trading symbol (required)
                order_id: Filter by specific order ID
                start_time: Start time in milliseconds
                end_time: End time in milliseconds
                limit: Max number of trades to return (default 50, max 1000)
            
            Returns:
                List of trade dicts
            
            Example response:
            [
                {
                    "symbol": "SOLUSDT",
                    "id": 28457,
                    "orderId": 12345,
                    "price": "180.5",
                    "qty": "5.0",
                    "quoteQty": "902.5",
                    "commission": "0.9025",
                    "commissionAsset": "USDT",
                    "time": 1642438920000,
                    "buyer": false,
                    "maker": true,
                    "positionSide": "LONG"
                }
            ]
        """

        if self._is_futures:
            endpoint = "/fapi/v1/userTrades"
        else:
            endpoint = "/api/v3/myTrades"

        params = {
            "symbol": symbol.upper(),
            "limit": min(limit, 1000) # Binance max is 1000
        }

        if orderId:
            params["orderId"] = orderId
        if start_time:
            params["startTime"] = start_time
        if end_time:
            params["endTime"] = end_time

        try:
            trades = await self._signed_request("GET", endpoint, params)
            
            logger.info(
                "%s[GET TRADES] Retrieved %d trades\n  Symbol: %s%s%s",
                Fore.GREEN, len(trades), symbol,
                ("\n  Order ID: %s" % orderId) if orderId else "",
                ("\n  Time Range: %s - %s" % (start_time, end_time)) if start_time or end_time else "",
            )
            
            return trades
            
        except Exception:
            # Fix: same rationale — _signed_request() already logs the full
            # rejection detail before raising.
            raise
    
    async def get_all_orders(
        self,
        symbol: str,
        orderId: Optional[int] = None,
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
        limit: int = 1000
    ) -> List[Dict[str, Any]]:
        """
        Get all orders (open, canceled, and filled)
        
        Args:
            symbol: Trading symbol (required)
            order_id: Filter orders >= this orderId
            start_time: Start time in milliseconds
            end_time: End time in milliseconds
            limit: Max number of orders (default 50, max 1000)
        
        Returns:
            List of order dicts (same format as get_order_status)
        """
        if self._is_futures:
            endpoint = "/fapi/v1/allOrders"
        else:
            endpoint = "/api/v3/allOrders"
        
        params = {
            "symbol": symbol.upper(),
            "limit": min(limit, 1000)
        }
        
        if orderId:
            params["orderId"] = orderId
        if start_time:
            params["startTime"] = start_time
        if end_time:
            params["endTime"] = end_time
        
        try:
            orders = await self._signed_request("GET", endpoint, params)
            
            logger.info(
                "%s[GET ALL ORDERS] Retrieved %d orders\n  Symbol: %s%s%s",
                Fore.GREEN, len(orders), symbol,
                ("\n  Order ID >= %s" % orderId) if orderId else "",
                ("\n  Time Range: %s - %s" % (start_time, end_time)) if start_time or end_time else "",
            )
            
            return orders
            
        except Exception:
            # Fix: same rationale — _signed_request() already logs the full
            # rejection detail before raising.
            raise

    def is_timeout_error(self, error: Exception) -> bool:
        """
        Check if an exception is a Binance 408 timeout error
        
        Args:
            error: Exception to check
        
        Returns:
            bool: True if it's a 408 timeout
        """
        error_str = str(error).lower()
        
        # Check for error code -1007
        if "-1007" in error_str:
            return True
        
        # Check for timeout keywords
        timeout_keywords = [
            "timeout waiting for response",
            "send status unknown",
            "execution status unknown",
            "408"
        ]
        
        return any(keyword in error_str for keyword in timeout_keywords)
    
    def parse_error_response(self, error: Exception) -> Dict[str, Any]:
        """
        Parse error response from Binance
        """
        error_str = str(error)
        
        # Try to extract JSON error response
        json_match = re.search(r'\{.*\}', error_str)
        if json_match:
            try:
                error_data = json.loads(json_match.group())
                return {
                    "code": error_data.get("code"),
                    "msg": error_data.get("msg"),
                    "is_timeout": self.is_timeout_error(error),
                    "raw": error_str
                }
            except Exception:
                pass
        
        return {
            "code": None,
            "msg": error_str,
            "is_timeout": self.is_timeout_error(error),
            "raw": error_str
        }
    
    async def get_account(self) -> Dict:
        """Get account info."""
        endpoint = self._get_endpoint("account")
        resp = await self._signed_request("GET", endpoint, {})
        return resp

    
    async def get_account_balance(self) -> float:
        """
        Get available USDT balance.

        Uses /fapi/v2/balance (weight 1) for futures instead of /fapi/v2/account
        (weight 5) — a 5x reduction in API weight for every balance check.

        NOTE: Prefer exchange_client.balance_cache.get() over calling this directly.
        The cache ensures only one REST call fires every 30 s regardless of how many
        components request the balance simultaneously.
        """
        if self._is_futures:
            try:
                resp = await self._signed_request("GET", "/fapi/v2/balance", {})
                assets = resp if isinstance(resp, list) else []
                for a in assets:
                    if a.get("asset") == "USDT":
                        return float(a.get("availableBalance", 0.0))
            except Exception:
                pass  # fall through to full account endpoint

        # Spot or futures fallback
        account = await self.get_account()
        for b in account.get("balances", []):
            if b["asset"] == "USDT":
                return float(b.get("free", 0.0))
        for a in account.get("assets", []):
            if a["asset"] == "USDT":
                return float(a.get("availableBalance", 0.0))
        return 0.0

    async def close(self):
        """Close internal session"""
        if not self._closed:
            if self.session is not None and not self.session.closed:
                await self.session.close()
            self._closed = True


    #---------------------------User -data events --------------------

    async def handle_user_event(self, event: Dict[str, Any]):
        """
        Call this when your Binance user-data ws (listenkey) receives an ORDER_TRADE_UPDATE or execution report.
        The adapter will call on_fill_callback when an actual trade fill occurs.
        Example event payload (partial):
        {
            "e": "executionReport",
            "E": 15970263860000,
            "s": "SOLUSDT",
            "S": "SELL",
            "o": {"x": "TRADE", "X": "FILLED", ...},
            "i": 12345, #order id
            "l" "0.001", #last executed qty
            "L": "45000.0", #Last Executed price

            ...
        }
        """
        #try to detect fills
        try:
            e_type = event.get("e")

            # Log all non-ACCOUNT_UPDATE events so we can see what Binance sends
            # for algo order fills (algoId vs orderId field mapping).
            if e_type not in ("ACCOUNT_UPDATE",):
                logger.info("[WS_RAW_EVENT] type=%s raw=%s", e_type, event)

            # ACCOUNT_UPDATE carries wallet balances — push to cache at zero REST cost.
            # Binance sends this on every fill, funding payment, and withdrawal.
            if e_type == "ACCOUNT_UPDATE":
                for asset in event.get("a", {}).get("B", []):
                    if asset.get("a") == "USDT":
                        try:
                            wb = float(asset.get("wb", 0))  # walletBalance
                            if wb > 0:
                                self.balance_cache.update_from_ws(wb)
                        except (ValueError, TypeError):
                            pass
                return  # nothing else to process for this event type

            if e_type in ("executionReport", "ORDER_TRADE_UPDATE"):
                order_status = event.get("o", {}).get("X") or event.get("X")
                # last executed qty
                last_qty = float(event.get("o",{}).get("l") or event.get("l") or 0.0)
                last_price = float(event.get("o", {}).get("L") or event.get("L") or 0.0)

                if last_qty > 0:
                    # "i" is the child market order ID spawned when the algo triggers.
                    # "si" is the parent algoId — this matches sl_order_id / tp_order_id.
                    inner = event.get("o", {})
                    order_id = inner.get("i") or event.get("i")
                    algo_id = inner.get("si") or event.get("si")
                    symbol = inner.get("s") or event.get("s")
                    side = inner.get("S") or event.get("S")

                    fill = {
                        "timestamp": event.get("E", self._now_ms()),
                        "symbol": symbol,
                        "side": side,
                        "order_id": order_id,
                        "algo_id": algo_id,
                        "qty": last_qty,
                        "price": last_price,
                        "status": order_status,
                        "raw": event,
                    }

                    #record trade volume in throttle manager
                    if self.throttle:
                        self.throttle.record_order(volume=last_qty)


                    #callback to execution coordinator
                    if self.on_fill_callback:
                        #allow both sync & async callbacks
                        res = self.on_fill_callback({
                            "orderId": str(fill["order_id"]),
                            "algoId": str(fill["algo_id"]) if fill["algo_id"] else None,
                            "price": fill["price"],
                            "timestamp": fill["timestamp"],
                            "qty": fill["qty"],
                            "side": fill["side"],
                            "status": fill["status"],
                            "symbol": fill["symbol"],
                            "raw": fill["raw"],
                        })
                        if asyncio.iscoroutine(res):
                            # Cause D fix: dispatch as a background task so the WS
                            # reader loop is not blocked by _on_fill()'s REST calls
                            # (place SL + place TP, up to 15s under API stress).
                            # Blocking here previously prevented pong frames from
                            # being processed, causing the ping timeout cascade.
                            asyncio.create_task(res, name="on_fill")

        except Exception as ex:
            # Keep adapter robust - Log or rethrow in your production logger
            logger.error("[BinanceAdapter] handle_user_event_error: %s", ex)

    async def get_open_orders(self, symbol: Optional[str] = None, monitor_priority: bool = False) -> list[Dict[str, Any]]:
        """
        Retrieve ALL open orders for the account (or filtered by symbol).
        
        Args:
            symbol (str, optional): Filter by symbol (e.g., "SOLUSDT"). 
                                    If None, returns all open orders.
            monitor_priority: If True, uses the lower-priority monitor semaphore.
                Set True from background loops (orphan cleanup, SL/TP monitor)
        
        Returns:
            list[dict]: List of open order dictionaries from Binance API.
                        Each order contains: orderId, symbol, side, type, price, 
                        origQty, status, timeInForce, etc.
        
        Example response:
            [
                {
                    "orderId": 12345,
                    "symbol": "SOLUSDT",
                    "side": "BUY",
                    "type": "LIMIT",
                    "price": "180.5",
                    "origQty": "0.1",
                    "status": "NEW",
                    "timeInForce": "GTC",
                    ...
                }
            ]
        """
        endpoint = "/fapi/v1/openOrders"  # Futures endpoint
        
        params = {}
        if symbol:
            params["symbol"] = symbol.upper()
        
        _request_fn = self._monitor_signed_request if monitor_priority else self._signed_request
        
        try:
            response = await _request_fn("GET", endpoint, params)
            
            logger.debug(
                "%s[GET_OPEN_ORDERS] Retrieved %d open orders%s",
                Fore.GREEN, len(response), (" for %s" % symbol) if symbol else "",
            )
            
            return response
            
        except Exception:
            # Fix: same rationale — _signed_request()/_monitor_signed_request()
            # already log the full rejection detail before raising.
            raise

    async def get_open_algo_orders(self, symbol: Optional[str] = None, monitor_priority: bool = False) -> list[Dict[str, Any]]:
        """
        Retrieve open ALGO (CONDITIONAL) orders for the account or filtered by symbol.

        Algo orders placed via /fapi/v1/algoOrder are stored separately from regular
        orders and are NOT returned by /fapi/v1/openOrders. This endpoint must be
        used to list/cancel SL and TP orders placed by place_stop_loss_order() and
        place_take_profit_order().

        As of December 9, 2025, Binance migrated all conditional orders (STOP_MARKET,
        TAKE_PROFIT_MARKET, STOP, TAKE_PROFIT, TRAILING_STOP_MARKET) to the Algo Service.

        NOTE: This endpoint may not be available on Binance testnet. If endpoint
        returns 404 error, gracefully returns empty list.

        Endpoint: GET /fapi/v1/openAlgoOrders
        Documentation: https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Current-All-Algo-Open-Orders

        Args:
            symbol: Filter by symbol.
            monitor_priority: If True, uses the lower-priority monitor semaphore.
                Set True from background loop (orphan cleanup, SL/TP monitor).

        Returns:
            list[dict]: List of open algo order dicts. Each contains:
                        algoId, clientAlgoId, symbol, side, algoType, orderType,
                        triggerPrice, quantity, algoStatus, etc.
                        Returns empty list if endpoint unavailable (testnet).

        Note: This endpoint may not be available on Binance testnet.
        """
        # Correct endpoint per Binance API documentation (updated Dec 2025)
        endpoint = "/fapi/v1/openAlgoOrders"
        
        # Cause F fix: 2s TTL cache keyed by symbol.  _verify_sl_order() and
        # _verify_tp_order() run concurrently via asyncio.gather() and each
        # independently call this endpoint for the SAME symbol within the same
        # instant — previously 2 REST calls where 1 would do.  The cache is
        # intentionally short (2s) so it never masks a genuinely stale order
        # state; it only deduplicates calls that arrive within the same
        # monitoring tick.
        _cache_key = (symbol or "").upper()
        _now = time.time()
        if not hasattr(self, "_open_algo_orders_cache"):
            self._open_algo_orders_cache: Dict[str, tuple] = {}
        _cached = self._open_algo_orders_cache.get(_cache_key)
        if _cached is not None and (_now - _cached[0]) < 2.0:
            logger.debug(
                "%s[GET_OPEN_ALGO_ORDERS] Cache hit for %s (age=%.2fs)",
                Fore.CYAN, _cache_key or "ALL", _now - _cached[0],
            )
            return _cached[1]

        params = {}
        if symbol:
            params["symbol"] = symbol.upper()

        _request_fn = self._monitor_signed_request if monitor_priority else self._signed_request

        try:
            response = await _request_fn("GET", endpoint, params)
            
            # Response is an array of algo orders (not wrapped in 'orders' field)
            orders = response if isinstance(response, list) else []

            # Cache write after fetching orders.
            self._open_algo_orders_cache[_cache_key] = (_now, orders)
            
            # Demoted to DEBUG — this polls every ~10s and filled orders.log
            # with hundreds of identical lines per minute with no signal value.
            logger.debug(
                "%s[GET_OPEN_ALGO_ORDERS] Retrieved %d open algo orders%s",
                Fore.GREEN, len(orders), (" for %s" % symbol) if symbol else "",
            )

            return orders

        except RuntimeError as e:
            error_msg = str(e)
            if "404" in error_msg and ("-5000" in error_msg or "Path" in error_msg or "invalid" in error_msg.lower()):
                env = "testnet" if "testnet" in self.base_url.lower() else "production"
                logger.warning(
                    "%s[GET_OPEN_ALGO_ORDERS] Algo orders endpoint not available on %s. "
                    "This is expected on testnet. Returning empty list.",
                    Fore.YELLOW, env,
                )
                return []
            else:
                logger.error("%s[GET_OPEN_ALGO_ORDERS] Failed to fetch open algo orders: %s", Fore.RED, e)
                raise
        except Exception:
            # Fix: same rationale — _signed_request()/_monitor_signed_request()
            # already log the full rejection detail before raising.
            raise
            
    async def get_algo_order_status(self, symbol: str, algo_id: str) -> Optional[Dict[str, Any]]:
        """Query /fapi/v1/algoOrder for SL/TP orders placed via the algo endpoint."""
        symbol = (symbol or self.default_symbol).upper()
        algo_resp = await self.query_algo_order(symbol, str(algo_id))

        if algo_resp is None:
            logger.warning("[GET ALGO ORDER STATUS] algoId=%s not found on %s", algo_id, symbol)
            return None

        status_map = {
            "NEW": "NEW", "WORKING": "NEW",
            "CANCELLED": "CANCELED", "CANCELED": "CANCELED",
            "EXPIRED": "EXPIRED", "FILLED": "FILLED",
        }
        return {
            "orderId": algo_resp.get("algoId"),
            "symbol": algo_resp.get("symbol"),
            "status": status_map.get(str(algo_resp.get("algoStatus", "")).upper(), algo_resp.get("algoStatus")),
            "type": algo_resp.get("orderType"),
            "side": algo_resp.get("side"),
            "price": algo_resp.get("triggerPrice"),
            "origQty": algo_resp.get("quantity"),
            "executedQty": algo_resp.get("executedQty", "0"),
            "_isAlgoOrder": True,
        }

    def get_symbol_info(self) -> Optional[SymbolFilters]:
        """Get cached symbol info"""
        return self._symbol_info
    
    def get_min_notional(self) -> float:
        """Get minimum notional value for current symbol"""
        if self._symbol_info is None:
            logger.warning("[MIN NOTIONAL] Symbol info not loaded, using default $100")
            return 100.0
        return self._symbol_info.min_notional
    
    @property
    def min_notional(self) -> float:
        """
        Property accessor for min_notional so callers can use
        ``getattr(exchange_client, 'min_notional', 5.0)`` without special-casing.
        Falls back to 5.0 (Binance USDT-M default) if symbol info is not yet loaded.
        """
        if self._symbol_info is None:
            return 5.0  # safe default; real value populated after initialize_symbol_info()
        return self._symbol_info.min_notional

    def get_tick_size(self) -> float:
        """Get tick size for current symbol"""
        if self._symbol_info is None:
            logger.warning("[TICK SIZE] Symbol info not loaded, using default 0.01")
            return 0.01
        return self._symbol_info.tick_size
    
    def get_step_size(self) -> float:
        """Get step size for current symbol"""
        if self._symbol_info is None:
            logger.warning("[STEP SIZE] Symbol info not loaded, using default 0.001")
            return 0.001
        return self._symbol_info.step_size
    
    async def get_position_risk(self, symbol: str = None, monitor_priority: bool = False) -> List[Dict]:
        """
        Get position risk data from Binance Futures.
        This is the CORRECT endpoint for getting position information.

        Args: 
            symbol: Filter by symbol
            monitor_priority: If True, uses the lower-priority monitor semaphore
                so background callers cannot starve the trading-path slots.
                Set True from SL/TP monitor, health check, and orphan cleanup.
        
        Returns list of position data for all symbols or specific symbol.
        
        Cause D fix: exceptions are now re-raised instead of silently returning [].
        Previously [] was indistinguishable from "no position found" to every
        caller, causing fatally wrong decisions.
            - has_open_position() -> False -> allows new entry into existing position
            - _verify_position_exists() -> False -> triggers fake position closure
            - _emergency_exit() -> skips market order placement
        
        Every caller already has its own except block with the correct fail-safe:
            - has_open_position()       except -> return True (safe: block entry)
            - _verify_position_exists() except -> return False (logs, no state reset)
            - _emergency_exit()         except -> logs, state preserved
        
            Letting the exception propaget restores those protections.
        """
        symbol = symbol or self.default_symbol
        endpoint = self._get_endpoint("positions")  # /fapi/v2/positionRisk
        
        _request_fn = self._monitor_signed_request if monitor_priority else self._signed_request

        result = await _request_fn("GET", endpoint, {"symbol": symbol})
            
        # Filter to just our symbol if multiple returned
        if isinstance(result, list):
            result = [p for p in result if p.get("symbol") == symbol]
            
        return result if isinstance(result, list) else [result]
            
    
    async def query_algo_order(self, symbol: str, algo_id: str) -> Optional[Dict[str, Any]]:
        """
        Query the status of an algo order by algo ID.

        Binance has no single-order GET by algoId. We check open orders first,
        then fall back to allAlgoOrders (covers filled/cancelled/historical).
        
        NOTE: Algo order endpoints may not be available on Binance testnet.
        Returns None if order not found or endpoints unavailable.

        Endpoint for historical: GET /fapi/v1/allAlgoOrders
        Documentation: https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Query-All-Algo-Orders
        
        Args:
            symbol: Trading symbol (e.g., "SOLUSDT")
            algo_id: The algo order ID to query
            
        Returns:
            Order dict if found, None if not found or endpoints unavailable
        """
        str_algo_id = str(algo_id)

        # 1. Check open algo orders first (fastest path for active orders)
        try:
            open_orders = await self.get_open_algo_orders(symbol)
            for order in open_orders:
                if str(order.get("algoId")) == str_algo_id:
                    return order
        except Exception as e:
            logger.warning("[QUERY_ALGO] Could not fetch open algo orders: %s", e)

        # 2. Fall back to historical orders (covers filled/cancelled/expired)
        # NOTE: /fapi/v1/allAlgoOrders does NOT support filtering by algoId as a
        # query parameter. Passing it produces a malformed URL that CloudFront
        # rejects with a 403. Fetch by symbol only and filter client-side.
        try:
            endpoint = "/fapi/v1/allAlgoOrders"
            params = {
                "symbol": symbol.upper(),
            }
            response = await self._signed_request("GET", endpoint, params)
            
            # Response is an array of algo orders
            orders = response if isinstance(response, list) else []
            
            for order in orders:
                if str(order.get("algoId")) == str_algo_id:
                    return order
                    
        except RuntimeError as e:
            error_msg = str(e)
            if "404" in error_msg and ("-5000" in error_msg or "Path" in error_msg or "invalid" in error_msg.lower()):
                env = "testnet" if "testnet" in self.base_url.lower() else "production"
                logger.warning(
                    "%s[QUERY_ALGO] Historical algo orders endpoint not available on %s. "
                    "This is expected on testnet.",
                    Fore.YELLOW, env,
                )
            else:
                logger.warning("[QUERY_ALGO] Could not fetch historical algo orders: %s", e)
        except Exception as e:
            logger.warning("[QUERY_ALGO] Could not fetch historical algo orders: %s", e)

        return None
        
    async def get_account_info(self) -> Dict:
        """
        Get account information including balance and leverage.
        """
        endpoint = self._get_endpoint("account")  # /fapi/v2/account
        
        try:
            result = await self._signed_request("GET", endpoint, {})
            return result
        except Exception as e:
            logger.error("%s[GET ACCOUNT INFO] Failed: %s", Fore.RED, e)
            return {}

    async def get_listen_key(self) -> str:
        """Create a user data stream listen key for Futures."""
        # Cause B/C/E/G fix: same shared ban check - this method bypasses
        # _signed_request/_request entirely via a raw session.post() call.
        _now = time.monotonic()
        if _now < self._ip_banned_until:
            raise RuntimeError(
                 "Binance IP ban (HTTP 418) active — %.0fs remaining." % (self._ip_banned_until - _now)
            )
        
        # Cause K fix: this previously used raw session.post() bypassing 
        # the throttle check entirely.
        if self.throttle and self.throttle.is_throttled():
            raise RuntimeError("Request throttled: would exceed limit")
        
        url = f"{self.base_url}/fapi/v1/listenKey"
        session = await self._get_session()
        async with session.post(url, headers={"X-MBX-APIKEY": self.api_key}) as resp:
            data = await resp.json()
            if self.throttle:
                 self.throttle.record_order(volume=0.0, weight=self._endpoint_weight.get("/fapi/v1/listenKey", 1))
            return data["listenKey"]

    async def keepalive_listen_key(self, listen_key: str) -> None:
        """Extend listen key validity (must call every 30-60 minutes)."""
        # Cause B/C/E/G fix: same shared ban check as get_listen_key above.
        _now = time.monotonic()
        if _now < self._ip_banned_until:
            raise RuntimeError(
                  "Binance IP ban (HTTP 418) active — %.0fs remaining." % (self._ip_banned_until - _now)
            )
        # Cause K fix: same throttle wiring as get_listen_key above.
        if self.throttle and self.throttle.is_throttled():
             raise RuntimeError("Request throttled: would exceed limit")
        url = f"{self.base_url}/fapi/v1/listenKey"
        session = await self._get_session()
        async with session.put(url, headers={"X-MBX-APIKEY": self.api_key}, 
                                    params={"listenKey": listen_key}) as resp:
            await resp.read()
            if self.throttle:
                  self.throttle.record_order(volume=0.0, weight=self._endpoint_weight.get("/fapi/v1/listenKey", 1))

    async def debug_dump_exchange_state(self, symbol: str = "SOLUSDT"):
        """
        Dumps everything relevant:
        - ONLY real open futures positions (filtered)
        - All open orders
        - Order history (recent)
        - Account balances
        """
        print("\n" + "="*80)
        print("🔍 EXCHANGE STATE DUMP")
        print("="*80)

        # ===== REAL OPEN POSITIONS =====
        try:
            positions = await self.get_open_positions(symbol)

            # FILTER ONLY REAL POSITIONS
            real_positions = [
                p for p in positions
                if float(p.get("positionAmt", 0)) != 0.0
            ]

            print(f"\n📌 REAL OPEN POSITIONS ({len(real_positions)}):")

            if not real_positions:
                print("👉 No active positions for", symbol)
            else:
                for p in real_positions:
                    print(json.dumps(p, indent=2))

        except Exception as e:
            logger.error(f"[ERROR] Could not load positions: {e}")

        # ===== OPEN ORDERS =====
        try:
            open_orders = await self.get_open_orders(symbol)
            logger.info(f"\n📌 OPEN ORDERS ({len(open_orders)}):")
            for o in open_orders:
                logger.info(json.dumps(o, indent=2))
        except Exception as e:
            logger.error(f"[ERROR] Could not load open orders: {e}")

        # ===== ORDER HISTORY =====
        try:
            history = await self._signed_request(
                "GET", "/fapi/v1/allOrders", {"symbol": symbol}
            )
            print(f"\n📌 ORDER HISTORY ({len(history)} TOTAL, showing last 20):")
            for h in history[-20:]:
                print(json.dumps(h, indent=2))
        except Exception as e:
            print(f"[ERROR] Could not load order history: {e}")

        # ===== ACCOUNT BALANCE =====
        try:
            acc = await self._signed_request("GET", "/fapi/v2/account", {})
            print("\n📌 ACCOUNT INFO:")
            print(json.dumps(acc, indent=2))
        except Exception as e:
            print(f"[ERROR] Could not load account info: {e}")

        print("\n" + "="*80 + "\n")