import time
from datetime import datetime
from typing import Dict, Optional, Tuple, Any
import logging
from alpha_scoring.alpha_pipeline import AlphaSignalPipeline
from dynamic_risk_engine.dynamic_risk_engine import DynamicRiskEngine
from dynamic_risk_engine.throttle_cooldown_manager import ThrottleCooldownManager
from dynamic_risk_engine.performance_tracker import PerformanceTracker
from Execution_layer.binance_adapter import BinanceExecutionAdapter
from Execution_layer.mock_adapter import MockExchangeAdapter #For testing and dry runs
from dynamic_risk_engine.signal_confidence_calibrator import SignalConfidenceCalibrator
from dynamic_risk_engine.dynamic_position_sizer import DynamicPositionSizer
from market_data.orderbook import OrderBook
from dynamic_risk_engine.daily_drawdown_manager import DailyDrawdownManager
from dynamic_risk_engine.cognitive_market_regime_classifier import CognitiveMarketRegimeClassifier, MarketRegime
from Execution_layer.adaptive_sl_tp import AdaptiveSLTP
from Execution_layer.stealth_router import StealthRouter
from Execution_layer.fee_schedule import FeeSchedule
from Execution_layer.slippage_model import SlippageModel
from Execution_layer.latency_model import LatencyModel
from Execution_layer.queue_position_model import QueuePositionModel
from alpha_scoring.order_age_scorer import OrderAgeDistributionScorer
from alpha_scoring.Order_layering_scorer import LayeringScoring
from alpha_scoring.cancel_activity_scorer import CancelActivityScorer
import asyncio


# ---- Execution frictions models (lightweight, pluggable) ----
import random
import math







logger = logging.getLogger(__name__)

