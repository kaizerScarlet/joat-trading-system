import time

class ThrottleCooldownManager:
    def __init__(self, max_losses=3, cooldown_seconds=300, max_trades_per_minute=3):
        """
        Initialize the throttle cooldown manager.
        
        :param max_losses: Maximum number of consecutive losing trades allowed before cooldown is triggered.
        :param cooldown_seconds: Time (in seconds) for which trading is paused after hitting max_losses.
        :param max_trades_per_minute: Limit to prevent excessive trading within a short time window.
        """
        self.max_losses = max_losses
        self.cooldown_seconds = cooldown_seconds
        self.max_trades_per_minute = max_trades_per_minute

        self.loss_streak = 0  # Tracks consecutive losses
        self.cooldown_until = 0  # Timestamp until which trading is paused
        self.trade_timestamps = []  # List to track recent trade times for rate limiting

    def register_trade(self, pnl: float):
        """
        Register a trade and apply logic for cooldown and rate-limiting.
        
        :param pnl: Profit or Loss of the trade (positive for profit, negative for loss)
        """
        now = time.time()

        # Update the loss streak
        if pnl < 0:
            self.loss_streak += 1
        else:
            self.loss_streak = 0  # Reset the loss streak on a winning trade

        # If loss streak hits the threshold, activate cooldown
        if self.loss_streak >= self.max_losses:
            self.cooldown_until = now + self.cooldown_seconds
            print(f"[COOLDOWN ACTIVATED] Until {self.cooldown_until}")
            return

        #Only add to timestamp if not in cooldown
        if not self.is_in_cooldown() and pnl < 0:
            # Record the time of this trade
            self.trade_timestamps.append(now)
            # Remove timestamps older than 60 seconds for rate-limiting
            self._prune_trade_timestamps(now)

    def is_in_cooldown(self) -> bool:
        """
        Check if we are currently in a cooldown period.
        
        :return: True if still in cooldown; False otherwise
        """
        now = time.time()
        if now < self.cooldown_until:
            return True
        else:
            # Cooldown has expired — reset internal state
            if self.cooldown_until != 0:
                self.cooldown_until = 0
                self.loss_streak = 0
            return False

    def can_trade(self):
        """
        Check if trading is allowed based on cooldown and trade rate limits.
        :return: True if trading is allowed, False otherwise
        """
        now = time.time()

        # ❌ Deny trading if still in cooldown period
        if self.is_in_cooldown():
            return False

        # ⬇️ Prune timestamps older than 60 seconds to enforce rate limit
        self._prune_trade_timestamps(now)

        # ❌ Deny if too many trades occurred in the last 60 seconds
        if len(self.trade_timestamps) >= self.max_trades_per_minute:
            return False

        # ✅ Allow trading
        return True


    def _prune_trade_timestamps(self, now):
        """
        Remove trade timestamps older than 60 seconds.
        
        This helps enforce the trades-per-minute limit.
        """
        self.trade_timestamps = [t for t in self.trade_timestamps if t > now - 60]

    def reset(self):
        """
        Completely reset the manager’s internal state.
        
        Useful for unit testing or restarting a trading session.
        """
        self.loss_streak = 0
        self.cooldown_until = 0
        self.trade_timestamps = []
