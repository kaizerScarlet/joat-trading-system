from dynamic_risk_engine.signal_confidence_calibrator import SignalConfidenceCalibrator
from dynamic_risk_engine.performance_tracker import PerformanceTracker
from market_data.orderbook import OrderBook
from dynamic_risk_engine.daily_drawdown_manager import DailyDrawdownManager
from Execution_layer.binance_adapter import BinanceExecutionAdapter

class DynamicPositionSizer:
    def __init__(self, account_balance: float):
        """
        Initialize the dynamic position sizer.
        
        :param max_risk_per_trade: Maximum risk per trade as a fraction of account balance (default 0.01 for 1%)
        :param account_balance: Total account balance (default 100000)
        """

        self.account_balance = BinanceExecutionAdapter()
        self.confidence =SignalConfidenceCalibrator()
        self.win_rate = PerformanceTracker()

        self.volatility = OrderBook()
        self.drawdown = DailyDrawdownManager()
        self.stop_loss = BinanceExecutionAdapter()

        self.max_risk_per_trade = (self.win_rate.win_rate()) - ((1 - self.win_rate.win_rate()) / self.win_rate.average_rrr())
    
    def calculate_position_size(self, stop_loss_distance):
        """
        Calculate position size based on account balance, risk parameters, and signal confidence.
        :param stop_loss_distance: Distance to stop loss in price units
        :param signal_confidence: Confidence level of the trading signal (0.0 - 1.0)
        :param win_rate: Estimated win rate of the strategy (0.0 - 1.0)
        :param rr_ratio: Risk-reward ratio for the trade
        :return: Calculated position size in units
        """
        drawdown = self.drawdown.get_daily_drawdown_limit()
        volatility = self.volatility.get_volatility_estimate()
        max_risk_per_trade = self.max_risk_per_trade
        risk_amount = self.account_balance.get_account()* max_risk_per_trade
        adjusted_risk = risk_amount * self.confidence.get_current_confidence()*(0.5 + self.win_rate.win_rate())*volatility  * drawdown   #Scale with confidence and win rate

        if stop_loss_distance == 0:
            return 0 # Avoid division by zero
        
        position_size = adjusted_risk / stop_loss_distance

        if self.account_balance < risk_amount:
            #If the account balance is less than risk amount do not place trade
            return 0.0
        return round(position_size, 4)  # Round to 4 decimal places for practical use
    


    def reset(self):
        """
        Reset the position sizer to initial state.
        """
        self.max_risk_per_trade = (self.win_rate.win_rate()) - ((1 - self.win_rate.win_rate()) / self.win_rate.average_rrr())
        self.account_balance =  self.account_balance.get_account()        #Need to fetch this information using binance, for now these are place holders

