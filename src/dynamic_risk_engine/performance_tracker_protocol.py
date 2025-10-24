from typing import Protocol, Dict, List, Any, Optional, runtime_checkable



@runtime_checkable
class PerformanceTrackerProtocol(Protocol):
    trades: List[Dict]
    get_equity_curve: List[float]
    balance: float
    sl_tp_history: List[Dict[str, Any]]
    slippage_fee: List[Dict[str, Any]] 
    fee: List[Dict[str, Any]] 
    trade_latency: List[Dict[str, Any]] 
    fill_probability: List[Dict[str, Any]]  

    def record_trade(self, order_id: str, pnl: float, risk: float, reward: float, metadata: Optional[Dict] = None) -> None:
        """Records a trade outcome including PnL, risk, reward, and metadata."""
        ...

    def win_rate(self) -> float:
        """Returns the current win rate across all recorded trades."""
        ...

    def average_rrr(self) -> float:
        """Returns the average risk-reward ratio across trades."""
        ...

    def profit_factor(self) -> float:
        """Returns the profit factor (gross profit / gross loss)."""
        ...

    def get_equity_curve(self) -> List[float]:
        """Returns the equity curve of cumulative PnL over time."""
        ...

    def record_sl_tp_drift(self, order_id: str, sl: float, tp: float) -> None:
        """Records SL/TP drift for diagnostics."""
        ...

    def record_slippage(self, order_id: str, slippage: float, side: str, qty: float, price: float, symbol: str) -> None:
        """Records slippage fee per trade."""
        ...

    def record_fee(self, order_id: str, fee: float, side: str, qty: float, price: float, symbol: str) -> None:
        """Records execution fee per trade."""
        ...

    def record_latency(self, order_id: str, latency_ms: float, side: str, qty: float, price: float, symbol: str) -> None:
        """Records latency per trade fill."""
        ...

    def record_fill_probability(self, order_id: str, fill_probability: float, side: str, qty: float, price: float, symbol: str) -> None:
        """Records fill probability per trade."""
        ...

    def reset(self) -> None:
        """Resets all performance metrics and internal state."""
        ...

    def get_summary(self) -> Dict[str, float]:
        """Returns a summary of key performance metrics."""
        ...

    def get_diagnostics(self) -> Dict[str, float]:
        """This gives you a snapshot of behavioral metrics:"""
        ...

    def get_last_trade(self) -> Optional[Dict]:
        """This helps trace recetn behaviour in tests or logs"""
        ...
