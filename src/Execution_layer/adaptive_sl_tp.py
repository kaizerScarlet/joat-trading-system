# adaptive_sl_tp.py

from typing import Tuple, Optional
import numpy as np
from alpha_scoring.AlphaBlender import AlphaBlender
from market_data.orderbook import OrderBook


class AdaptiveSLTP:
    """
    Adaptive Stop Loss / Take Profit manager.

    High-level behavior:
      - At trade start, set SL and TP using max(ATR_distance, volatility_distance).
      - Updates on every tick (monitor_and_adjust):
          * Moves SL to break-even once the "original risk" profit threshold is reached.
          * After break-even, SL trails price and tightens according to a "trailing gap"
            computed from composite microstructure score, volatility, profit size, and distance to TP.
          * SL never loosens (non-leaking): it can only move toward the current price.
          * TP is dynamic and scales outward when momentum/support is strong.
      - Requires the orderbook object to provide:
          * get_midprice()
          * get_volatility_estimate()
          * get_order_age_score()         -> normalized [0,1]
          * get_cancel_activity_score()   -> normalized [0,1]
          * get_layering_score()          -> normalized [0,1]
    """

    def __init__(
        self,
        atr_window: int = 14,
        base_atr_multiplier: float = 1.5,
        vol_multiplier: float = 2.0,
        min_gap_ticks: float = 0.01,
        max_gap_multiplier: float = 5.0,
        tp_extension_factor: float = 1.5,
    ):
        """
        :param orderbook: OrderBook-like instance (must expose required getters).
        :param atr_window: Number of candles stored for ATR calc.
        :param base_atr_multiplier: Base multiplier for ATR distance.
        :param vol_multiplier: Multiplier for volatility-based distance.
        :param weights: weights for (order_age, cancel_activity, layering) composite. Sum should be ~1.
        :param min_gap_ticks: absolute minimum gap in price units (prevents choking).
        :param max_gap_multiplier: maximum multiple of base distance allowed for gap.
        :param tp_extension_factor: TP distance = current SL distance * tp_extension_factor (keeps asymmetry).
        """
        self.alpha_score = AlphaBlender
        self.ob = OrderBook()
        self.atr_window = atr_window
        self.base_atr_multiplier = base_atr_multiplier
        self.vol_multiplier = vol_multiplier

        # gap bounds & tp factor
        self.min_gap_ticks = min_gap_ticks
        self.max_gap_multiplier = max_gap_multiplier
        self.tp_extension_factor = tp_extension_factor

        # candle buffers for ATR
        self.highs = []
        self.lows = []
        self.closes = []

        # trade state
        self.in_trade: bool = False
        self.side: Optional[str] = None  # 'bid' or 'ask'
        self.entry_price: Optional[float] = None
        self.stop_loss: Optional[float] = None
        self.take_profit: Optional[float] = None

        # store original initial risk distance for break-even checks
        self.original_risk: Optional[float] = None

    # --------------------------
    # Market data helpers
    # --------------------------
    def update_candlestick(self, high: float, low: float, close: float) -> None:
        """Add OHLC candle for ATR calculation; keep fixed-length history."""
        self.highs.append(high)
        self.lows.append(low)
        self.closes.append(close)
        if len(self.highs) > self.atr_window:
            self.highs.pop(0); self.lows.pop(0); self.closes.pop(0)

    def _calculate_atr(self) -> float:
        """Return ATR computed from stored candles. Returns 0.0 if insufficient data."""
        if len(self.closes) < 2:
            return 0.0
        trs = []
        for i in range(1, len(self.closes)):
            tr = max(
                self.highs[i] - self.lows[i],
                abs(self.highs[i] - self.closes[i-1]),
                abs(self.lows[i] - self.closes[i-1]),
            )
            trs.append(tr)
        return float(np.mean(trs)) if trs else 0.0

    # --------------------------
    # Composite microstructure score
    # --------------------------
    def _compute_composite_score(self) -> float:
        """
        Compute weighted composite score from orderbook-provided metrics.
        Each underlying metric MUST be normalized 0..1 by the orderbook implementation.
        Returns value in [0,1].
        """

        alpha = self.alpha_score.compute_alpha_score()
        score = alpha.get(self.side, 0.0)

        return score
    

    # --------------------------
    # Start / stop trade flow
    # --------------------------
    def start_trade(self, side: str) -> Tuple[Optional[float], Optional[float]]:
        """
        Enter trade: set entry price, initial SL and TP using the original ATR+vol distance logic.
        :param side: 'bid' for long, 'ask' for short.
        """
        mid = float(self.ob.get_midprice())
        if mid == 0.0:
            raise ValueError("Midprice unavailable (0.0) when attempting to start trade")

        self.side = side
        self.in_trade = True
        self.entry_price = mid

        atr = self._calculate_atr()
        vol_est = float(self.ob.get_volatility_estimate())

        atr_distance = atr * self.base_atr_multiplier
        vol_distance = mid * vol_est * self.vol_multiplier
        base_distance = max(atr_distance, vol_distance, self.min_gap_ticks)

        # initial stop and tp
        if side == "bid":
            self.stop_loss = round(self.entry_price - base_distance, 8)
            self.take_profit = round(self.entry_price + base_distance, 8)
        elif side == "ask":
            self.stop_loss = round(self.entry_price + base_distance, 8)
            self.take_profit = round(self.entry_price - base_distance, 8)
        else:
            raise ValueError("Side must be 'bid' or 'ask'")

        self.original_risk = abs(self.entry_price - self.stop_loss)

        return self.stop_loss, self.take_profit

    def stop_trade(self) -> None:
        """Clear current trade state."""
        self.in_trade = False
        self.side = None
        self.entry_price = None
        self.stop_loss = None
        self.take_profit = None
        self.original_risk = None

    # --------------------------
    # Trailing gap computation
    # --------------------------
    def _compute_trailing_gap(self, composite_score: float, current_price: float) -> float:
        """
        Compute trailing gap (distance from price to SL) using:
          - base_distance (ATR/vol)
          - composite_score: higher => market more stable/supportive => gap can be wider
          - profit_factor: bigger profit => allow faster tightening
          - proximity_to_tp: if close to TP, tighten more aggressively
        Returns the gap (positive number).
        """

        atr = self._calculate_atr()
        vol_est = float(self.ob.get_volatility_estimate())

        # base distance using current price (so it adapts on each tick)
        atr_distance = atr * self.base_atr_multiplier
        vol_distance = current_price * vol_est * self.vol_multiplier
        base_distance = max(atr_distance, vol_distance, self.min_gap_ticks)

        # Composite transforms: composite in [0,1]. Interpret:
        #   composite ~1 -> stable/supportive -> allow wider gap (less choke)
        #   composite ~0 -> unstable -> gap should be tighter (protect quickly)
        # We'll map composite -> factor in range [0.5, 1.5] (tunable)
        composite_factor = 0.5 + self._compute_composite_score()         # [0.5, 1.5]

        # Profit factor: how far price is from entry relative to original risk.
        profit_distance = 0.0
        if self.entry_price is not None:
            if self.side == "bid":
                profit_distance = max(0.0, current_price - self.entry_price)
            else:
                profit_distance = max(0.0, self.entry_price - current_price)

        # if we know original_risk, compute profit_ratio (0 at entry -> larger when deeper in profit)
        profit_ratio = 0.0
        if self.original_risk and self.original_risk > 0:
            profit_ratio = profit_distance / self.original_risk

        # Profit-tightening factor: deeper profits -> more aggressive tightening
        # map profit_ratio to [1.0, 0.3] multiplier, i.e., deeper profit => smaller multiplier (tighter)
        profit_factor = max(0.3, 1.0 - 0.35 * min(profit_ratio, 3.0))

        # Distance to TP: if close to TP, tighten further
        distance_to_tp = abs(self.take_profit - current_price) if self.take_profit is not None else np.inf
        # if distance_to_tp < base_distance*1.5 -> scale to tighten
        if distance_to_tp < base_distance * 1.5:
            proximity_factor = 0.7  # tighten more
        else:
            proximity_factor = 1.0  # normal

        # Combine the factors multiplicatively
        gap = base_distance * composite_factor * profit_factor * proximity_factor

        # enforce min gap and max gap (max relative to base_distance)
        max_allowed = base_distance * self.max_gap_multiplier
        gap = max(self.min_gap_ticks, min(gap, max_allowed))
        return float(gap)

    # --------------------------
    # Monitor / adjust (call on every tick)
    # --------------------------
    def monitor_and_adjust(self) -> None:
        """
        Call this function on every tick (or whenever midprice/ob metrics update).
        It will:
          - move SL to break-even once original_risk is achieved
          - compute trailing gap and update SL (only tighten; never loosen)
          - update TP dynamically (extend outward when momentum/support strong)
        """
        if not self.in_trade:
            return

        current_price = float(self.ob.get_midprice())
        if current_price == 0.0:
            return  # can't act without valid price

        composite = self._compute_composite_score()

        # 1) Break-even: if price moved by at least original_risk, move SL to entry
        if self.original_risk is not None and self.entry_price is not None:
            if self.side == "bid" and current_price >= self.entry_price + self.original_risk:
                # move SL to entry (profit protected)
                self.stop_loss = max(self.stop_loss, round(self.entry_price, 8))
            elif self.side == "ask" and current_price <= self.entry_price - self.original_risk:
                self.stop_loss = min(self.stop_loss, round(self.entry_price, 8))

        # 2) Compute the desired trailing gap and propose new SL based on it
        gap = self._compute_trailing_gap(composite, current_price)

        if self.side == "bid":
            proposed_sl = round(current_price - gap, 8)
            # tighten only (never loosen)
            if self.stop_loss is None:
                self.stop_loss = proposed_sl
            else:
                self.stop_loss = round(max(self.stop_loss, proposed_sl), 8)

            # protect ordering: SL must be < TP
            if self.take_profit is not None and self.stop_loss >= self.take_profit:
                # snap SL slightly below TP
                self.stop_loss = round(self.take_profit - self.min_gap_ticks, 8)

        else:  # 'ask' short
            proposed_sl = round(current_price + gap, 8)
            if self.stop_loss is None:
                self.stop_loss = proposed_sl
            else:
                # for shorts we only tighten (make stop lower), i.e., move stop closer to price: min()
                self.stop_loss = round(min(self.stop_loss, proposed_sl), 8)

            # ordering: SL must be > TP for shorts
            if self.take_profit is not None and self.stop_loss <= self.take_profit:
                self.stop_loss = round(self.take_profit + self.min_gap_ticks, 8)

        # 3) Dynamic TP: extend TP outward based on (current SL distance) * tp_extension_factor
        if self.stop_loss is not None and self.entry_price is not None:
            sl_dist = abs(current_price - self.stop_loss)
            # choose a conservative baseline if sl_dist is tiny (avoid degenerate TP)
            baseline = max(sl_dist, max(1e-8, abs(self.entry_price - self.stop_loss)))
            if self.side == "bid":
                new_tp = round(current_price + (baseline * self.tp_extension_factor), 8)
                # never move TP inward below current TP unless you want to lock smaller target — we will allow outward-only
                if self.take_profit is None:
                    self.take_profit = new_tp
                else:
                    # allow TP to move outward only
                    self.take_profit = round(max(self.take_profit, new_tp), 8)

            else:
                new_tp = round(current_price - (baseline * self.tp_extension_factor), 8)
                if self.take_profit is None:
                    self.take_profit = new_tp
                else:
                    self.take_profit = round(min(self.take_profit, new_tp), 8)

            # ensure ordering after TP update
            if self.side == "bid" and self.stop_loss >= self.take_profit:
                self.stop_loss = round(self.take_profit - self.min_gap_ticks, 8)
            if self.side == "ask" and self.stop_loss <= self.take_profit:
                self.stop_loss = round(self.take_profit + self.min_gap_ticks, 8)

    # --------------------------
    # Accessors
    # --------------------------
    def get_sl_tp(self) -> Tuple[Optional[float], Optional[float]]:
        """Return (stop_loss, take_profit) rounded for convenience."""
        if self.stop_loss is None or self.take_profit is None:
            return self.stop_loss, self.take_profit
        return round(self.stop_loss, 8), round(self.take_profit, 8)

    # --------------------------
    # Utility: inspector for debug
    # --------------------------
    def debug_state(self) -> dict:
        """Return a snapshot of internal state for logging/inspection."""
        return {
            "in_trade": self.in_trade,
            "side": self.side,
            "entry_price": self.entry_price,
            "stop_loss": self.stop_loss,
            "take_profit": self.take_profit,
            "original_risk": self.original_risk,
            "atr": self._calculate_atr(),
            "composite_score": self._compute_composite_score(),
            "midprice": float(self.ob.get_midprice()),
        }

