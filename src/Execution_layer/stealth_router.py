import asyncio
import random
from typing import Optional
import logging
from market_data.orderbook import OrderBook
from Execution_layer.fee_schedule import FeeSchedule
from Execution_layer.slippage_model import SlippageModel
from Execution_layer.queue_position_model import QueuePositionModel 
from Execution_layer.binance_adapter import BinanceExecutionAdapter
from Execution_layer.smart_pricing_model import SmartRepricingModel
from dynamic_risk_engine.cognitive_market_regime_classifier import CognitiveMarketRegimeClassifier, MarketRegime

logger = logging.getLogger(__name__)

class StealthRouter:
    """
    Breaks a parent order into multiple smaller child orders with randomized size, timing ,
    and price adjustments to reduce market footprint.
    Now Supports hybrid mode: start passive, monitor queue, reprice or cross if fill prob drops
    """

    def __init__(self, exchange_client = None, symbol: str = "BTCUSDT",
                 min_slice_usd: float = 50,
                 max_slice_usd: float = 500,
                 random_delay_range: tuple = (0.3, 1.5),
                 tick_size: float = 0.01,
                 qty_precison: int = 6,
                 max_slices: int = 20,
                 slippage_bps: float = 5.0, #max slippage per slice (optional)
                 queue_model = None,#New: queue model injected for hybrid monitoring
                 repricing_model = None, #New: repricing model (optional
                 regime_classifier = None,
                 slippage_model = None
                 
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
        :param queue_model: model with .estimate() for fill probability (Optional)
        """

        self.exchange_client = exchange_client or BinanceExecutionAdapter()
        self.symbol = symbol
        self.min_slice_usd = min_slice_usd
        self.max_slice_usd = max_slice_usd
        self.random_delay_range = random_delay_range
        self.tick_size = tick_size
        self.qty_precision = qty_precison
        self.max_slices = max_slices
        self.slippage_bps = slippage_bps / 10000.0 #convert bps to fraction
        self.queue_model = queue_model or QueuePositionModel()
        self.regime_classifier = regime_classifier or CognitiveMarketRegimeClassifier()
        self.execution_log = [] #Post Trade analysis log
        self.repricing_model = repricing_model or SmartRepricingModel(tick_size=self.tick_size, slippage_bps=slippage_bps)
        self.slippage_model = slippage_model or SlippageModel()
    
    def now_ms(self):
        import time
        return int(time.time() * 1000)


    async def execute_parent_order(self, side:str, total_qty: float,
                                   order_type: str, limit_price: Optional[float]=None,
                                   fee_schedule = None, #New: FeeSchedule (Optional)
                                   slippage_model = SlippageModel(), #New: SlippageModel (Optional)
                                   orderbook = OrderBook, #New: OrderBook (Optional)
                                   mode: str = "normal",    #New: normal | hybrid
                                   hybrid_threshold: float = 0.3, # Fill prob cutoff
                                   hybrid_horizon: int = 5, # Seconds to evaluate fill prob
                                   fill_prob_threshold: float = 0.25, # New: Hybrid upgrade trigger
                                   ):
        """
        Executes a parent order in multiple stealthy slices.
        Supports noraml mode (fire & forget) and hybrid mode (monitor & adapt)
        Hybrid Mode:
            -If we start passive (LIMIT) but queue-fill probability deteriorates, 
            we can cancel/replace or cross aggressively mid-trade.
        """
        order_type = order_type.upper()
        if order_type not in ("LIMIT","MARKET"):
            raise ValueError(f"Unsupported order_type: {order_type}")

        remaining_qty = total_qty
        placed_order_ids = []
        slice_count = 0

        #Regime detection
        regime = self.regime_classifier.update_regime() if self.regime_classifier else MarketRegime.UNKNOWN
        logger.info(f"[StealthRouter] Detected market regime: {regime.value}")

        #Regime-based tuning
        if regime == MarketRegime.TRENDING:
            self.random_delay_range = (0.1, 0.4)
            self.slippage_bps = 10.0
            fill_prob_threshold = 0.4
        elif regime == MarketRegime.MEAN_REVERTING:
            self.random_delay_range = (1.0, 2.5)
            self.slippage_bps = 2.0
            fill_prob_threshold = 0.2
        elif regime == MarketRegime.VOLATILE:
            self.random_delay_range = (0.3, 1.0)
            self.slippage_bps = 15.0
            fill_prob_threshold = 0.5
        elif regime == MarketRegime.ILLIQUID:
            self.random_delay_range = (2.0, 4.0)
            self.slippage_bps = 5.0
            fill_prob_threshold = 0.3

        #Sync repricing model with updated regime slippage
        self.repricing_model.slippage_bps = self.slippage_bps

        # Regime-aware velocity thresholds
        if regime == MarketRegime.TRENDING:
            velocity_fast = 0.6
            velocity_slow = 0.2
        elif regime == MarketRegime.MEAN_REVERTING:
            velocity_fast = 0.4
            velocity_slow = 0.1
        elif regime == MarketRegime.VOLATILE:
            velocity_fast = 0.8
            velocity_slow = 0.3
        elif regime == MarketRegime.ILLIQUID:
            velocity_fast = 0.3
            velocity_slow = 0.05
        else:
            velocity_fast = 0.5
            velocity_slow = 0.1


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
            #Velocity-aware sizing
            slice_qty = self._choose_slice_size(remaining_qty)
            velocity = self.get_recent_fill_velocity()
            logger.debug(f"[Velocity Feedback] Recent fill velocity: {velocity:.4f} qty/s")

            #Adjust Slice Size based on regime-aware velocity
            if velocity > velocity_fast:
                slice_qty = min(slice_qty * 1.5, remaining_qty)
            elif velocity < velocity_slow:
                slice_qty = max(slice_qty * 0.5, self._choose_slice_size(remaining_qty) * 0.5)

            #OptionaL: adjust delay range based on fill speed
            if velocity > velocity_fast:
                self.random_delay_range = (0.1, 0.4)
            elif velocity < velocity_slow:
                self.random_delay_range = (1.5, 3.0)

            #Base price from caller / mid
            slice_price = self.repricing_model.optimize_price(
                side=side,
                orderbook=orderbook,
                fill_prob_target=fill_prob_threshold
            )

            m = _mid()
            if order_type == "LIMIT" and slippage_model and m:
                #Pull slightly toward mid to reduce crossing; final snap is done in _choose_slice_price
                slice_price = self.slippage_model.expected_limit_price(side, slice_price, m, micro_revert_bps=0.5)
            
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

            #Hybrid: Check queue fill probability before placing slice
            exp_fill_prob = 1.0
            top_liq = _top_liq(side)
            if mode == "hybrid" and order_type == "LIMIT" and top_liq > 0 and m:
                #Estimate queue probability
                _, fill_prob_per_s = self.queue_model.estimate(side, slice_qty, top_liq, orderbook)
                horizon_s = 5
                exp_fill_prob = 1 - (1 - fill_prob_per_s) ** horizon_s

                # ---- Hybrid upgrade -------
                slice_order_type = order_type #Preserve Original
                if exp_fill_prob < fill_prob_threshold:
                    logger.info(f"[Hybrid] fill probability {exp_fill_prob:.2f} < {fill_prob_threshold:.2f}, "
                                f"upgrading slice {slice_count + 1} to MARKET")
                    slice_order_type = "MARKET"
                    slice_price = None
                    liquidity = "TAKER"


            # ---- Place slice (retry aware) ------
            for attempt in range(3):
                try:
                    resp =   await self.exchange_client.place_order(
                    symbol = self.symbol,
                    side = side,
                    size = slice_qty,
                    type = slice_order_type,
                    price = slice_price,
                    quantity = round(slice_qty, self.qty_precision)
                )

                    if resp and "orderId" in resp:
                        fill_ts = self.now_ms() #Timestamp after placement
                        rec = {
                            "orderId": resp["orderId"],
                            "qty": slice_qty,
                            "price": slice_price,
                            "liquidity": liquidity, # <------ tag for fee attribution upstream
                            "exp_fill_prob": exp_fill_prob,  # New: Store expected fill probability
                            'regime': regime.value, # New: Store detected regime
                            'placement_ts': fill_ts,
                            'expected_slip': exp_slip if order_type == "MARKET" else 0.0,
                            'latency_ms': None,#Will be updated on fill
                            'realized_slip': None # Will be updated on fill
                        }
                        placed_order_ids.append(rec)
                        self.execution_log.append(rec) #Store slice metrics for post trade analysis
                        logger.debug(f"Placed slice {slice_count + 1} / {self.max_slices}: "
                                     f"{slice_qty} {side} @ {slice_price} "
                                     f"(liq={liquidity}, fillProb={exp_fill_prob:.2f}) "
                                      f" Remaining: {remaining_qty - slice_qty})")
                        
                        # --- Hybrid monitoring (only for LIMIT) -----
                        if mode == "hybrid" and order_type == "LIMIT" and self.queue_model:
                            asyncio.create_task(
                                self._monitor_slice(
                                    slice_info = rec,
                                    side = side,
                                    qty = slice_qty,
                                    orderbook = orderbook,
                                    horizon_sec = hybrid_horizon,
                                    threshold =  hybrid_threshold
                                )
                            )
                        break
                except Exception as e:
                    logger.warning(f"Retry {attempt + 1} failed placing slice: {e}")
                    await asyncio.sleep(1.0 + attempt)

            #Decrement remaining qty and advance-
            remaining_qty = max(0, remaining_qty - slice_qty)
            slice_count += 1

            if remaining_qty > 0:
                maybe_coro = self._random_delay()
                if asyncio.iscoroutine(maybe_coro):
                    await maybe_coro

        if slice_count >= self.max_slices:
            logger.warning(f"Reached max slices limit ({self.max_slices}) before completing parent order") 

        logger.info(f"[Execution Summary] {len(self.execution_log)} slices executed under {regime.value} regime")
        for rec in self.execution_log:
            logger.debug(f"Slice {rec['orderId']}: qty={rec['qty']} liq={rec['liquidity']} expSlip={rec['expected_slip']:.4f} "
                    f"realSlip={rec['realized_slip']} latency={rec['latency_ms']}ms")

        
        return placed_order_ids
    

    async def _monitor_slice(self, slice_info, side, qty, orderbook:OrderBook , horizon_sec: int, threshold: float):
        """
        Monitor a passive slice; cancel/replace or cross if fill prob drops below threshold.
        """
        order_id = slice_info["orderId"]

        while True:
            await asyncio.sleep(0.25) #check 4x/sec

            try:
                top_liq = orderbook.get_top_liquidity(side)
                qfrac, fill_prob_per_s = self.queue_model.estimate(
                    side = side,
                    our_qty = qty,
                    tob_qty = top_liq,
                    orderbook = orderbook
                )
                exp_fill_prob = 1 -(1 - min(fill_prob_per_s, 1.0)) ** horizon_sec

                if exp_fill_prob < threshold:
                    # ------ Cancel old slice ----
                    try:
                        await self.exchange_client.cancel_order_by_id(self.symbol, order_id)
                        logger.info(f"Hybrid: canceled slice {order_id}, exp_fill_prob={exp_fill_prob:.2f}")
                    except Exception as e:
                        logger.warning(f"Hybrid: Cancel failed for {order_id}: {e}")
                    
                    # ---- decide reprice vs cross ----
                    best_bid = orderbook.get_best_price("bid")
                    best_ask = orderbook.get_best_price("ask")
                    spread = abs(best_ask - best_bid) if best_bid and best_ask else 0.0
                    mid = (best_bid + best_ask) * 0.5 if best_bid and best_ask else None
                    tight = (spread / (mid or 1.0)) < 0.0002

                    if tight:
                        # cross immediately
                        await self.exchange_client.place_order(
                            symbol = self.symbol,
                            side = side,
                            type = "MARKET",
                            quantity = round(qty, self.qty_precision)
                        )
                        logger.info(f"Hybrid: flipped slice {order_id} to MARKET due low fill probability")
                    else:
                        # Reprice passive at current best
                        new_price = best_ask if side.upper() == "BUY" else best_bid
                        await self.exchange_client.place_order(
                            symbol = self.symbol,
                            side = side,
                            type = "LIMIT",
                            price = new_price,
                            quantity = round(qty, self.qty_precision),
                            timeInForce = "GTC"
                            )
                        logger.info(f"Hybrid: repriced slice {order_id} at {new_price}")
                    break
            except Exception as e:
                logger.exception(f"Hybrid monitor error for slice {order_id} : {e}")
                break    


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
        

    def record_fill(self, order_id: str, fill_price: float, fill_ts: float, fill_qty: Optional[float] = None):
        for rec in self.execution_log:
            if rec["orderId"] == order_id:
                rec["latency_ms"] = fill_ts - rec["placement_ts"]
                rec_price = rec.get("price", fill_price)
                rec["realized_slip"] = abs(fill_price - rec_price)
                qty_used =  fill_qty if fill_qty is not None else rec["qty"]
                rec["fill_velocity"] = qty_used / max((rec["latency_ms"] / 1000.0), 0.001)  # qty/sec
                logger.info(
                    f"[Execution Attribution] Order {order_id} filled." 
                    f"Latency={rec['latency_ms']}ms, Slip={rec['realized_slip']:.4f},"
                    f" Velocity={rec['fill_velocity']:.4f} qty/s"
                )
                return
            
        # Unexpected: Fill for an order not logged at placement
        logger.warning(
            f"Fill received for unknown order_id = {order_id}."
            "Creating synthetic execution_log entry with defaults."
        )

        synthetic_record = {
            "orderId": order_id,
            "qty": None, #Unknown
            "price": fill_price, # at least we know the fill price
            "placement_ts": fill_ts, # Assume fill_ts as placement baseline
            "latency_ms": None, #Cannot compute without true placement
            "realized_slip": None,      # cannot compute without expected price
            "fill_velocity": None,      # cannot compute without qty
            "liquidity": None,          # unknown
            "exp_fill_prob": None,      # unknown
            "regime": None,             # unknown
            "expected_slip": None,      # unknown
        }

        self.execution_log.append(synthetic_record)

    def get_recent_fill_velocity(self, lookback: int = 5) -> float:
        recent = self.execution_log[-lookback:]
        if not recent:
            return 0.0
        velocities = [rec.get("fill_velocity", 0.0) for rec in recent if rec.get("fill_velocity") is not None]
        return sum(velocities) / max(len(velocities), 1)
