#connects to binance's websocket
"""
Minimal, read-only Binance market data feed.
Subscribes to:
    *Depth 100ms stream (symbol@depth@100ms)
    *Trade stream   (symbol@trade)

publishes normalized 'Event' objects into utils.bus.Bus.

Usage at the bottom('python -m market_data.binance_ws_client')
prints the first 10 events then exits - ideal for smoke-testing
"""
from __future__ import annotations
import asyncio 
import json
import websockets
from utils.bus import BUS
from utils.event_types import Event, Channel

BINANCE_WS_URL = "wss://stream.binance.com:9443/stream"

class BinanceWSFeed:
    def __init__(self, symbol: str = "btcusdt"):
        self.symbol = symbol.lower()
        self._ws: websockets.WebSocketClientProtocol | None = None
        self._task: asyncio.Task | None = None

    async def connect(self) -> None:
        streams = f"{self.symbol}@depth@1000ms/{self.symbol}@trade"
        uri = f"{BINANCE_WS_URL}?streams={streams}"
        self._ws = await websockets.connect(uri, ping_interval=15, ping_timeout=10)
        self._task = asyncio.create_task(self._listen())

    async def disconnect(self) -> None:
        if self._ws:
            await self._ws.close()

    #------------------------------------------------------------------------------------

    async def _listen(self) -> None:
        assert self._ws is not None, "WebSockect not connected"
        async for raw in self._ws:
            msg = json.loads(raw)
            stream = msg["stream"]
            data = msg["data"]

            #depth updates
            if stream.endswith("depth@100ms"):
                ts = data["E"]      #event time
                event = Event(
                    ts = ts,
                    symbol = self.symbol.upper(),
                    channel = Channel.BOOK,
                    payload = data,
                )
                await BUS.put(event)

            #trades
            elif stream.endswith("trade"):
                ts = data["T"]  #trade time
                event = Event(
                    ts = ts,
                    symbol = self.symbol.upper(),
                    channel = Channel.TRADE,
                    payload = data,
                )
                await BUS.put(event)
    # ----------------------------------------------------------------------------------------------------------
    # Convenience helper for stand-alone smoke tests
    async def _demo(self, limit: int = 10) -> None:
        count = 0
        while count < limit:
            evt = await BUS.get()
            print(evt)
            count += 1
#------------------------------------------------------------------------------------------------------------------
if __name__ == "__main__":
    """
   'python -m market_data.binance_ws_client'
   prints 10 events and exits - verifying connectivity.
    """
    async def _run():
        feed = BinanceWSFeed("btcusdt")
        await feed.connect()
        await feed._demo(limit=10)
        await feed.disconnect()
    asyncio.run(_run())