import asyncio
import random
from typing import Optional

class StealthRouter:
    """
    Breaks a parent order into multiple smaller child orders with randomized size, timing ,
    and price adjustments to reduce market footprint.
    """

    def __init__(self, exchange_client, symbol: str,
                 min_slice_usd: float = 50,
                 max_slice_usd: float = 500,
                 random_delay_range: tuple = (0.3, 1.5),
                 tick_size: float = 0.01
                 
                 ):
        """
        :param exchange_client: Adapter with place_order() and get_midprice() methods.
        :param symbol: Trading pair (e.g, "BTCUSDT").
        :param min_slice_usd: Minimium USD value of a slice.
        :param max_slice_usd: Maximum USD value of a slice.
        :param random_delay_range: min and max seconds between slices.
        :param tick_size: Price tick size for rounding.
        """

        self.exchange_client = exchange_client
        self.symbol = symbol
        self.min_slice_usd = min_slice_usd
        self.max_slice_usd = max_slice_usd
        self.random_delay_range = random_delay_range
        self.tick_size = tick_size


    async def execute_parent_order(self, side:str, total_qty: float,
                                   order_type: str, limit_price: Optional[float]=None):
        """
        Executes a parent order in slices.
        """
        remaining_qty = total_qty
        placed_order_ids = []

        while remaining_qty > 0:
            slice_qty = self._choose_slice_size(remaining_qty)
            slice_price = self._choose_slice_price(side, limit_price, order_type)


            resp =   await self.exchange_client.place_order(
                symbol = self.symbol,
                side = side,
                size = slice_qty,
                type = order_type,
                price = slice_price,
                quantity = slice_qty
            )

            if resp and "orderId" in resp:
                placed_order_ids.append(resp["orderId"])

            remaining_qty = max(0, remaining_qty - slice_qty)

            if remaining_qty > 0:
                await self._random_delay()
        
        return placed_order_ids


    def _choose_slice_size(self, remaining_qty: float) -> float:
        """Random slice size in base asset units."""
        mid_price = getattr(self.exchange_client, "get_midprice", lambda *_: None)(self.symbol)

        if not mid_price:
            mid_price = 1.0 #fallback

        
        slice_usd = random.uniform(self.min_slice_usd, self.max_slice_usd)
        slice_qty = min(remaining_qty, slice_usd / mid_price)
        return round(slice_qty, 6) #Binance lot size precision
    


    def _choose_slice_price(self, side: str, limit_price: Optional[float], order_type: str):
        """Random price adjustment for limit orders"""
        if order_type.upper() == "MARKET":
            return None 
        jitter = self.tick_size * random.randint(-2, 2)
        if side.upper() == "BUY":
            return round(limit_price + jitter, 2)
        else:
            return round(limit_price - jitter, 2)


    async def _random_delay(self):
        """
        Random pause between slices.
        """
        delay = random.uniform(*self.random_delay_range)
        await asyncio.sleep(delay)
        