#execution/ binance_adapter.py

import asyncio
import time
import hmac
import hashlib
from urllib.parse import urlencode
from typing import Optional, Callable, Dict, Any
import aiohttp
from dynamic_risk_engine.throttle_cooldown_manager import ThrottleCooldownManager

DEFAULT_RECV_WINDOW = 5000 #ms

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
            api_key: str,
            api_secret: str,
            base_url: str = "https://api.binance.com",
            session: Optional[aiohttp.ClientSession] = None,
            default_recv_window: int = DEFAULT_RECV_WINDOW,
            default_symbol: Optional[str] = None,
    ):
        self.api_key = api_key
        self.api_secret = api_secret("utf-8")
        self.base_url = base_url.rstrip("/")
        self.session = session or aiohttp.ClientSession()
        self._closed = False
        self._lock =asyncio.Lock() #serialize signed request creation if needed


        #Optional integration objects
        self.throttle = ThrottleCooldownManager()
        self.on_fill_callback = Optional[Callable[[Dict[str, Any]], None]] = None

        self.recv_window = default_recv_window
        self.default_symbol = default_symbol


        # Approximate weight cost mapping (for our throttle manager)
        self._endpoint_weight = {
            "/api/v3/order": 1,  #Place order
            "/api/v3/order (cancel)": 1,    #cancel
            "/api/v3/order (query)": 1, #status
            "/sapi/v1/accountSnapshot": 5,


        }

    # ------------------ Low-Level helpers --------------------------
    def _sign(self, data: str) -> str:
        sig = hmac.new(self.api_secret, data.encode("utf-8"), hashlib.sha256).hexdigest()
        return sig 
    
    def _now_ms(self) -> int:
        return int(time.time() * 1000)
    
    
    async def _signed_request(self, method: str, path: str, params: Optional[Dict] =  None) -> Dict:
        """
        Make a signed request to Binance. Uses recvWindow and timestamp automatically.
        Method should be 'GET', 'POST', 'DELETE' etc.
        """
        params = params.copy() if params else {}
        params["timeestamp"] = self._now_ms()
        params["recvWindow"] = self.recv_window

        query = urllib.parse.urlencode(params, doseq=True)
        signature = self._sign(query)
        query = f"{query}&signature={signature}"
        url = f"{self.base_url}{path}?{query}"

        #throttle weight accounting
        weight = self._endpoint_weight.get(path, 1)
        if self.throttle:
            #If throttle manager disallows, raise or wait - here we check and raise
            if self.throttle.is_throttled():
                raise RuntimeError("Throttle manager prevents REST request (would exceed limit).")
            self.throttle.record_order(volume=0.0, weight=weight)

        
        headers = {"X-MBX-APIKEY": self.api_key}
        async with self._lock: #Ensure query string created atomically (not strictly required)
            async with self.session.request(method, url, headers=headers) as resp:
                text = await resp.text()
                if resp.status >= 400:
                    raise RuntimeError(f"Binance API Error {resp.status}: {text}")
                return await resp.json()
            


    # -----------------------Public API -------------------------------
    async def place_order(
            self,
            symbol: Optional[str] = None,
            side: str = "BUY",
            size: float = None,
            type: str = "MARKET",
            quantity: Optional[float] = None,
            price: Optional[float] = None,
            time_in_force: str = "GTC",
            stoploss: Optional[float] = None,
            takeprofit: Optional[float] = None,
            new_client_order_id: Optional[str] = None,
            **extra
    ) -> Dict[str, Any]:
        """
        Place an order (async). Returns the exchange response (dict).
        -side: 'BUY' or 'SELL'
        - type: 'MARKET' or 'LIMIT'

        Note: ensure quantity/price rounding to exchange tick/lot rules upstream
        """
        assert type in ("MARKET", "LIMIT"), "Only MARKET and LIMIT implemented here"

        payload = {
            "symbol": (symbol or self.default_symbol).upper(),
            "side": side,
            "type": type,
            "size": size,
            "price": price,
            "sl": stoploss,
            "tp": takeprofit,
        }

        if new_client_order_id:
            payload["newClientOrderId"] = new_client_order_id

        if type == "MARKET":
            payload["quantity"] = quantity

        else: #LIMIT
            payload["timeInForce"] = time_in_force
            payload["price"] = price
            payload["quantity"] = quantity


        #Use signed REST endpoint
        resp = await self._signed_request("POST", "/api/v3/order", payload)
        #Record trade/order activity in throttle manager if adapter received immediate maker fill later via WS
        return resp 
    

    async def cancel_order(self, symbol: Optional[str] = None, orderId: Optional[int] = None, origClientOrderId: Optional[str] = None) -> Dict:
        """
        Cancel an order. Provide orderID or origClientOrderId
        """
        payload = {"symbol": (symbol or self.default_symbol).upper()}
        if orderId:
            payload["orderId"] = orderId
        if origClientOrderId:
            payload["origClientOrderId"] = origClientOrderId

        resp = await self._signed_request("DELETE", "/api/v3/order", payload)

        #We count cancels in throttle Manager
        if self.throttle:
            self.throttle.record_cancel()
        return resp
    

    async def get_order_status(self, symbol: Optional[str] = None, orderId: Optional[int] = None, origClientOrderId: Optional[str] = None) -> Dict:
        payload = {"symbol": (symbol or self.default_symbol).upper()}
        if orderId:
            payload["orderId"] = orderId
        if origClientOrderId:
            payload["origClientOrderId"] = origClientOrderId
        resp = await self._signed_request("GET", "/api/v3/order", payload)
        return resp
    
    async def get_account(self) -> Dict:
        """Get account info (example usage)."""
        resp = await self._signed_request("GET", "/api/v3/account",{})
        return resp
    

    async def close(self):
        """Close internal session"""
        if not self._closed:
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
            "s": "BTCUSDT",
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
            if e_type in ("executionReport", "ORDER_TRADE_UPDATE"):
                exec_type = event.get("o",{}).get("x") or event.get("x")
                order_status = event.get("o", {}).get("X") or event.get("X")
                # last executed qty
                last_qty = float(event.get("o",{}).get("l") or event.get("l") or 0.0)
                last_price = float(event.get("o", {}).get("L") or event.get("L") or 0.0)

                if last_qty > 0:
                    fill = {
                        "timestamp": event.get("E", self._now_ms()),
                        "symbol": event.get("s"),
                        "side": event.get("S"),
                        "order_id": event.get("i") or event.get("i"),
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
                        res = self.on_fill_callback(fill)
                        if asyncio.iscoroutine(res):
                            await res

        except Exception as ex:
            #Keep adapter robust - Log or rethrow in your production logger
            print("[BinanceAdapter] handle_user_event_error:", ex)