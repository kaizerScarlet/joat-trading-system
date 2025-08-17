import asyncio
import random
from typing import Optional
import logging
from market_data.orderbook import OrderBook
from Execution_layer.execution_coordinator import SlippageModel

logger = logging.getLogger(__name__)

class StealthRouter:
    """
    Breaks a parent order into multiple smaller child orders with randomized size, timing ,
    and price adjustments to reduce market footprint.
    """

    def __init__(self, exchange_client, symbol: str,
                 min_slice_usd: float = 50,
                 max_slice_usd: float = 500,
                 random_delay_range: tuple = (0.3, 1.5),
                 tick_size: float = 0.01,
                 qty_precison: int = 6,
                 max_slices: int = 20,
                 slippage_bps: float = 5.0 #max slippage per slice (optional)
                 
                 ):
        """
        :param exchange_client: Adapter with place_order() and get_midprice() methods.
        :param symbol: Trading pair (e.g, "BTCUSDT").
        :param min_slice_usd: Minimium USD value of a slice.
        :param max_slice_usd: Maximum USD value of a slice.
        :param random_delay_range: min and max seconds between slices.
        :param tick_size: Price tick size for rounding.
        :param qty_precison: precision for quantity rounding
        :param max_slices: maximum number of slices per parent order.
        :param slippage_bps: max allowed slippage in basis points per slice
        """

        self.exchange_client = exchange_client
        self.symbol = symbol
        self.min_slice_usd = min_slice_usd
        self.max_slice_usd = max_slice_usd
        self.random_delay_range = random_delay_range
        self.tick_size = tick_size
        self.qty_precision = qty_precison
        self.max_slices = max_slices
        self.slippage_bps = slippage_bps / 10000.0 #convert bps to fraction


    async def execute_parent_order(self, side:str, total_qty: float,
                                   order_type: str, limit_price: Optional[float]=None,
                                   fee_schedule = None, #New: FeeSchedule (Optional)
                                   slippage_model = SlippageModel, #New: SlippageModel (Optional)
                                   orderbook = OrderBook, #New: OrderBook (Optional)
                                   ):
        """
        Executes a parent order in multiple stealthy slices.
        """
        order_type = order_type.upper()
        if order_type not in ("LIMIT","MARKET"):
            raise ValueError(f"Unsupported order_type: {order_type}")

        remaining_qty = total_qty
        placed_order_ids = []
        slice_count = 0

        #helpers from orderbook if available
        def _best(side_):
            if hasattr(orderbook, "get_best_price"):
                if side_.upper() == "BUY":
                    return orderbook.get_best_price("ask")
                else:
                    return orderbook.get_best_price("bid")
            return None 
        
        def _mid():
            if hasattr(orderbook, "get_best_price"):
                b = orderbook.get_best_price("bid")
                a = orderbook.get_best_price('ask')
                return (a + b) * 0.5 if a and b else None
            return None
        
        def _top_liq(side_):
            if hasattr(orderbook, "get_top_liquidity"):
                return orderbook.get_top_liquidity(side_)
            return 0.0

        while remaining_qty > 0 and slice_count < self.max_slices:
            slice_qty = self._choose_slice_size(remaining_qty)

            #Base price from caller / mid
            slice_price = self._choose_slice_price(side, limit_price, order_type)

            m = _mid()
            if order_type == "LIMIT" and slippage_model and m:
                #Pull slightly toward mid to reduce crossing; final snap is done in _choose_slice_price
                slice_price = slippage_model.expected_limit_price(side, slice_price, m, micro_revert_bps=0.5)
            
            #if MARKET, price stays None (Adapter will send a market)
            #If LIMIT and price ends up crossing current opposite best, we'll be taker.
            opp_best = _best(side)
            liquidity = "MAKER"
            if order_type == "MARKET":
                liquidity = "TAKER"
            elif opp_best is not None:
                if (side.upper() == "BUY" and slice_price >= opp_best) or (side.upper() == "SELL" and slice_price <= opp_best):
                    liquidity = "TAKER"

            #Optional: if MARKET, annotate expected slippage for visibility (no price update here)
            if order_type == "MARKET" and slippage_model and m is not None and opp_best is not None:
                spread = abs(_best("BUY") - _best("SELL")) if _best("BUY") and _best("SELL") else abs(opp_best - m) * 2
                exp_slip = slippage_model.expected_market_slip(side, m, spread, qty=slice_qty, top_liquidity= max(1.0, _top_liq(side)))
                #You can log exp_slip or attach to metadata if you want to collect expected vs realized



            # ---- Place slice (retry aware) ------
            for attempt in range(3):
                try:
                    resp =   await self.exchange_client.place_order(
                    symbol = self.symbol,
                    side = side,
                    size = slice_qty,
                    type = order_type,
                    price = slice_price,
                    quantity = round(slice_qty, self.qty_precision)
                )

                    if resp and "orderId" in resp:
                        rec = {
                            "orderId": resp["orderId"],
                            "qty": slice_qty,
                            "price": slice_price,
                            "liquidity": liquidity, # <------ tag for fee attribution upstream
                        }
                        placed_order_ids.append(rec)
                        logger.debug(f"Placed slice {slice_count + 1} / {self.max_slices}: "
                                     f"{slice_qty} {side} @ {slice_price} (Remaining: {remaining_qty - slice_qty})")
                        break
                except Exception as e:
                    logger.warning(f"Retry {attempt + 1} failed placing slice: {e}")
                    await asyncio.sleep(1.0 + attempt)

            #Decrement remaining qty and advance-
            remaining_qty = max(0, remaining_qty - slice_qty)
            slice_count += 1

            if remaining_qty > 0:
                await self._random_delay()

        if slice_count >= self.max_slices:
            logger.warning(f"Reached max slices limit ({self.max_slices}) before completing parent order") 
        
        return placed_order_ids


    def _choose_slice_size(self, remaining_qty: float) -> float:
        """Random slice size in base asset units."""
        mid_price = getattr(self.exchange_client, "get_midprice", lambda *_: None)(self.symbol)

        if not mid_price:
            mid_price = 1.0 #fallback

        
        slice_usd = random.uniform(self.min_slice_usd, self.max_slice_usd)
        slice_qty = min(remaining_qty, slice_usd / mid_price)
        return round(slice_qty, self.qty_precision) #Binance lot size precision
    


    def _choose_slice_price(self, side: str, limit_price: Optional[float], order_type: str):
        """Random price adjustment for limit orders using tick_size"""
        if order_type.upper() == "MARKET":
            return None 
        

        mid_price = getattr(self.exchange_client, "get_midprice", lambda *_: None)(self.symbol)
        if not mid_price:
            mid_price = limit_price or 1.0 #Fallback

        base_price = limit_price or mid_price

        #Optional jitter range in ticks (e.g. [-2, 2])
        tick_jitter = random.randint(-2, 2)
        jitter = self.tick_size * tick_jitter

        #Optional slippage control
        max_slip = mid_price * self.slippage_bps
        jitter = max(min(jitter, max_slip), -max_slip)

        #Apply jitter with directionality logic
        if side.upper() == "BUY":
            adjusted_price = base_price + jitter # Slightly aggressive or passive
        else:
            adjusted_price = base_price - jitter

        #Snap to tick size
        adjusted_price = round(adjusted_price / self.tick_size) * self.tick_size
        return adjusted_price

    async def _random_delay(self):
        """
        Random pause between slices.
        """
        delay = random.uniform(*self.random_delay_range)
        logger.debug(f"Sleeping for {delay:.2f}s before next slice")
        await asyncio.sleep(delay)
        