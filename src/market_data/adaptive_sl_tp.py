from typing import Tuple
import numpy as np
from market_data.orderbook import OrderBook

class AdaptiveSLTP:
    def __init__(self, orderbook: OrderBook, atr_window=14, atr_multiplier=1.5, vol_multiplier=2.0):
        """
        Initialize the adaptive SL/TP manager.
        
        :param orderbook: An instance of your OrderBook class providing market data.
        :param atr_window: Number of periods for ATR calculation.
        :param atr_multiplier: Multiplier for ATR-based SL/TP distance.
        :param vol_multiplier: Multiplier for volatility-based SL/TP distance.
        """
        self.orderbook = orderbook
        self.atr_window = atr_window
        self.atr_multiplier = atr_multiplier
        self.vol_multiplier = vol_multiplier
        
        # Store recent candle data for ATR calculation
        self.highs = []
        self.lows = []
        self.closes = []
        
        # Track current active stop loss, take profit, and entry price
        self.current_sl = None
        self.current_tp = None
        self.entry_price = None
        
        # Side of the current trade ('bid' or 'ask')
        self.current_side = None

    def update_candlestick(self, high: float, low: float, close: float):
        """
        Feed new candle data for ATR calculation.
        Keeps a fixed-length history.
        """
        self.highs.append(high)
        self.lows.append(low)
        self.closes.append(close)
        
        if len(self.highs) > self.atr_window:
            self.highs.pop(0)
            self.lows.pop(0)
            self.closes.pop(0)

    def _calculate_atr(self) -> float:
        """
        Calculate ATR (Average True Range) from stored candle data.
        """
        if len(self.closes) < 2:
            return 0.0

        trs = []
        for i in range(1, len(self.closes)):
            high_low = self.highs[i] - self.lows[i]
            high_close = abs(self.highs[i] - self.closes[i-1])
            low_close = abs(self.lows[i] - self.closes[i-1])
            trs.append(max(high_low, high_close, low_close))

        return np.mean(trs) if trs else 0.0

    def get_adaptive_sl_tp(self, side: str) -> Tuple[float, float]:
        """
        Calculate initial adaptive Stop Loss and Take Profit levels based on ATR and volatility.
        
        :param side: 'bid' for long trades or 'ask' for short trades.
        :return: Tuple (stop_loss, take_profit)
        """
        midprice = self.orderbook.get_midprice()
        if midprice == 0.0:
            raise ValueError("Midprice not available yet")

        atr = self._calculate_atr()
        volatility = self.orderbook.get_volatility_estimate()

        # Calculate distances for SL/TP based on ATR and volatility
        atr_distance = atr * self.atr_multiplier
        vol_distance = midprice * volatility * self.vol_multiplier

        # Use the larger distance for safety margin
        distance = max(atr_distance, vol_distance)

        if side == "bid":
            sl = midprice - distance
            tp = midprice + distance
        elif side == "ask":
            sl = midprice + distance
            tp = midprice - distance
        else:
            raise ValueError("Side must be 'bid' or 'ask'")

        return round(sl, 2), round(tp, 2)

    def set_initial_sl_tp(self, side: str):
        """
        Initialize SL, TP, and entry price when a new trade is taken.
        
        :param side: 'bid' or 'ask'
        """
        self.current_side = side
        self.entry_price = self.orderbook.get_midprice()
        self.current_sl, self.current_tp = self.get_adaptive_sl_tp(side)

    def update_trailing_sl(self):
        """
        Update the trailing stop loss adaptively based on price movements and volatility.
        This should be called continuously or on every new tick/candle.
        """
        if self.current_sl is None or self.entry_price is None or self.current_side is None:
            # No active trade to manage
            return

        current_price = self.orderbook.get_midprice()
        atr = self._calculate_atr()
        volatility = self.orderbook.get_volatility_estimate()

        # Calculate adaptive distance (same logic as initial SL/TP)
        atr_distance = atr * self.atr_multiplier
        vol_distance = current_price * volatility * self.vol_multiplier
        distance = max(atr_distance, vol_distance)

        if self.current_side == "bid":
            # Move SL up if price has moved favorably beyond entry price to lock in profits
            # Move SL never backwards (only tighten or keep)
            new_sl = max(self.current_sl, self.entry_price)

            # Also trail SL behind current price with adaptive distance
            trailing_sl_candidate = current_price - distance

            # Use the tighter SL between current SL and trailing candidate
            self.current_sl = max(new_sl, trailing_sl_candidate)

        elif self.current_side == "ask":
            # For short side, SL moves down to lock in profits or reduce losses
            new_sl = min(self.current_sl, self.entry_price)

            trailing_sl_candidate = current_price + distance
            self.current_sl = min(new_sl, trailing_sl_candidate)

        # Round SL for neatness
        self.current_sl = round(self.current_sl, 2)

        # Ensure SL does not cross TP
        self._ensure_sl_tp_order()

    def update_trailing_tp(self):
        """
        Move take profit dynamically forward as price moves favorably.
        Ensure TP remains beyond SL to avoid crossing.
        """
        if self.current_tp is None or self.entry_price is None or self.current_side is None:
            return

        current_price = self.orderbook.get_midprice()
        atr = self._calculate_atr()
        volatility = self.orderbook.get_volatility_estimate()

        # Use a larger multiplier for TP than SL to allow bigger profit capture
        atr_distance = atr * (self.atr_multiplier * 2)  # example: double ATR multiplier for TP
        vol_distance = current_price * volatility * (self.vol_multiplier * 2)

        distance = max(atr_distance, vol_distance)

        if self.current_side == "bid":
            # TP moves up but must remain above SL
            new_tp = max(self.current_tp, current_price + distance)
            # Prevent TP crossing or going below SL
            if new_tp <= self.current_sl:
                new_tp = self.current_sl + 0.01  # a tiny gap to avoid equality
            self.current_tp = round(new_tp, 2)

        elif self.current_side == "ask":
            new_tp = min(self.current_tp, current_price - distance)
            if new_tp >= self.current_sl:
                new_tp = self.current_sl - 0.01
            self.current_tp = round(new_tp, 2)

        # Ensure SL and TP order is still valid
        self._ensure_sl_tp_order()

    def _ensure_sl_tp_order(self):
        """
        Internal helper to make sure SL and TP do not cross over.
        Adjust SL slightly if necessary.
        """
        if self.current_sl is None or self.current_tp is None:
            return

        if self.current_side == "bid" and self.current_sl >= self.current_tp:
            # Keep SL strictly less than TP
            self.current_sl = round(self.current_tp - 0.01, 2)
        elif self.current_side == "ask" and self.current_sl <= self.current_tp:
            # Keep SL strictly greater than TP
            self.current_sl = round(self.current_tp + 0.01, 2)

    def check_adverse_signal_and_tighten(self, adverse_signal: bool):
        """
        Optionally tighten or close SL if an adverse signal is detected.
        
        :param adverse_signal: Boolean flag indicating adverse condition.
        """
        if not adverse_signal or self.current_sl is None:
            return

        current_price = self.orderbook.get_midprice()

        # Tighten SL towards current price to reduce risk or close position
        if self.current_side == "bid":
            # Tighten SL closer to current price but never beyond entry price
            tightened_sl = max(current_price - (self.atr_multiplier * 0.5), self.entry_price)
            if tightened_sl > self.current_sl:
                self.current_sl = round(tightened_sl, 2)

        elif self.current_side == "ask":
            tightened_sl = min(current_price + (self.atr_multiplier * 0.5), self.entry_price)
            if tightened_sl < self.current_sl:
                self.current_sl = round(tightened_sl, 2)

        # Ensure SL does not cross TP after tightening
        self._ensure_sl_tp_order()

    def get_current_sl_tp(self) -> Tuple[float, float]:
        """
        Return the current active stop loss and take profit.
        """
        return self.current_sl, self.current_tp
