from typing import Protocol, Dict, List, runtime_checkable
from datetime import datetime
from typing import List, Dict
from Execution_layer.binance_adapter_protocol import BinanceExecutionAdapterProtocol


@runtime_checkable
class DailyDrawdownManagerProtocol(Protocol):
    account_balance: BinanceExecutionAdapterProtocol
    _drawdown_ratio: float
    daily_drawdown: None
    day_pnls: Dict[str, List[float]]
    trading_halted: Dict[str, bool]

    async def initialize(self) -> None:
        """Initializes drawdown limit based on current account balance."""
        ...

    def record_pnl(self, timestamp: datetime, pnl: float) -> None:
        """Records a PnL event and halts trading if drawdown exceeds limit."""
        ...

    def calculate_daily_drawdown(self, timestamp: datetime) -> float:
        """Calculates peak-to-trough drawdown for the given day."""
        ...

    def alert_trading_halted(self, timestamp: datetime)-> None:
        """ Alert that trading has been halted for the day due to drawdown limit"""
        ...
        
    def is_trading_halted(self, timestamp: datetime) -> bool:
        """Returns True if trading is halted for the given day."""
        ...

    def reset_daily_drawdown(self, timestamp: datetime) -> None:
        """Resets drawdown records for the given day."""
        ...

    def in_drawdown_limit(self, timestamp: datetime) -> bool:
        """Returns True if current drawdown is within allowed limit."""
        ...

    def get_status(self, timestamp: datetime) -> Dict[str, any]:
        """Returns drawdown status, trading halt flag, limit, and cumulative PnL."""
        ...

    def get_drawdown_curve(self, timestamp: datetime) -> List[float]:
        """Returns cumulative PnL curve for the day to visualize drawdown evolution."""
        ...

    def get_daily_drawdown_limit(self) -> float:
        """Returns the current drawdown limit."""
        ...

    def get_debug_view(self, timestamp: datetime) -> Dict[str, any]:
        """Get Debug view for introspection and debugging"""
        ...
