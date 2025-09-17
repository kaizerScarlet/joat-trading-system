from dynamic_risk_engine.performance_tracker import PerformanceTracker
from dynamic_risk_engine.daily_drawdown_manager import DailyDrawdownManager
from dynamic_risk_engine.signal_confidence_calibrator import SignalConfidenceCalibrator
from dynamic_risk_engine.dynamic_position_sizer import DynamicPositionSizer
from dynamic_risk_engine.throttle_cooldown_manager import ThrottleCooldownManager
from Execution_layer.binance_adapter import BinanceExecutionAdapter
from market_data.orderbook import OrderBook
from dynamic_risk_engine.cognitive_market_regime_classifier import  CognitiveMarketRegimeClassifier, MarketRegime
from cancel_window.simple_cancel_window import SimpleCancelWindow
from datetime import datetime 



class DynamicRiskEngine:
    """
    Master coordinator for all risk and sizing modules.
    Governs whether trades can proceed based on how large they should be
    """

    def __init__(self,daily_drawdown_limit: float):

        """
        :param initial_balance: Starting balance for the risk engine
        :param max_risk_per_trade: Maximum risk allowed per trade as a fraction of the balance
        """
        self.performance_tracker = PerformanceTracker()
        self.daily_drawdown_manager = DailyDrawdownManager(daily_drawdown_limit)  # 25% daily drawdown limit
        self.signal_confidence_calibrator = SignalConfidenceCalibrator()
        self.dynamic_position_sizer = DynamicPositionSizer()
        self.throttle_cooldown_manager = ThrottleCooldownManager()
        self.binance_adapter = BinanceExecutionAdapter()

        self.orderbook = OrderBook()
        self.cancel_window = SimpleCancelWindow()
        self.market_regime_classifier =  CognitiveMarketRegimeClassifier(
            orderbook=self.orderbook,
            signal_calibrator=self.signal_confidence_calibrator,
            cancel_window=self.cancel_window
        )

        self.current_regime = MarketRegime.UNKNOWN

        self.initial_balance = None #Will be set asynchronously
        self.max_risk_per_trade = None

    async def initialize(self):
        """
        Initialize the engine with the current account balance.
        """
        await self.dynamic_position_sizer.initialize()

        #Explicitly initialize drawdown manager to set drawdown_limit
        await self.daily_drawdown_manager.initialize()

        self.initial_balance = await self.binance_adapter.get_account_balance()
        self.max_risk_per_trade = self.dynamic_position_sizer.max_risk_per_trade

    def update_market_regime(self):
        self.current_regime = self.market_regime_classifier.update_regime()

    def can_trade(self) -> bool:
        """
        Determine if trading is currently allowed  on the risk engine state.
        :return: True if trading is allowed, False otherwise
        """
        return (
             self.daily_drawdown_manager.in_drawdown_limit(datetime.now()) and
             self.throttle_cooldown_manager.can_trade()

        )
    

    def get_risk_for_trade(self) -> float:
        return self.max_risk_per_trade

    
    async def get_position_size(self, stop_loss_distance: float) -> float:
        """
        Get optimal position size based on current edge and risk conditions.
        :param stop_loss_distnace: price units from entry to stop loss
        :return: Calculated position size in units
        """

        confidence = self.signal_confidence_calibrator.get_current_confidence()


        base_size = await self.dynamic_position_sizer.calculate_position_size(
            stop_loss_distance=stop_loss_distance
        )

        #Regime-aware throttle
        if self.current_regime == MarketRegime.VOLATILE:
            return base_size * 0.7
        elif self.current_regime == MarketRegime.ILLIQUID:
            return base_size * 0.5
        elif self.current_regime == MarketRegime.TRENDING and confidence > 0.7:
            return base_size * 1.1
        return base_size
    

    def register_trade(self, pnl:float, risk: float, reward: float, signal_id: str, was_correct: bool, metadata: dict = None):
        """
        Register a trade with its PnL and risk parameters.
        :param pnl: Profit or Loss from the trade
        :param risk: Risk amount for the trade
        :param reward: Reward amount for the trade
        :param signal_id: Unique identifier for the trading signal
        :param was_correct: Whether the signal was correct (True) or incorrect (False)
        :param metadata: Optional metadata about the trade
        """
        self.performance_tracker.record_trade(pnl, risk, reward, metadata)
        self.daily_drawdown_manager.record_pnl(datetime.now(), pnl)
        self.signal_confidence_calibrator.update_signal_result(
            signal_id=signal_id,
            was_correct=was_correct
        )
        self.throttle_cooldown_manager.register_trade_result(pnl)

    def get_risk_curve_value(self) -> float:
        confidence = self.signal_confidence_calibrator.get_current_confidence()
        risk_curve = lambda c: 0.005 + (c ** 2) * 0.045
        return round(risk_curve(confidence), 4)

    async def reset(self):
        """
        Reset all internal state (e.g., start of day
        )"""

        self.performance_tracker.reset()
        self.daily_drawdown_manager.reset_daily_drawdown(datetime.now())
        self.signal_confidence_calibrator.reset()

        self.dynamic_position_sizer = DynamicPositionSizer()
        self.dynamic_position_sizer.max_risk_per_trade = self.max_risk_per_trade
        self.dynamic_position_sizer.account_balance = self.binance_adapter
        self.dynamic_position_sizer.drawdown.account_balance = self.binance_adapter
        await self.dynamic_position_sizer.initialize()

        self.daily_drawdown_manager.account_balance = self.binance_adapter
        await self.daily_drawdown_manager.initialize()

        self.throttle_cooldown_manager =  ThrottleCooldownManager()
        self.current_regime = MarketRegime.UNKNOWN


    async def get_diagnostic(self) -> dict:
        """
        Return full risk risk enigine diagnostic state.
        Usefule for debugging and monitoring, or audit logs
        """

        return {

            'can_trade': self.can_trade(),
            'position_size_for_1_sl': await self.get_position_size(stop_loss_distance=1.0),
            'current_confidence': self.signal_confidence_calibrator.get_current_confidence(),
            'current_win_rate': round(self.performance_tracker.win_rate(), 4),
            'average_rrr': round(self.performance_tracker.average_rrr(), 4),
            'profit_factor': round(self.performance_tracker.profit_factor(), 4),
            'drawdown_triggered': self.daily_drawdown_manager.is_trading_halted(datetime.now()),
            'cooldown_active': self.throttle_cooldown_manager.is_in_cooldown(),
            'equity_curve': self.performance_tracker.get_equity_curve(),
            'market_regime': self.current_regime.value,
            'regime_duration_seconds': self.market_regime_classifier.get_regime_duration_seconds(),
            'regime_stability': self.market_regime_classifier.get_regime_stability(),
            'regime_history_tail': [r.value for r in list(self.market_regime_classifier.regime_history)[-5:]],
            'confidence_breakdown': self.signal_confidence_calibrator.get_confidence_breakdown(),
            'risk_curve_value': self.get_risk_curve_value(),
            

        }
    

