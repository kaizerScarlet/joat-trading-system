from typing import List, Dict, Optional
import time

class PerformanceTracker:
    
    """
    Tracks trading performance metrics such as win rate, RR,  profit factor, equity curve
    """
    def  __init__(self):
        self.trades : List[Dict] = []
        self.equity_curve: List[float] = []
        self.balance: float = 0.0
        self.sl_tp_history = []
        self.slippage_fee = []
        self.fee = []
        self.trade_latency = []
        self.fill_probability = []


    def record_trade(self,order_id: str, pnl: float, risk: float, reward: float, metadata: Optional[Dict] = None):
        """
        Record a trade outcome

        :param pnl: Profit or Loss of the trade
        :param risk: The risk taken in the trade (used to calculate RRR)
        :param reward: The reward gained from the trade (used to calculate RRR)
        :param metadata: Optional metadata about the trade
        """

        is_win = pnl > 0

        trade = {
            'order_id': order_id,
            'pnl': pnl,
            'risk': risk,
            'reward': reward,
            'rrr': (reward / risk) if risk else 0.0,
            'win': is_win,
            'metadata': metadata or {}
        }

        self.trades.append(trade)
        self.balance += pnl
        self.equity_curve.append(self.balance)


    def win_rate(self) -> float:
        """
        Calculate the win rate of trades
        """
        if not self.trades:
            return 0.0
        wins = sum(1 for t in self.trades if t.get('win', False))
        return wins / len(self.trades)
    
    def average_rrr(self) -> float:
        """
        returns the average risk-reward ratio of trades
        """
        rrr = [t['rrr'] for t in self.trades if t['risk'] > 0]
        return sum(rrr) / len(rrr) if rrr else 0.0
    
    def record_sl_tp_drift(self,order_id: str, sl: float, tp: float):
        """
        Record SL/TP evolution for diagnostics.
        You can extend this to log timestamped drift or visualize it later.
        """
        self.sl_tp_history.append({
            "timestamp": time.time(),
            "order_id": order_id,
            "sl": sl,
            "tp": tp
        })

    
    def profit_factor(self) -> float:
        """
        Calculate the profit factor of trades
        """
        gross_profit = sum(t['pnl'] for t in self.trades if t['pnl'] > 0)
        gross_loss = -sum(t['pnl'] for t in self.trades if t['pnl'] < 0)
        return gross_profit / gross_loss if gross_loss > 0 else float('inf')
    
    def get_equity_curve(self) -> List[float]:
        """
        Get the equity curve of the trading strategy
        """
        return self.equity_curve
    
    def record_slippage(self,order_id: str, slippage: float, side: str, qty: float, price: float, symbol: str)-> None:
        """
        Record the on-fill order slippage for trades
        """
        self.slippage_fee.append({
            "order_id": order_id,
            "Slippage_fee": slippage,
            "side": side,
            "size": qty,
            "price": price,
            "symbol": symbol,

        })

    def record_fee(self,order_id: str, fee: float, side: str, qty: float, price: float, symbol: str) -> None:
        """
        Record the on-fill order fee per trade
        """
        self.fee.append({
            "order_id": order_id,
            "Schedule_Fee": fee,
            "side": side,
            "size": qty,
            "price": price,
            "symbol": symbol
        })

    def record_latency(self, order_id: str, latency_ms: float, side: str, qty: float, price: float, symbol: str)-> None:
        """
        Record fill latency on fill per trade
        """
        self.trade_latency.append({
            "order_id": order_id,
            "trade_latency": latency_ms,
            "side": side,
            "size": qty,
            "price": price,
            "symbol": symbol,
        })


    def record_fill_probability(self, order_id: str, fill_probability: float, side: str, qty: float, price: float, symbol: str) -> None:
        """
        Record the fill probability per trade, this is given by the queue model
        """
        self.fill_probability.append({
            "order_id": order_id,
            "fill_probability": fill_probability,
            "side": side,
            "size": qty,
            "price": price,
            "symbol": symbol,
        })


    
    def reset(self):
        """
        Reset the performance tracker
        """
        self.trades = []
        self.equity_curve = []
        self.balance = 0.0
        self.sl_tp_history = []
        self.slippage_fee = []
        self.fee = []
        self.trade_latency = []
        self.fill_probability = []


    def get_summary(self) -> Dict[str, float]:
        """
        Get a summary of performance metrics
        """
        return{
            'total_trades': len(self.trades),
            'win_rate': round(self.win_rate(), 4),
            'average_rrr': round(self.average_rrr(), 4),
            'profit_factor': round(self.profit_factor(), 4),
            'final_balance': round(self.balance, 4),
        }
    
    def get_diagnostics(self) -> Dict[str, float]:
        """This gives you a snapshot of behavioral metrics:"""
        return {
            "total_trades": len(self.trades),
            "win_rate": self.win_rate(),
            "average_rrr": self.average_rrr(),
            "profit_factor": self.profit_factor(),
            "final_balance": self.balance,
            "slippage_events": len(self.slippage_fee),
            "fee_events": len(self.fee),
            "latency_events": len(self.trade_latency),
            "fill_probability_events": len(self.fill_probability),
            "sl_tp_drift_events": len(self.sl_tp_history)
        }
    
    def get_last_trade(self) -> Optional[Dict]:
        return self.trades[-1] if self.trades else None



