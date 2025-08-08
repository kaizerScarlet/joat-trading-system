from typing import Dict, Any, Optional
from alpha_scoring.alpha_pipeline import AlphaSignalPipeline
from dynamic_risk_engine.dynamic_risk_engine import DynamicRiskEngine
from dynamic_risk_engine.performance_tracker import PerformanceTracker
from dynamic_risk_engine.throttle_cooldown_manager import ThrottleCooldownManager

class ExecutionEngine:
    """
    Central Engine for executing trades based on alpha signals and risk conditions.
    Integrates with alpha signal generators, risk enigne, throttle manager, order manager, and
    exchange APIs to determine and place trades in a compliant, adaptive manner.
    """

    def __init__(
            self, 
            order_manager,
            binance_api,
            execution_model,
            logger=None
    ):
        self.alpha_signal_pipeline = AlphaSignalPipeline()
        self.risk_engine = DynamicRiskEngine()
        self.throttle_manager = ThrottleCooldownManager()
        self.order_manager = order_manager
        self.binance_api = binance_api
        self.performance_tracker = PerformanceTracker()
        self.execution_model = execution_model
        self.logger = logger or print 


    def execute(self, timestamp: int, market_data:Dict[str, Any]):
        """
        Orchestrates  full trade decision and execution pipeline.
        """
        #1. Update alpha models
        self.alpha_signal_pipeline.update_market(timestamp, market_data)
        alpha_scores = self.alpha_signal_pipeline.get_alpha_signal(timestamp)

        for side in ['ask', 'bid']:
            score = alpha_scores.get(side, 0.0)
            if not self.risk_engine.can_trade():
                continue

            #2. Compute Order size from dynamic risk enigine
            size = self.risk_engine.get_position_size(stop_loss_distance=10)
            if size <= 0:
                continue


            #3. Check throttle limits(Binance compliance)
            if not self.throttle_manager.is_throttled():
                self.logger(f"[{side}] Order Throttled")
                continue

            #4. Determine optimal order type (market vs limit)
            order_type = self.execution_model.choose_order_type(score, market_data, side)
            price = self.execution_model.estimate_price(score, market_data, side, order_type)

            #5. Submit Order through Binance API
            order_response = self.order_manager.place_order(
                side = side,
                size = size,
                price = price,
                order_type = order_type,
                metadata = {
                    "Alpha_Score": score,
                    "Order_type": order_type,
                    "side": side,
                    "timestamp": timestamp
                }
            )


            #Record the order to throttle manager
            self.throttle_manager.record_order(volume=size, weight=order_response.get("weight", 1))

            #6. Handle order fill and update tracker
            if order_response.get("filled"):
                pnl = order_response.get("pnl", 0.0)


                #Feed the trade result to the throttle manager for cooldown
                self.throttle_manager.register_trade_result(pnl)

                risk = self.risk_engine.get_risk_for_trade(score, side)
                reward = pnl if pnl > 0 else 0.0

                #Record Trade for Peformance Tracker
                self.performance_tracker.record_trade(
                    pnl = pnl,
                    risk = risk,
                    reward = reward,
                    metadata = {
                        "Alpha_Score": score,
                        "side": side,
                        "order_type": order_type,
                        "price": price,
                    }
                )

                

                #7. Feedback to Alpha Blender
                self.alpha_signal_pipeline.trade_feedback(
                    signal_dict = {
                        "cancel_activity": market_data.get("cancel_score", 0.0),
                        "layering": market_data.get("layering_score", 0.0),
                        "order_type": market_data.get("age_score", 0.0)
                    },
                    pnl = pnl,
                    side = side
                )

    def get_debug_info(self) -> Dict[str, Any]:
        return {
            "alpha": self.alpha_signal_pipeline.get_debug(),
            "risk": self.risk_engine.get_diagnostic(),
            "Throttle_Manager_Binance": self.throttle_manager.get_diagnostic(),
            "Performance": self.performance_tracker.get_summary()
        }