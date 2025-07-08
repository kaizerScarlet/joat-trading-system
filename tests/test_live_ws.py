import pytest, asyncio
from market_data.binance_ws_client import BinanceWSFeed
from utils.bus import BUS

@pytest.mark.live
@pytest.mark.asyncio
async def test_ws_recieves_one_msg():
    feed = BinanceWSFeed("btcusdt")
    await feed.connect()
    evt = await asyncio.wait_for(BUS.get(), timeout=10)
    assert evt.channel in ("book", "trade")
    await feed.disconnect()