class ExecutionCoordinator:
    """
    ExecutionCoordinator: decides, executes, and reconciles fills/positions
    Coordinates execution for JOAT by combining alpha signals, 
    risk constraints, throttle limits, and execution tactics.
    -Maintains local order registry (orders_by_id)
    -Maintains simple portfolio: position.size (positive = long, negative = short), avg_price
    -Computes realized PnL on fills that reduce position
    -Updates PerformanceTracker with realized PnL and simple risk estimate

    """
    def __init__(
            self,
            config: Optional[Dict] = None
    ):
        """
        Args:
            alpha_pipeline: AlphaSignalPipeline instance (produces bid/ask scores)
            risk_engine: DynamicRiskEngine instance
            throttle_manager: ThrottleCooldownManager instance
            exchange_client: BinanceExecutionAPI or mock adapter
            performance_tracker: PerformanceTracker instance
            config: Optional dict with execution settings
        """
        self.alpha_pipeline = AlphaSignalPipeline()
        self.risk_engine = DynamicRiskEngine(daily_drawdown_limit=0.25)
        self.throttle_manager = ThrottleCooldownManager()
        self.drawdown_manager = DailyDrawdownManager(daily_drawdown_limit=0.25)
        self.exchange_client = BinanceExecutionAdapter()
        self.performance_tracker = PerformanceTracker()
        self.confidence = SignalConfidenceCalibrator()
        self.dynamic_position_sizer = DynamicPositionSizer()
        self.orderbook = OrderBook()

        self.regime_classifier = CognitiveMarketRegimeClassifier()
        self.spoofing_detector = CancelActivityScorer()
        self.layering_scorer = LayeringScoring()
        self.order_age_scorer= OrderAgeDistributionScorer()

        #Instantiate adaptive SL/TP and give it the orderbook so it can fetch microstructure score
        self.sl_and_tp = AdaptiveSLTP(
             atr_window = 14,
             base_atr_multiplier=1.5,
             vol_multiplier=2.0
        )


        self.config = config or {
            "symbol": "BTCUSDT",
            "min_order_notional": 10,
            "max_position_usd": 1000,
            "default_risk_per_trade": 0.01,
            "min_confidence_to_trade": 0.55,
            "maker_bps": 8.0,
            "taker_bps": 10.0,
            "latency_jitter_ms": 20.0,
            "queue_horizon_sec": 5,
            "latency_tail_p": 0.05,
            "latency_tail_mult": 3.0,
            "impact_coeff": 0.5,        # higher => more market impact assumed
            "order_type_preference": "adaptive" #'market' ,'limit' or adaptive

        }

        self.sl_order_id = None
        self.tp_order_id = None
        self.position_size = 0.0
        self.entry_price = 0.0

        #Assign on_fill callback to adapter
        self.exchange_client.on_fill_callback = self._on_fill

        #Stealth router
        self.stealth_router = StealthRouter(
             exchange_client=self.exchange_client,
             symbol=(config or {}).get("symbol", "BTCUSDT"),
             min_slice_usd=50,
             max_slice_usd=500,
             random_delay_range=(0.3, 1.5),
             tick_size=0.01
        )

        # -----Execution Frictions config --------
        self.fees = FeeSchedule(
             maker_bps=(self.config.get("maker_bps", 8.0)),
             taker_bps=(self.config.get("taker_bps", 10.0)),
        )

        self.latency = LatencyModel(
             base_ms=self.config.get("latency_base_ms", 20.0),
             jitter_ms=self.config.get("latency_jitter_ms", 15.0),
             p_tail=self.config.get("latency_tail_p", 0.05),
             tail_multiplier=self.config.get("latency_tail_mult", 3.0),
        )

        self.slippage_model = SlippageModel(
             impact_coeff=self.config.get("impact_coeff", 0.5)
        )

        self.queue_model = QueuePositionModel()
         

    # Startup reconciliation (loaction: ExecutionCoordiantor)
    async def reconcile_open_orders(self):
         """
         Fetch open orders from adapter and reconcile with local state/cache.
         """
         try:
              all_open = await self.exchange_client.get_open_orders()
              logger.info("coordinator reconciliation found %d open orders", len(all_open))
         except Exception:
              logger.exception("Failed to reconcile open orders on startup")
         
    def now_ms(self) -> int:
         """
         Return Monotonic current time in ms adjusted by server offset if available
         """
         return int(time.time() * 1000 + getattr(self, "time_offset_ms", 0))

    def on_new_alpha(self, alpha: Dict[str, float], market_snapshot: Dict):
        """
        Called whenever a new alpha is produced.
        Args:
            alpha: dict with {'bid': float, 'ask': float}
            market_snapshot: dict with current best bid/ask, spreads, volumes

        """

        ts = time.time()

        #Decide trade side
        side = self._decide_trade_side()
        if side is None:
            return # No trade opportunity
            
        #Risk + Throttle checks + Daily Drawdown Check
        if not self._check_pre_trade_conditions():
            return 
        


        #Estimate initial SL/TP distances so position sizer can compute size.
        #We compute base_distance similarly to AdaptiveSLTP.start_trade so sizing uses same assumptions
        side_for_sl = 'bid' if side == 'BUY' else 'ask'
        base_sl, base_tp = self.sl_and_tp.start_trade(side_for_sl)

        if base_sl is None or base_tp is None:
             logger.debug("Unable to estimate initial SL/TP; aborting trade.")

        
        stop_loss_distance = abs(self.orderbook.get_midprice() - base_sl)


        #Determine size using dyanamic position sizer (expects risk / stop loss)
        order_size = self._compute_order_size(stop_loss_distance)
        if order_size <= 0:
            logger.debug("Calculated order_size <= 0; aborting trade.")
            return
        
            
        #Select order type and price
        order_type, price = self._choose_order_type_and_price(side, order_size)



        #Send Order
        self._execute_order(side, order_size, order_type, price, ts, base_sl, base_tp, side_for_sl)
     
    async def _on_fill(self, fill: Dict[str, Any]):
         """
         Called by adapter when any order fills.
         Handles SL/TP hits, entry fills, and stealth slice fills.
         """
         order_id = fill.get("order_id")
         side = fill.get("side")
         qty = fill.get("qty", 0)
         price = fill.get("price", 0.0)
         symbol = fill.get("symbol")

         # --- Fill latency ----
         dispatch_ts = fill.get("dispatch_ts")
         fill_ts = fill.get("fill_ts", self.now_ms())
         if dispatch_ts:
              latency_ms = fill_ts - dispatch_ts
              self.performance_tracker.record_latency(latency_ms)

         # --- Slippage ----
         expected_price = fill.get("expected_price")
         if expected_price:
              slippage = abs(price - expected_price)
              self.performance_tracker.record_slippage(slippage)

         # --- Fee attribution (NEW) ---
         liquidity = fill.get("liquidity", None) #"Maker" / "Taker" / None
         fee_rate = (self.fees.maker_rate() if liquidity == "MAKER" else self.fees.taker_rate())

         notional = abs(qty * price)
         fee = notional * fee_rate

         try:
              self.performance_tracker.record_fee(fee) # if your tracker supports it
     
         except Exception:
              pass

         # ------Stop loss hit -------
         if order_id == self.sl_order_id:
              await self.exchange_client.cancel_order_by_id(self.tp_order_id)
              self._reset_position_state()
              return
         # -------Take Profit hit ------
         if order_id == self.tp_order_id:
              await self.exchange_client.cancel_order_by_id(self.sl_order_id)
              self._reset_position_state()
              return
         
         # -----Entry fill (first fill) ----
         if self.position_size == 0 and qty > 0:
              #Track position from first fill
              self.position_size = qty if side == "BUY" else -qty
              self.entry_price = price 

              #Get SL/TP from AdaptiveSLTP at fill time
              sl_price, tp_price = self.sl_and_tp.start_trade(side.lower() if side else None)
              self.sl_order_id = await self.exchange_client.place_stop_loss_order(symbol, side, sl_price, qty)
              self.tp_order_id = await self.exchange_client.place_take_profit_order(symbol, side, tp_price, qty)

         # ----- Stealth slice awareness ------
         if hasattr(self, "active_entry_order_ids") and order_id in self.active_entry_order_ids:
              #This fill is part of our stealth parent order
              logger.debug(f"stealth slice filled: order_id={order_id}, qty={qty}, price={price}")
    
              #If we already have an open position, adjust SL/TP dynamically
              if self.position_size != 0:
                   self._update_sl_tp_after_slice(qty, side)
                   
    def _update_sl_tp_after_slice(self, qty: float, side: str):
         """
         Dynamically adjust SL/TP after an additional stealth slice fills
         Keeps position risk parameters in sync with new size.
         """
         sl_price, tp_price = self.sl_and_tp.get_sl_tp()
         if self.sl_order_id:
              asyncio.create_task(
                   self.exchange_client.modify_order(
                        symbol=self.config["symbol"],
                        orig_order_id=self.sl_order_id,
                        new_qty=abs(self.position_size) + qty,
                        new_price = sl_price
                   )
              )
         if self.tp_order_id:
              asyncio.create_task(
                   self.exchange_client.modify_order(
                        symbol=self.config["symbol"],
                        orig_order_id=self.tp_order_id,
                        new_qty=abs(self.position_size) + qty,
                        new_price = tp_price
                   )
              )
         logger.info(f"Adjusted SL/TP after stealth slice fill: SL={sl_price}, TP={tp_price}")

    def _decide_trade_side(self) -> Optional[str]:
               """
               Decide trade direction based on bid/ask scores.
               Args:
                    :param alpha: Dict {'bid": score, 'Ask': score}
               """
               alpha = self.alpha_pipeline.get_alpha_signal()
               bid_score = alpha.get("bid", 0.0)
               ask_score = alpha.get("ask", 0.0)

               regime = self.regime_classifier.get_current_regime()
               current_time = int(time.time() * 1000)
               spoof_pressure = self.spoofing_detector.compute_score(current_time, side=None)
               layering_score = self.layering_scorer.compute_score(current_time)
               order_age_bias = self.order_age_scorer.compute_score(side=None) #returns {'bid': float, 'ask': float }

               #---- Interpret order age bias ----
               bid_age_score = order_age_bias.get('bid', 0.0)
               ask_age_score = order_age_bias.get('ask', 0.0)

               # ----Interpret spoof pressure ----
               bid_cancel_spoof = spoof_pressure.get('bid', 0.0)
               ask_cancel_spoof = spoof_pressure.get('ask', 0.0)

               #---- Interpret layering score ----
               bid_layering_score = layering_score.get('layering_score', 0.0)
               ask_layering_score = layering_score.get('layering_score', 0.0)

               # ---- Decision Logic ----
               if bid_score >= self.config["min_confidence_to_trade"] and bid_score > ask_score:
                    if regime == "TRENDING":
                         if bid_cancel_spoof < 0.3 or bid_layering_score > 0.5:
                              return "BUY"
                    elif regime == "MEAN_REVERTING":
                         if bid_cancel_spoof > 0.7 or bid_age_score < 0.0:
                              return None # Fade spoof
                         return "SELL" # fade bid aggression
                    elif regime == "ILLIQUID":
                         if order_age_bias > 0.5 and bid_layering_score > 0.4:
                              return "BUY" #Follow strong bid aggression
                    elif regime == "LIQUID":
                         return "BUY" #Spoof impact low
                    
               elif ask_score >= self.config["min_confidence_to_trade"] and ask_score > bid_score:
                    if regime == "TRENDING":
                         if ask_cancel_spoof < 0.3 or ask_layering_score > 0.5:
                              return "SELL"
                    elif regime == "MEAN_REVERTING":
                         if ask_cancel_spoof > 0.7 or ask_age_score < 0.0:
                              return None
                         return "BUY" # fade ask aggression
                    elif regime == "ILLIQUID":
                         if order_age_bias > 0.5 and ask_layering_score > 0.4:
                              return "SELL" #Follow strong ask aggression
                    elif regime == "VOLATILE":
                         if ask_cancel_spoof < 0.5 and ask_layering_score > 0.3:
                              return "SELL"
                    elif regime == "LIQUID":
                         return "SELL"
               return None

    def _check_pre_trade_conditions(self) -> bool:
            
            """
            Run all checks before placing an order
            Args: 
                :param side: str
                :param confidence: float
            """

            #Computes the confidence to trade
            confidence = self.confidence.get_current_confidence()
            #If the confidence is less than 55% then trade condition not met
            if confidence < 0.55:
                 return False
            
            if self.throttle_manager.is_throttled():
                return False
            
            if not self.risk_engine.can_trade():
                return False 
    
            return True
            
    def _compute_order_size(self, stop_loss_distance: float) -> float:
            """
            Convert confidence into a position size in base asset
            Args:
                :param confidence: float
                :param market_snapshot: Dict

            :Returns:
                    Order_size(lot)
            """

            price = self.orderbook.get_midprice()
            if price == 0.0:
                """
                This means that mid_price is not available
                this defaults to zero
                """
                return 0.0
            #This give the overall size of my position
            order_size = self.dynamic_position_sizer.calculate_position_size(stop_loss_distance)
            #Need to make it such that it tells me how much I need to buy and sell to get there
            #To minimize slippage
            """
            Code to follow here: To break down orders.
            """

            return order_size
    

    def _choose_order_type_and_price(self, side: str, order_size: float) -> Tuple[str, Optional[float]]:
         """
         Select order type adaptively based on spread, volatility, fee, slippage, and Queue-position fill probability

         Hybrid mode:
               -Start passive (LIMIT) if cost advantage is clear.
               -Auto-upgrade to MARKET (cross) if queue-fill probability drops below threshold
               within configured horizon
         """

         best_bid = self.orderbook.get_best_price('bid')
         best_ask = self.orderbook.get_best_price('ask')
         mid = (best_bid + best_ask) * 0.5 if best_bid and best_ask else None
         spread = (best_ask - best_bid) if best_bid and best_ask else 0.0

         #if explicit preference, keep it
         pref = self.config.get("order_type_preference", "adaptive")
         if pref == "market":
              return "MARKET", None
         if pref == "limit":
              return "LIMIT", (best_ask if side == "BUY" else best_bid)
         
         #Adaptive: Compare expected cost (fees + slippage)
         #Need top of book liquidity if available; if your OrderBook exposes it, use it else fallback
         top_liq = getattr(self.orderbook, "get_top_liquidity", lambda *_: 0.0)(side)
         if mid:
              # rough market slippage for 1 unit, size-aware tweak is applied at execution time
              exp_slip = self.slippage_model.expected_market_slip(side, mid, spread, qty=order_size, top_liquidity=max(1.0, top_liq))
         else:
              exp_slip = spread * 0.5

         #Fees (bps -> fraction)
         taker_fee = self.fees.taker_rate()
         maker_fee = self.fees.maker_rate()

         #Cost if we cross now (market): spread / 2 +impact + taker fee
         market_cost_bps_equiv = (exp_slip / (mid or best_ask or 1.0)) * 1e4 + taker_fee * 1e4

         #Cost if we rest: maker fee (maybe rebate) but risk of not filling
         #Crude: if spread is wide, prefer resting; if very tight, prefer taking.
         rest_cost_bps_equiv = maker_fee * 1e4

         #Queue-Position penalty (bps)
         exp_fill_prob = 1.0
         if top_liq > 0 and mid:
              #Estimate queue fraction & per second fill prob
              qfrac, fill_prob_per_s = self.queue_model.estimate(
               side=side, 
               our_qty=order_size,   #actual order size(or slice size)
               tob_qty=top_liq, 
               orderbook=self.orderbook #New: inject live activity
               )

              #Suppose we want at least 80% chance of fill within horizon_h(sec)
              horizon_s = self.config.get("queue_horizon_sec", 5)

              #Probability of filling within horizon
              exp_fill_prob = 1 -( 1 - fill_prob_per_s) ** horizon_s

              #If probability is low, assign penalty proportional to spread
              #e.g if only 20% chnace of fill -> 80% of spread is effectively "risk"
              penalty_bps = (1.0 - exp_fill_prob) * (spread / (mid or 1.0)) * 1e4
              rest_cost_bps_equiv += penalty_bps


         # ------- Hybrid Decision Logic ------------
         #if Market is cheaper or safer, take immediately
         if market_cost_bps_equiv <= rest_cost_bps_equiv:
              #cheaper (or safer to cross now)
              return "MARKET", None
         else:
              #Otherwise, start as Limit, but watch fill probability
              #Hybrid upgrade path is handled in StealthRouter mid-trade
              #cheaper  to rest -> place passive at best, nudge toward mid
              base = (best_ask if side == "BUY" else best_bid)
              price = self.slippage_model.expected_limit_price(side, base, mid or base, micro_revert_bps=0.5)

              #Store inital expectation for hybrid mode monitoring
              self.last_expected_fill_prob = exp_fill_prob
              return "LIMIT", price
         

    def _execute_order(self, side:str, size:float, order_type: str, price: Optional[float], ts: float, base_sl: float, base_tp: float, side_for_sl:str):
         """
         Send the order via StealthRouter for stealth execution with latency/ fees / slippage awareness
         """
         async def _run():
               try:
                    # ----latency simulation before first child Leaves the house ---
                    await asyncio.sleep(self.latency.sample_ms() / 1000.0)
                    result = self.stealth_router.execute_parent_order(
                        side=side,
                        total_qty=size,
                        order_type=order_type,
                        limit_price=price,
                        fee_schedule = self.fees,                #New
                        slippage_model = self.slippage_model,    #New (for per-slice adjustments)
                        orderbook = self.orderbook ,   #New (for queue/top-liq)
                        metadata = {
                             "dispatch_ts": self.now_ms(),
                               "expected_price": price
                        }
                   )
                    #Result = list of slice records; store IDs for later reconciliation
                    self.active_entry_order_ids = [r["orderId"] for r in result if "orderId" in r]

               except Exception as e:
                    logger.exception("StealthRouter execution failed: %s", e)
                    return
         
               # Record metadata (You can aggregate expected cost here if you like)
               self.performance_tracker.record_trade(
                   pnl=0.0, #real PnL computed on fill
                   risk = size,
                   reward = 0.0,
                   metadata = {
                        "side": side,
                        "order_type": order_type,
                        "timestamp": ts,
                        "sl": base_sl,
                        "tp": base_tp,
                   }
               )
               #Initialize SL/TP manager state for the new trade
               # AdaptiveSLTP expects 'bid' (long) 
               try:
                    self.sl_and_tp.start_trade(side_for_sl)
                
               except Exception as e:
                    logger.exception("Failed to initialize AdaptiveSLTP start_trade(): %s", e)

               logger.info("Placed parent order with %d slices; type=%s price=%s sl=%s tp=%s", len(self.active_entry_order_ids or []),
                      order_type, price, base_sl, base_tp)
         asyncio.create_task(_run())
    

    # -----------------------
    # Market tick handling
    # -------------------------
    def on_market_tick(self, high: Optional[float] = None, low: Optional[float] = None, close: Optional[float]=None):
         """
            Called on every new tick or each book snapshot update
            Responsibilities:
                -Feed candlesticks data (if available) to the SL/TP manager for ATR
                -Ask AdaptiveSLTP to monitor and adjust SL/TP (tick by tick)
                -Propagate changes by modifying SL/TP orders on open positions

         """

         # Update candle history if we receive OHLC (runner may supply these)
         if high is not None and low is not None and close is not None:
              try:
                   self.sl_and_tp.update_candlestick(high, low, close)
              except Exception:
                   logger.debug("Error updating candlestick to AdaptiveSLTP", exc_info=True)

         #The SL/TP manager updates internal SL/TP based on microstructure and volatility
         try:
              self.sl_and_tp.monitor_and_adjust()
         except Exception:
              logger.exception("Error running AdaptiveSLTP.monitor_and_adjust()")

         #Emergency tighten on bad alpha
         try:
               debug_info = self.sl_and_tp.debug_state()
               composite_score = float(debug_info.get("composite_score", 1.0))
               if composite_score < 0.55:
                    logger.warning("Low composite score detected(%.3f) - tighten SL aggressively.", composite_score)
                    # Re-run monitor with awareness (we could also set a flag inside AdaptiveSLTP to force gap gap min)
                    self.sl_and_tp._emergency_mode = True
                    self.sl_and_tp.monitor_and_adjust()
         except Exception:
              logger.exception("Emergency SL tigthen logic failed")

         # Emergency override under drawdown stress
         try:
              drawdown = self.drawdown_manager.calculate_daily_drawdown(datetime.now())
              threshold = self.drawdown_manager.get_daily_drawdown_limit()
              if drawdown <= threshold:
                       logger.warning("Drawdown threshold breached (%.3f <= %.3f) — forcing SL tightening.", drawdown, threshold)
                       self.sl_and_tp._emergency_mode = True
                       self.sl_and_tp.monitor_and_adjust()
         except Exception:
                 logger.exception("Drawdown override logic failed")
     
         #Log current SL/TP state for traceability
         try:
               sl, tp = self.sl_and_tp.get_sl_tp()
               self.performance_tracker.record_sl_tp_drift( sl, tp)
               debug_snapshot = self.sl_and_tp.debug_state()
               logger.debug("SLTP Debug State: %s", debug_snapshot)
         except Exception:
              logger.exception("failed to log AdaptiveSLTP debug state")


        #Push updated SL/TP to exchange for open positions
         self.monitor_open_positions()


    # ----------------------
    # Open positions syncing
    # -----------------------

    def monitor_open_positions(self):
         """
         Retrieve open positions from the exchange and update stop-loss / take-profit
         levels if AdaptiveSLTP produced new SL/TP.
         """
         try:
              open_positions = self.exchange_client.get_open_positions(symbol=self.config['symbol'])
         except Exception:
              logger.exception("Failed to fetch open positions from Exchange")
         
         #Get SL/TP from our manager
         sl, tp = self.sl_and_tp.get_sl_tp()


         for pos in open_positions:
              #Example pos dict expected: {'id', 'side', 'entry_price', 'stop_loss', 'take_profit'}
              pos_id = pos.get('id')
              pos_side = pos.get('side')    #Buy or sell
              #Compare and update only if different
              try:
                   #Map sides consistently
                   if sl is None or tp is None:
                        continue
                   #Current on-exchange SL/TP
                   pos_sl = pos.get('stop_loss')
                   pos_tp = pos.get('take_profit')


                   #Only match if different (avoid excessive modify calls)
                   if (pos_sl != sl) or (pos_tp != tp):
                        self.exchange_client.modify_order_sl_tp(
                             position_id = pos_id,
                             stop_loss = sl,
                             take_profit = tp
                        )
                        logger.debug("Modified position %s SL/TP -> sl=%s tp=%s", pos_id, sl, tp)

              except Exception:
                   logger.exception("Failed to modify SL/TP for Position %s", pos_id)

    def _reset_position_state(self):
         self.position_size = 0.0
         self.entry_price = 0.0
         self.sl_order_id = None
         self.tp_order_id = None