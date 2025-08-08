# execution/mock_adapter.py
import asyncio
import time
import uuid
from typing import Optional, Callable, Dict, Any, List


class MockExchangeAdapter:
    """
    Local simulated exchange adapter — good for unit testing / backtesting.
    - instant fills (configurable)
    - records orders, cancels, and calls on_fill_callback just like real adapter would
    """

    def __init__(self, instant_fill: bool = True, latency_ms: int = 10, throttle_manager: Optional[Any] = None):
        self.instant_fill = instant_fill
        self.latency_ms = latency_ms
        self.on_fill_callback: Optional[Callable[[Dict[str, Any]], None]] = None
        self.throttle = throttle_manager
        self.orders: Dict[str, Dict] = {}
        self._lock = asyncio.Lock()

    async def place_order(self, symbol: str, side: str, type: str, quantity: float, price: Optional[float] = None, **kwargs):
        """
        Simulate placing an order. Returns a mock order report.
        """
        async with self._lock:
            client_id = kwargs.get("new_client_order_id") or f"mc_{uuid.uuid4().hex[:8]}"
            now = int(time.time() * 1000)
            order = {
                "symbol": symbol,
                "side": side,
                "type": type,
                "quantity": quantity,
                "price": price,
                "client_id": client_id,
                "status": "NEW",
                "order_id": uuid.uuid4().int & (1 << 32) - 1,
                "timestamp": now,
            }
            self.orders[client_id] = order
            if self.throttle:
                self.throttle.record_order(volume=quantity, weight=1)
            if self.instant_fill:
                # simulate a short latency then report fill
                await asyncio.sleep(self.latency_ms / 1000.0)
                fill = {
                    "timestamp": int(time.time() * 1000),
                    "symbol": symbol,
                    "side": side,
                    "order_id": order["order_id"],
                    "qty": quantity,
                    "price": price or 0.0,
                    "status": "FILLED",
                    "raw": order,
                }
                # record trade volume in throttle manager
                if self.throttle:
                    self.throttle.record_trade(volume=quantity)
                if self.on_fill_callback:
                    res = self.on_fill_callback(fill)
                    if asyncio.iscoroutine(res):
                        await res
                order["status"] = "FILLED"
            return order

    async def cancel_order(self, symbol: str, order_id: Optional[int] = None, client_id: Optional[str] = None):
        async with self._lock:
            # find order
            found = None
            if client_id and client_id in self.orders:
                found = self.orders[client_id]
            elif order_id:
                for o in self.orders.values():
                    if o["order_id"] == order_id:
                        found = o
                        break
            if found:
                found["status"] = "CANCELED"
                if self.throttle:
                    self.throttle.record_cancel()
                return {"status": "CANCELED", "order": found}
            return {"status": "NOT_FOUND"}

    async def get_order_status(self, symbol: str, order_id: Optional[int] = None, client_id: Optional[str] = None):
        if client_id and client_id in self.orders:
            return self.orders[client_id]
        elif order_id:
            for o in self.orders.values():
                if o["order_id"] == order_id:
                    return o
        return None

    async def close(self):
        return
