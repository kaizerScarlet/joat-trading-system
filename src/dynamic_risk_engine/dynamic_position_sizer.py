class DynamicPositionSizer:
    def __init__(self, max_risk_per_trade: float, account_balance: float):
        """
        Initialize the dynamic position sizer.
        
        :param max_risk_per_trade: Maximum risk per trade as a fraction of account balance (default 0.01 for 1%)
        :param account_balance: Total account balance (default 100000)
        """
        self.max_risk_per_trade = max_risk_per_trade
        self.account_balance = account_balance
    
    def calculate_position_size(self, stop_loss_distance, signal_confidence: float, win_rate: float, rr_ratio: float):
        """
        Calculate position size based on account balance, risk parameters, and signal confidence.
        :param stop_loss_distance: Distance to stop loss in price units
        :param signal_confidence: Confidence level of the trading signal (0.0 - 1.0)
        :param win_rate: Estimated win rate of the strategy (0.0 - 1.0)
        :param rr_ratio: Risk-reward ratio for the trade
        :return: Calculated position size in units
        """
        risk_amount = self.account_balance * self.max_risk_per_trade
        adjusted_risk = risk_amount * signal_confidence * (0.5 + win_rate) #Scale with confidence and win rate

        if stop_loss_distance == 0:
            return 0 # Avoid division by zero
        
        position_size = adjusted_risk / stop_loss_distance
        return round(position_size, 4)  # Round to 4 decimal places for practical use
    


    def reset(self):
        """
        Reset the position sizer to initial state.
        """
        self.max_risk_per_trade = 0.01
        self.account_balance = 100000 #Need to fetch this information using binance, for now these are place holders

