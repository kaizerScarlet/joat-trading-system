#This Throttle manager is designed to help my execution stay compliant with Binance hard limits
# ML Limits, and WAF Rules
#While adaptive throttling based on system load and recent trade behaviour

import time
from typing import List, Tuple
from collections import deque
import asyncio
from dynamic_risk_engine.cognitive_market_regime_classifier_protocol import CognitiveMarketRegimeClassifierProtocol, MarketRegime 
from dynamic_risk_engine.signal_confidence_calibrator_protocol import SignalConfidenceCalibratorProtocol
from cancel_window.simple_cancel_window_protocol import CancelWindowProtocol
from market_data.orderbook_protocol import OrderBookProtocol

class ThrottleCooldownManager:
    """
    ThrottleManager enforces hard-limis, machine learning behaviour rules.
    and soft throttling to avoid being banned by Binance (WAF, ML system)

    It tracks order, cancel, and trade events to:
        -Avoid hard bans (e.g.,  100 orders per 10s, 200k/day)
        -Maintain healthy conversion rate (trades/orders + cancels)
        -maintain healthy fill weight (volume traded/ volume ordered)
        -prevent weight-based throttling (6000 request weight/min)
        -Loss Streak for cooldown management
    """
    def __init__(
            self,
            regime_classifier: CognitiveMarketRegimeClassifierProtocol,
            confidence: SignalConfidenceCalibratorProtocol,
            cancel_window: CancelWindowProtocol,
            orderbook: OrderBookProtocol,
            max_losses=3, 
            cooldown_seconds=60,
            max_trades_per_minute=3,

            max_orders_per_10s = 100,
            max_orders_per_day = 200000,
            max_weight_per_minute = 6000,
            min_conversion_rate = 0.05, #5%  of orders must convert
            min_fill_weight = 0.05, #5%  of volume must fill

        
            
            ):
        """
        Initialize the throttle cooldown manager with configured thresholds

        Args:
            max_orders_per_10s (int): max orders allowed in any 10 second window.
            max_orders_per_day (int): Max allowed order per 24 hours.
            max_weight_per_minute (int): Max request weight allowed per 60 seconds.
            min_conversion_rate (float): minimum ratio of trades to (order + cancels).
            min_fill_weight (float): Minimum Ratio of filled volume to ordered volume.
        
        :param max_losses: Maximum number of consecutive losing trades allowed before cooldown is triggered.
        :param cooldown_seconds: Time (in seconds) for which trading is paused after hitting max_losses.
        :param max_trades_per_minute: Limit to prevent excessive trading within a short time window.
        """
        #Cooldown control
        self.max_losses = max_losses
        self.cooldown_seconds = cooldown_seconds
        self.max_trades_per_minute = max_trades_per_minute
        self.loss_streak = 0  # Tracks consecutive losses
        self.cooldown_until = 0  # Timestamp until which trading is paused

        #Event Tracking for limits
        self.order_timestamps = deque()
        self.cancel_timestamps = deque()
        self.trade_timestamps = deque()
        self.minute_weights = deque()

        self.trade_timestamps = []

        #Volume metrics
        self.volume_traded = 0.0
        self.order_volume_total = 0.0

        #Limit Thresholds
        self.max_orders_per_10s = max_orders_per_10s
        self.max_orders_per_day = max_orders_per_day
        self.max_weight_per_minute = max_weight_per_minute
        self.min_conversion_rate = min_conversion_rate
        self.min_fill_weight = min_fill_weight


        #Counters and Resets
        self.daily_order_count = 0
        self.last_reset = time.time()

        self.confidence = confidence
        self.cancel_window = cancel_window
        self.orderbook = orderbook

        #Regime Classifier (for potential adaptive throttling)
        self.regime_classifier = regime_classifier
        
