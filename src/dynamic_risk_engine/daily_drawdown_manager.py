from datetime import datetime
from typing import List, Dict
from dynamic_risk_engine.cognitive_market_regime_classifier_protocol import CognitiveMarketRegimeClassifierProtocol, MarketRegime
from Execution_layer.binance_adapter_protocol import BinanceExecutionAdapterProtocol

class DailyDrawdownManager:
    """
    Manages daily drawdown limits for trading strategies.
    when limits are hit, it can trigger alerts or stop trading.
    """
    def __init__(self, daily_drawdown_limit: float, binance_adapter: BinanceExecutionAdapterProtocol, regime_classifier: CognitiveMarketRegimeClassifierProtocol):
        """
        :param daily drawdown_limit: Maximum allowed drawdown for the day (in base currency or % of account balance)
        """
        self.account_balance = binance_adapter
        self.regime_classifier = regime_classifier
        self._drawdown_ratio = daily_drawdown_limit # Store raw ratio
        self.daily_drawdown_limit = None # Will be set later
        self.day_pnls : Dict[str, List[float]] = {}  # Maps date to list of daily PnLs
        self.trading_halted: Dict[str, bool] = {}  # Maps date to trading halted status

    async def initialize(self):
        """
        Asynchronously initializes the drawdown limit based on current account balance.
        Must be called before using drawdown logic
        """
        balance = await self.account_balance.get_account()
        self.daily_drawdown_limit = -abs(self._drawdown_ratio * balance)

    def _get_day(self, timestamp: datetime) -> str:
        """
        Get the date string for a given timestamp.
        :param timestamp: datetime object
        :return: Date string in 'YYYY-MM-DD' format
        """
        if isinstance(timestamp, str):
            return timestamp #Already a day string
        return timestamp.strftime('%Y-%m-%d')
    
    def get_daily_drawdown_limit(self):
        regime = self.regime_classifier.get_current_regime()
        overlay = self.regime_classifier.get_behavioral_overlay()

        regime_weights = {
            MarketRegime.TRENDING: 1.0,
            MarketRegime.MEAN_REVERTING: 0.9,
            MarketRegime.VOLATILE: 1.3,
            MarketRegime.ILLIQUID: 1.2,
            MarketRegime.UNKNOWN: 1.0

        }

        overlay_boost = {
            "LIQUIDITY_VACUUM": 1.4,
            "AGGRESSIVE_SWEEP_UP": 1.3,
            "AGGRESSIVE_SWEEP_DOWN": 1.3,
            "REVERSION_TRAP_UP": 1.1,
            "REVERSION_TRAP_DOWN": 1.1,
            "PASSIVE_FADE": 1.2,
            "CROSS_SIDE_TENSION": 1.1,
            "LAYER_WIPE": 1.4,
            "CANCEL_DENSITY_SPIKE": 1.3,
            "MOMENTUM_EXHAUSTION": 1.2,
            "CHOPPY_NOISE": 0.8,
            "NORMAL": 1.0
        }

        regime_weight = regime_weights.get(regime, 1.0)
        overlay_factor = overlay_boost.get(overlay, 1.0)

        return self.daily_drawdown_limit * regime_weight * overlay_factor
        
    

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

        modulated_limit = self.get_daily_drawdown_limit()
        if self.calculate_daily_drawdown(timestamp) <= modulated_limit:
            self.trading_halted[day] = True
            self.alert_trading_halted(day)

    def calculate_daily_drawdown(self, timestamp: datetime) -> float:
        """
        Calculate the maximum drawdown for given day using peak-to-through logic.

        Drawdown is defined as the largest drop from a cumulative profit peak to trough.
        This method captures intra-day volatility and penalizes deep losses even if recovery occurs later.

        Args:
            timestamp (datetime): Timestamp representing the day to evaluate.
        
        Returns:
            Float: maximum drawdown for the day (negative value if loss occurred, zero otherwise).
        """
        day = self._get_day(timestamp)
        pnls = self.day_pnls.get(day, [])

        # Build cumlative PnL curve
        cummulative = [sum(pnls[:i + 1]) for i in range(len(pnls))]

        #Identify the peak and trough in the curve
        peak = max(cummulative, default=0.0)
        trough = min(cummulative, default=0.0)

        #Drawdown is the drop from peak to trough
        drawdown = trough - peak
        return drawdown
    
    def alert_trading_halted(self, timestamp: datetime):
        """
        Alert that trading has been halted for the day due to drawdown limit.
        :param day: Date string in 'YYYY-MM-DD' format
        """
        days = self._get_day(timestamp)
        regime = self.regime_classifier.get_current_regime()
        overlay = self.regime_classifier.get_behavioral_overlay()
        print(f"Trading halted for {days} | Regime : {regime} | overlay : {overlay} due to drawdown limit exceeded: {self.daily_drawdown_limit}")

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
        return not self.is_trading_halted(timestamp)
    

    def get_status(self, timestamp: datetime) -> Dict[str, any]:
        """
        Get the current status of the daily drawdown manager.
        :param timestamp: datetime object
        :return: Dictionary with current drawdown , trading status, drawdown limit, PnL events for the day, cumulative PnL for the day
        """
        day = self._get_day(timestamp)
        return {
            "day": self._get_day(timestamp),
            "current_drawdown": self.calculate_daily_drawdown(timestamp),
            "trading_halted": self.is_trading_halted(timestamp),
            "daily_drawdown_limit": self.daily_drawdown_limit,
            "pnl_events": len(self.day_pnls.get(day,[])),
            "cumulative_pnl": sum(self.day_pnls.get(day, []))

        }
    
    def get_drawdown_curve(self, timestamp: datetime) -> List[float]:
        """
        Returns the cumulative PnL curve for the given day to visualize drawdown evolution.
        Args:
            timestamp (datetime): Timestamp representing the day to inspect.

        Returns:
            List[float]: Cumulative PnL values at each step of the day.
        """
        day = self._get_day(timestamp)
        pnls = self.day_pnls.get(day, [])
        return [sum(pnls[:i + 1]) for i in range(len(pnls))]
    
    def get_debug_view(self, timestamp: datetime) -> Dict[str, any]:
        """
        Returns a detailed debug snapshot of the drawdown manager's state for the given day.
        Includes drawdown metrics, trading status, volatility, and curve evolution.
        """
        day = self._get_day(timestamp)
        pnls = self.day_pnls.get(day, [])
        curve = self.get_drawdown_curve(timestamp)
        drawdown = self.calculate_daily_drawdown(timestamp)
        peak = max(curve, default=0.0)
        trough = min(curve, default=0.0)
        volatility = round((max(pnls) - min(pnls)) if pnls else 0.0, 4)

        regime = self.regime_classifier.get_current_regime()
        overlay = self.regime_classifier.get_behavioral_overlay()
        
        if "_" in overlay:
            overlay_type, overlay_direction = overlay.split("_", 1)
        else:
            overlay_type, overlay_direction = overlay, "NEUTRAL"


        return {
            "day": day,
            "regime": regime,
            "overlay": overlay,
            "overlay_type": overlay_type,
            "overlay_direction": overlay_direction,
            "drawdown_limit": self.daily_drawdown_limit,
            "current_drawdown": round(drawdown, 4),
            "peak_pnl": round(peak, 4),
            "trough_pnl": round(trough, 4),
            "cumulative_pnl": round(sum(pnls), 4),
            "pnl_events": len(pnls),
            "volatility": volatility,
            "trading_halted": self.is_trading_halted(timestamp),
            "drawdown_curve": curve[-5:],  # last 5 points for quick glance
        }

