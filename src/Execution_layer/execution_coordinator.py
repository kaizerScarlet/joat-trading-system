import time
from typing import Dict, Optional
from alpha_scoring.alpha_pipeline import AlphaSignalPipeline
from dynamic_risk_engine.dynamic_risk_engine import DynamicRiskEngine
from dynamic_risk_engine.throttle_cooldown_manager import ThrottleCooldownManager
from dynamic_risk_engine.performance_tracker import PerformanceTracker
from Execution_layer.binance_adapter import BinanceExecutionAdapter
from Execution_layer.mock_adapter import MockExchangeAdapter #For testing and dry runs

class ExecutionCoordinator:
    """
    Coordinates execution for JOAT by combining alpha signals, 
    risk constraints, throttle limits, and execution tactics.
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
        side, confidence = self._decide_trade_side(alpha)
        if side is None:
            return # No trade opportunity
            
        #Risk + Throttle checks
        if not self._check_pre_trade_conditions(side, confidence):
            return 
            
        #Determine size
        order_size = self._compute_order_size(confidence, market_snapshot)
        if order_size <= 0:
            return
            
        #Select order type and price
        order_type, price = self._choose_order_type_and_price(side, market_snapshot)

        #Send Order
        self._execute_order(side, order_size, order_type, price, ts)


    def _decide_trade_side(self, alpha: Dict[str, float]):
            """
            Decide trade direction based on bid/ask scores.
            """
            bid_score = alpha.get("bid", 0.0)
            ask_score = alpha.get("ask", 0.0)

            if bid_score >= self.config["min_confidence_to_trade"] and bid_score > ask_score:
                return "BUY", bid_score
                
            elif ask_score >= self.config["min_confidence_to_trade"] and ask_score > bid_score:
                return "SELL", ask_score
                
            return None, 0.0
            


    def _check_pre_trade_conditions(self, side: str, confidence: float) -> bool:
            """
            Run all checks before placing an order
            """

            if self.throttle_manager.is_throttled():
                return False
            if not self.risk_engine.can_trade(side, confidence):
                return False 
            return True
            
    def _compute_order_size(self, confidence: float, market_snapshot: Dict) -> float:
            """
            Convert confidence into a position size in base asset
            """

            price = market_snapshot.get("mid_price", None)
            if not price:
                return 0.0
                

            risk_budget = self.config["default_risk_per_trade"] * self.config["max_position_usd"]
            usd_size = risk_budget * confidence #scale with confidence
            base_size = usd_size / price


            if usd_size < self.config["min_order_notional"]:
                return 0.0
            return round(base_size, 6)
    

    def _choose_order_type_and_price(self, side: str, market_snapshot: Dict):
         """
         Select order type adaptively based on spread and volatility
         """
         best_bid = market_snapshot.get("best_bid")
         best_ask = market_snapshot.get("best_ask")
         spread = market_snapshot.get("spread", best_ask - best_bid)


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
    
    def _execute_order(self, side:str, size:float, order_type: str, price: Optional[float], ts: float):
         """
         Send the order via exchange client
         """
         order_id = self.exchange_client.place_order(
              symbol = self.config["symbol"],
              side = side,
              size = size,
              order_type = order_type,
              price = price
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
                   }
              )
