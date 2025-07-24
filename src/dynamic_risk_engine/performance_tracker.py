from typing import List, Dict, Optional

class PerformanceTracker:
    
    """
    Tracks trading performance metrics such as win rate, RR,  profit factor, equity curve
    """
    def  __init__(self):
        self.trades : List[Dict] = []
        self.equity_curve: List[float] = []
        self.balance: float = 0.0

    def record_trade(self, pnl: float, risk: float, reward: float, metadata: Optional[Dict] = None):
        """
        Record a trade outcome

        :param pnl: Profit or Loss of the trade
        :param risk: The risk taken in the trade (used to calculate RRR)
        :param reward: The reward gained from the trade (used to calculate RRR)
        :param metadata: Optional metadata about the trade
        """

        is_win = pnl > 0

        trade = {
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
    
    def reset(self):
        """
        Reset the performance tracker
        """
        self.trades = []
        self.equity_curve = []
        self.balance = 0.0

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

