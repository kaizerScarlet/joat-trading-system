from typing import Protocol, Optional, Dict, Any, runtime_checkable
import asyncio
import time
import hmac
import hashlib
import urllib.parse
from urllib.parse import urlencode
from typing import Optional, Callable, Dict, Any
import aiohttp
from dynamic_risk_engine.throttle_cooldown_manager_protocol import ThrottleCooldownManagerProtocol


@runtime_checkable
class BinanceExecutionAdapterProtocol(Protocol):
    api_key: str
    api_secret: str
    base_url: str
    session: Optional[aiohttp.ClientSession]
    _closed: bool
    _lock: asyncio

    throttle: ThrottleCooldownManagerProtocol
    on_fill_callback: Optional[Callable[[Dict[str, Any]], None]]

    recv_window: int
    default_symbol: str

    _endpoint_weight: Dict[str, int]

    fee_schedule: Dict[str, float]


    async def place_order(
        self,
        symbol: Optional[str],
        side: str,
        type: str,
        quantity: Optional[float],
        price: Optional[float],
        time_in_force: str,
        new_client_order_id: Optional[str],
        **extra
    ) -> Dict[str, Any]:
        """Places a market or limit order and returns exchange response."""
        ...

    async def place_stop_loss_order(self, symbol: str, side: str, stop_price: float, quantity: float) -> Dict:
        """Places a stop-limit order acting as a stop loss."""
        ...

    async def place_take_profit_order(self, symbol: str, side: str, take_profit_price: float, quantity: float) -> Dict:
        """Places a limit order acting as a take profit."""
        ...

    async def modify_order(
        self,
        symbol: str,
        orig_order_id: Optional[int],
        orig_client_order_id: Optional[str],
        new_price: Optional[float],
        new_qty: Optional[float],
        new_client_order_id: Optional[str],
        max_wait_ms: int
    ) -> Dict[str, Any]:
        """Attempts to modify an order by cancelling and replacing it."""
        ...

    async def cancel_order_by_id(self, symbol: str, order_id: int) -> Dict:
        """Cancels an order by its order ID."""
        ...

    async def cancel_order(
        self,
        symbol: Optional[str],
        orderId: Optional[int],
        origClientOrderId: Optional[str]
    ) -> Dict:
        """Cancels an order using order ID or client order ID."""
        ...

    async def get_order_status(
        self,
        symbol: Optional[str],
        orderId: Optional[int],
        origClientOrderId: Optional[str]
    ) -> Dict:
        """Returns the status of an order."""
        ...

    async def get_account(self) -> Dict:
        """Returns full account information."""
        ...

    async def get_account_balance(self) -> float:
        """Returns free balance for USDT (or configured asset)."""
        ...

    async def sync_server_time(self) -> int:
        """Synchronizes local time offset with Binance server time."""
        ...

    def get_fee_schedule(self) -> Dict[str, float]:
        """Returns the current fee schedule (maker/taker bps)."""
        ...

    async def handle_user_event(self, event: Dict[str, Any]) -> None:
        """Processes user-data WS events and triggers fill callbacks."""
        ...

    async def close(self) -> None:
        """Closes internal aiohttp session."""
        ...
