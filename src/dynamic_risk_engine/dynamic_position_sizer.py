from dynamic_risk_engine.signal_confidence_calibrator import SignalConfidenceCalibrator
from dynamic_risk_engine.performance_tracker import PerformanceTracker
from market_data.orderbook import OrderBook
from dynamic_risk_engine.daily_drawdown_manager import DailyDrawdownManager
from Execution_layer.binance_adapter import BinanceExecutionAdapter

class DynamicPositionSizer:
    def __init__(self):
        """
        Initialize the dynamic position sizer.
        
        :param max_risk_per_trade: Maximum risk per trade as a fraction of account balance (default 0.01 for 1%)
        :param account_balance: Total account balance (default 100000)
        """

        self.account_balance = BinanceExecutionAdapter()
        self.confidence =SignalConfidenceCalibrator()
        self.win_rate = PerformanceTracker()

        self.volatility = OrderBook()
        self.drawdown = DailyDrawdownManager(daily_drawdown_limit=0.25)
        self.stop_loss = BinanceExecutionAdapter()

        self.max_risk_per_trade = None 
    
    async def initialize(self):
        await self.drawdown.initialize()
        self.max_risk_per_trade = self._compute_max_risk_per_trade()

    def get_drawdown_throttle(self) -> float:
        drawdown = self.drawdown.get_daily_drawdown_limit()
        if drawdown >= 0:
            return 1.0 # No drawdown, no throttle
        elif drawdown <= -0.25:
            return 0.5 # Heavy throttle
        elif drawdown <= -0.1:
            return 0.75 # Moderate throttle
        else:
            return 0.9 # Light throttle

    def _compute_max_risk_per_trade(self):
        win_rate = self.win_rate.win_rate()
        rrr = self.win_rate.average_rrr()
        
        #Bootstrap RRR if undefined or zero
        if rrr is None or rrr <= 0:
            confidence = self.confidence.get_current_confidence()
            rrr = 1.5 + confidence #Adaptive Fallback
        
        raw_risk =  win_rate - ((1 - win_rate) / rrr)
        return max(0.01, raw_risk)  # Ensure non-negative risk
    
    async def calculate_position_size(self, stop_loss_distance: float) -> float:
        """
          Calculate position size based on account balance, risk parameters, and signal confidence.
            :param stop_loss_distance: Distance to stop loss in price units
            :param signal_confidence: Confidence level of the trading signal (0.0 - 1.0)
            :param win_rate: Estimated win rate of the strategy (0.0 - 1.0)
            :param rr_ratio: Risk-reward ratio for the trade
            :return: Calculated position size in units
         """
        balance = await self.account_balance.get_account_balance()
        drawdown = self.drawdown.get_daily_drawdown_limit()

        throttle = self.get_drawdown_throttle()
        volatility = self.volatility.get_volatility_estimate()
        max_risk_per_trade = self.max_risk_per_trade
        risk_amount = balance* max_risk_per_trade
        adjusted_risk = risk_amount * self.confidence.get_current_confidence()*(0.5 + self.win_rate.win_rate())*volatility  *   throttle  #Scale with confidence and win rate

        if stop_loss_distance == 0:
            return 0 # Avoid division by zero
        
        position_size = adjusted_risk / stop_loss_distance

        if balance < risk_amount:
            #If the account balance is less than risk amount do not place trade
            return 0.0
        return round(position_size, 4)  # Round to 4 decimal places for practical use
    


    async def get_sizing_diagnostics(self, stop_loss_distance: float) -> dict:
        balance = await self.account_balance.get_account_balance()
        drawdown = abs(self.drawdown.get_daily_drawdown_limit())
        volatility = self.volatility.get_volatility_estimate()
        confidence = self.confidence.get_current_confidence()
        win_rate = self.win_rate.win_rate()
        risk_amount = balance * self.max_risk_per_trade
        adjusted_risk = risk_amount * confidence * (0.5 + win_rate) * volatility * drawdown

        return {
            "balance": balance,
            "drawdown": drawdown,
            "volatility": volatility,
            "confidence": confidence,
            "win_rate": win_rate,
            "risk_amount": risk_amount,
            "adjusted_risk": adjusted_risk,
            "stop_loss_distance": stop_loss_distance,
            "position_size": round(adjusted_risk / stop_loss_distance, 4) if stop_loss_distance > 0 else 0.0
        }


    async def reset(self):
        """
        Reset the position sizer to initial state.
        """
        await self.initialize()