#
#   Cooldown and Loss Streak Control
#

    def register_trade_result(self, pnl: float):
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
            if self.cooldown_until != 0 and now >= self.cooldown_until:
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
        now = time.time()
        self.trade_timestamps = deque([t for t in self.trade_timestamps if t > now - 60])

    def reset(self):
        """
        Completely reset the manager’s internal state.
        
        Useful for unit testing or restarting a trading session.
        """
        self.loss_streak = 0
        self.cooldown_until = 0
        self.trade_timestamps = deque()


    def _cleanup(self):
        """
        Remove outdated event timestamps and reset daily counters every 24 hours
        """
        now = time.time()
        #Remove timestamps older than 10 seconds
        while self.order_timestamps and now - self.order_timestamps[0] > 10:
            self.order_timestamps.popleft()
        while self.order_timestamps and now - self.order_timestamps[0] > 10:
            self.order_timestamps.popleft()
        while self.trade_timestamps and now - self.trade_timestamps[0] > 60:
            self.trade_timestamps.popleft()


        # Reset Daily count every 24h
        if now - self.last_reset > 86400:
            self.daily_order_count = 0
            self.volume_traded = 0.0
            self.order_volume_total = 0.0
            self.last_reset = now 

    
    def record_order(self, volume: float=1.0, weight: int = 1):
        """
        Log an Order submission.
        Args:
            volume (float): size of the order (used for fill weight),
            weight (int): API weight (ususally 1 for most REST calls)
        """
        self._cleanup()
        self.order_timestamps.append(time.time())
        self.order_volume_total += volume
        self.daily_order_count += 1
        self.minute_weights.append((time.time(), weight))


    def record_cancel(self):
        """
        Log an order cancel event.
        """
        self._cleanup()
        self.cancel_timestamps.append(time.time())


    def record_fill(self, volume: float):
        """
        Log a Trade fill
        Args:
            volume (float): Volume filled
        """
        self._cleanup()
        self.trade_timestamps.append(time.time())
        self.volume_traded += volume

    def get_conversion_rate(self):
        """
        Calculate the coversion rate: Trades / (orders + cancels).
        Returns: 
                float: conversion rate (0.0 if no activity).
        """
        total_actions = len(self.order_timestamps) + len(self.cancel_timestamps)
        return len(self.trade_timestamps) / total_actions if total_actions > 0 else 0.0

    def get_fill_weight(self):
        """
        Calculate the fill weight: total filled volume / total ordered volume.
        Returns:
            float: fill weight (0.0 if no orders)
        """
        return self.volume_traded / self.order_volume_total if self.order_volume_total > 0 else 0.0

    def get_weight_per_minute(self):
        """
        Calculate API request weight over the past 60 seconds
        Returns:
            float: Total weight used
        """
        now = time.time()
        self.minute_weights = deque([(t, w) for t,w in self.minute_weights if now - t <= 60])
        return sum(w for _,w in self.minute_weights)
    
    def is_throttled(self) -> bool:
        """
        Binance rules
        Check if the system is currently throttled based on all rule types.
        Returns:
            bool: True if any throttle condition is violated
        """
        self._cleanup()
        reasons = []

        overlay = self.regime_classifier.get_behavioral_overlay()
        regime = self.regime_classifier.get_current_regime()

        if overlay == "LIQUIDITY_VACUUM":
            reasons.append("Behavioral throttle: LIQUIDITY_VACUUM")
        if overlay == "CHOPPY_NOISE":
            reasons.append("Behavioral throttle: CHOPPY_NOISE")

        if len(self.order_timestamps) > self.max_orders_per_10s:
            reasons.append("Order Exceed 10s limit")
        if self.daily_order_count > self.max_orders_per_day:
            reasons.append("Daily order count exceeded")
        if self.get_weight_per_minute() > self.max_weight_per_minute:
            reasons.append("Weight per minute Exceeded")
        if self.get_conversion_rate() < self.min_conversion_rate:
            reasons.append("Low conversion Rate")
        if self.get_fill_weight() < self.min_fill_weight:
            reasons.append("Low fill weight")


        if reasons:
            print(f"[THROTTLE ACTIVE] Regime={regime}, Overlay={overlay}, Reasons={reasons}")

        return len(reasons) > 0
    




    def get_diagnostic(self) -> dict:
        """
        Return a snapshot of the current system for debugging.
        Returns:
            dict: Diagnostics including counts, rations, and flags
        """

        return{
            "orders_last_10s": len(self.order_timestamps),
            "cancels_last_10s": len(self.cancel_timestamps),
            "trades_last_min": len(self.trade_timestamps),
            "conversion_rate": round(self.get_conversion_rate(), 4),
            "fill_weight": round(self.get_fill_weight(), 4),
            "weight_per_minute": round(self.get_weight_per_minute(), 2),
            "daily_order_count": self.daily_order_count,
            "loss_streak": self.loss_streak,
            "in_cooldown": self.is_in_cooldown(),
            "overlay": self.regime_classifier.get_behavioral_overlay(),
            "regime": self.regime_classifier.get_current_regime(),
        }


class AsyncThrottleCooldownManager(ThrottleCooldownManager):
    """
    Extends the existing Throttle Manager with async-safe event registration.
    If using multi-threading or multi-process, consider proper locking.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        #Use an asyncio.Lock for concurrency safety (if needed)
        self._lock = asyncio.Lock()

    async def record_order_async(self, volume: float = 1.0, weight: int = 1):
        async with self._lock:
            self.record_order(volume, weight)
    
    async def record_cancel_async(self):
        async with self._lock:
            self.record_cancel()

    async def record_fill_async(self, volume:float):
        async with self._lock:
            self.record_fill(volume)

    async def register_trade_result(self, pnl: float):
        async with self._lock:
            self.register_trade_result(pnl)




    