import time

class ThrottleCooldownManager:
    def __init__(self, max_losses = 3, cooldonw_seconds=300, max_trades_per_minute=10):
        """
        Initialize the throttle cooldown manager.:
        :param max_losses: Maximum consecutive losses before cooldown
        :param cooldonw_seconds: Cooldown period in seconds after max losses
        :param max_trades_per_minute: Maximum trades allowed per minute

        """
        self.loss_streak = 0
        self.last_trade_timestamp = 0
        self.cooldown_until = 0
        self.trade_timestamps = []
        self.max_losses = max_losses
        self.cooldown_seconds = cooldonw_seconds
        self.max_trades_per_minute = max_trades_per_minute

    def register_trade(self, pnl):
        """
        Register a trade with its PnL result.
        :param pnl: Profit or Loss from the trade
        :return: None

        """
        now = time.time()

        if pnl < 0:
            self.loss_streak += 1
        else:
            self.loss_streak = 0
        
        self.last_trade_timestamp = now
        self.trade_timestamps.append(now)
        self.trade_timestamps = [t for t in self.trade_timestamps if t > now - 60]  # Keep trades in last minute

        if self.loss_streak >= self.max_losses:
            self.cooldown_until = now + self.cooldown_seconds
            print(f"Cooldown activated until {self.cooldown_until}")
        
    def is_in_cooldown(self):
        """
        Check if currently in cooldown period.
        :return: True if in cooldown, False otherwise
        """
        now = time.time()
        return now < self.cooldown_until
    
    def can_trade(self):
        """
        Check if trading is allowed based on cooldown and trade rate limits.
        :return: True if trading is allowed, False otherwise
        """
        now = time.time()
        
        if self.is_in_cooldown():
            return False
        
        # Check trades per minute limit
        if len(self.trade_timestamps) >= self.max_trades_per_minute:
            return False
        
        return True

    