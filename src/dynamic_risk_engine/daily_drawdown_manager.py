from datetime import datetime
from typing import List, Dict

class DailyDrawdownManager:
    """
    Manages daily drawdown limits for trading strategies.
    when limits are hit, it can trigger alerts or stop trading.
    """
    def __init__(self, daily_drawdown_limit: float):
        """
        :param daily drawdown_limit: Maximum allowed drawdown for the day (in base currency or % of account balance)
        """
        self.daily_drawdown_limit = daily_drawdown_limit
        self.day_pnls : Dict[str, List[float]] = {}  # Maps date to list of daily PnLs
        self.trading_halted: Dict[str, bool] = {}  # Maps date to trading halted status

    def _get_day(self, timestamp: datetime) -> str:
        """
        Get the date string for a given timestamp.
        :param timestamp: datetime object
        :return: Date string in 'YYYY-MM-DD' format
        """
        if isinstance(timestamp, str):
            return timestamp #Already a day string
        return timestamp.strftime('%Y-%m-%d')
    

    def record_pnl(self, timestamp: datetime, pnl: float):
        """
        Record the PnL for a given timestamp.
        :param timestamp: datetime object of the PnL event
        :param pnl: Profit or Loss amount

        """
        day = self._get_day(timestamp)
        if day not in self.day_pnls:
            self.day_pnls[day] = []
        self.day_pnls[day].append(pnl)

        if self.calculate_daily_drawdown(day) < -self.daily_drawdown_limit:
            self.trading_halted[day] = True
            self.alert_trading_halted(day)

    def calculate_daily_drawdown(self, timestamp: datetime) -> float:
        """
        Calculate the total PnL for a given day.
        """
        day = self._get_day(timestamp)
        if day not in self.day_pnls:
            return 0.0
        return sum(self.day_pnls[day])
    
    def alert_trading_halted(self, timestamp: datetime):
        """
        Alert that trading has been halted for the day due to drawdown limit.
        :param day: Date string in 'YYYY-MM-DD' format
        """
        days = self._get_day(timestamp)
        print(f"Trading halted for {days} due to drawdown limit exceeded: {self.daily_drawdown_limit}")

    def is_trading_halted(self, timestamp: datetime) -> bool:
        """
        Check if trading is halted for the given timestamp.
        :param timestamp: datetime object
        :return: True if trading is halted, False otherwise
        """
        day = self._get_day(timestamp)
        return self.trading_halted.get(day, False)
    
    def reset_daily_drawdown(self, timestamp: datetime):
        """
        Reset the daily drawdown records for a new day.
        :param timestamp: datetime object of the reset event
        """
        day = self._get_day(timestamp)
        if day in self.day_pnls:
            del self.day_pnls[day]
        if day in self.trading_halted:
            del self.trading_halted[day]


    def in_drawdown_limit(self, timestamp: datetime) -> bool:
        """
        Check if the current drawdown is within the allowed limit.
        :param timestamp: datetime object of the current state
        :return: True if within limit, False otherwise
        """
        day = self._get_day(timestamp)
        return self.calculate_daily_drawdown(day) >= -self.daily_drawdown_limit