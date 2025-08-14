import time, datetime
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
from Execution_layer.adaptive_sl_tp import AdaptiveSLTP
from Execution_layer.stealth_router import StealthRouter
import asyncio

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
        self.alpha_pipeline = AlphaSignalPipeline
        self.risk_engine = DynamicRiskEngine
        self.throttle_manager = ThrottleCooldownManager
        self.drawdown_manager = DailyDrawdownManager
        self.exchange_client = BinanceExecutionAdapter
        self.performance_tracker = PerformanceTracker
        self.confidence = SignalConfidenceCalibrator
        self.dynamic_position_sizer = DynamicPositionSizer
        self.orderbook = OrderBook


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
        order_type, price = self._choose_order_type_and_price(side)



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

               if bid_score >= self.config["min_confidence_to_trade"] and bid_score > ask_score:
                    return "BUY"
                    
               elif ask_score >= self.config["min_confidence_to_trade"] and ask_score > bid_score:
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
    

    def _choose_order_type_and_price(self, side: str) -> Tuple[str, Optional[float]]:
         """
         Select order type adaptively based on spread and volatility
         """

         best_bid = self.orderbook.get_best_price('bid')
         best_ask = self.orderbook.get_best_price('ask')
         spread = best_ask - best_bid


         if self.config["order_type_preference"] == "market":
              return "MARKET", None
         
         elif self.config["order_type_preference"] == "limit":
              return "LIMIT", best_ask if side == "BUY" else best_bid
         else:
              # Adaptive: if spread small, take with market; if large, place passive
              if spread / best_ask < 0.0002:    # < 2 bps
                   return "MARKET", None
              else:
                   price = best_ask if side == "BUY" else best_bid
                   return "LIMIT", price
    
    def _execute_order(self, side:str, size:float, order_type: str, price: Optional[float], ts: float, base_sl: float, base_tp: float, side_for_sl:str):
         """
         Send the order via StealthRouter for stealth execution
         """
         try:
               order_id = self.stealth_router.execute_parent_order(
                        side=side,
                        total_qty=size,
                        order_type=order_type,
                        limit_price=price,
                   )
               self.active_entry_order_ids = order_id
         except Exception as e:
              logger.exception("StealthRouter execution failed: %s", e)
              return
         

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

         logger.info("Placed order %s side=%s type=%s price=%s sl=%s tp=%s", self.active_entry_order_ids,
                     side, size, order_type, price, base_sl, base_tp)
    

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