import time
from typing import Dict, Optional
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
        self.risk_engine = DynamicRiskEngine()
        self.throttle_manager = ThrottleCooldownManager()
        self.exchange_client = BinanceExecutionAdapter()
        self.performance_tracker = PerformanceTracker()
        self.confidence = SignalConfidenceCalibrator()
        self.dynamic_position_sizer = DynamicPositionSizer()
        self.orderbook = OrderBook()


        self.config = config or {
            "symbol": "BTCUSDT",
            "min_order_notional": 10,
            "max_position_usd": 1000,
            "default_risk_per_trade": 0.01,
            "min_confidence_to_trade": 0.55,
            "order_type_preference": "adaptive" #'market' ,'limit' or adaptive

        }


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
            
        #Risk + Throttle checks
        if not self._check_pre_trade_conditions():
            return 
            
        #Determine size
        order_size = self._compute_order_size()
        if order_size <= 0:
            return
        
            
        #Select order type and price
        order_type, price = self._choose_order_type_and_price(side)

        #Determine the SL and TP



        #Send Order
        self._execute_order(side, order_size, order_type, price, ts)


    def _decide_trade_side(self):
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
            
    def _compute_order_size(self) -> float:
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
    

    def _choose_order_type_and_price(self, side: str):
         """
         Select order type adaptively based on spread and volatility
         """

         best_bid = self.orderbook.get_best_price('bid')
         best_ask = self.orderbook.get_best_price('ask')
         spread = self.orderbook.get_best_price("spread", best_ask - best_bid)


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
    
    def _execute_order(self, side:str, size:float, order_type: str, price: Optional[float], ts: float, stop_loss: float, take_profit: float):
         """
         Send the order via exchange client
         """
         order_id = self.exchange_client.place_order(
              symbol = self.config["symbol"],
              side = side,
              size = size,
              order_type = order_type,
              price = price,
              stop_loss = stop_loss,
              take_profit = take_profit
         )

         if order_id:
              self.performance_tracker.record_trade(
                   pnl=0.0, #real PnL computed on fill
                   risk = size,
                   reward = 0.0,
                   metadata = {
                        "side": side,
                        "order_type": order_type,
                        "timestamp": ts,
                        "sl": stop_loss,
                        "tp": take_profit,
                   }
              )
