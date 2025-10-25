from enum import Enum
from typing import Dict, Any
from collections import deque
from datetime import datetime
from market_data.orderbook_protocol import OrderBookProtocol
from dynamic_risk_engine.signal_confidence_calibrator_protocol import SignalConfidenceCalibratorProtocol
from cancel_window.simple_cancel_window_protocol import CancelWindowProtocol



class MarketRegime(Enum):
    TRENDING = "trending"
    MEAN_REVERTING = "mean_reverting"
    VOLATILE = "volatile"
    ILLIQUID = "illiquid"
    UNKNOWN = "unknown"


class CognitiveMarketRegimeClassifier:
    def __init__(self, orderbook: OrderBookProtocol, signal_calibrator: SignalConfidenceCalibratorProtocol, cancel_window: CancelWindowProtocol):
        self.orderbook = orderbook
        self.signal_calibrator = signal_calibrator
        self.cancel_window = cancel_window
        self.regime_history = deque(maxlen=20) #Temporal memory
        self.last_regime = MarketRegime.UNKNOWN
        self.last_regime_change = datetime.now()

    
    def classify_environment(self) -> MarketRegime:
        if not self.orderbook.price_history or not self.orderbook.bids or not self.orderbook.asks:
             return MarketRegime.UNKNOWN

        volatility = self.orderbook.get_volatility_estimate()
        imbalance_bid = self.orderbook.get_order_imbalance("bid")
        imbalance_ask = self.orderbook.get_order_imbalance("ask")
        liquidity = (
            self.orderbook.get_liquidity_within_bps("bid", 50) +
            self.orderbook.get_liquidity_within_bps("ask", 50)
        )
        update_rate = self.orderbook.get_update_rate()
        #Directional Trend Detection
        if volatility > 0.015 :
            if imbalance_bid > 0.6:
                return MarketRegime.TRENDING #Upward trend
            elif imbalance_ask > 0.6:
                return MarketRegime.TRENDING #Downward trend
            
        # === Mean Reverting ===
        elif volatility < 0.005 and liquidity > 500:
            return MarketRegime.MEAN_REVERTING
        
        # === Volatile ====
        elif volatility > 0.03:
            return MarketRegime.VOLATILE
        
        # === Illiquid ====
        elif liquidity < 100 or update_rate < 0.5:
            return MarketRegime.ILLIQUID
        else:
            return MarketRegime.UNKNOWN
        

    def reinforce_regime(self, base_regime: MarketRegime) -> MarketRegime:
        confidence = self.signal_calibrator.get_current_confidence()
        volatility =  self.orderbook.get_volatility_estimate()
        liquidity = (
            self.orderbook.get_liquidity_within_bps("bid", 50) +
            self.orderbook.get_liquidity_within_bps("ask", 50)
        )

        imbalance_bid = self.orderbook.get_order_imbalance("bid")
        imbalance_ask = self.orderbook.get_order_imbalance("ask")

        update_rate = self.orderbook.get_update_rate()

        #Compute spoof impact scores
        spoof_scores = [
            self.cancel_window.compute_cancel_impact_score(f['price'], f['side'])
            for f in self.cancel_window._flags
            if f['type'] == "CANCEL_DENSITY_SPIKE"
        ]

        max_spoof_score = max(spoof_scores, default=0.0)

        #VOLATILE: spoofing + high volatility
        if max_spoof_score > 0.25 and volatility > 0.02:
            return MarketRegime.VOLATILE
        
        # MEAN_REVERTING: low confidence + low volatility
        if confidence < 0.4 and volatility < 0.005:
            return MarketRegime.MEAN_REVERTING
        
        #TRENDING: high confidence + strong directional imbalance
        if confidence > 0.7 and volatility > 0.015:
            if imbalance_bid > 0.6:
                return MarketRegime.TRENDING #Upward Trend
            elif imbalance_ask > 0.6:
                return MarketRegime.TRENDING #Downward Trend
        
        #ILLIQUID: poor update rate + low liquidity
        if liquidity < 100 or update_rate < 0.5:
            return MarketRegime.ILLIQUID

        # Override TRENDING if confidence is decaying
        if base_regime == MarketRegime.TRENDING and confidence < 0.3:
            return MarketRegime.MEAN_REVERTING

        return base_regime
    

    def update_regime(self) -> MarketRegime:
        base_regime = self.classify_environment()
        reinforced_regime = self.reinforce_regime(base_regime)

        #Detect regime drift (mutation within same label)
        drift_detected = self.detect_regime_drift()
        over_lay = self.get_behavioral_overlay()

        # Log regime shift
        if reinforced_regime != self.last_regime:
            print(f"[Regime Shift] {self.last_regime.value} → {reinforced_regime.value} at {datetime.now()}")
            self.last_regime = reinforced_regime
            self.last_regime_change = datetime.now()

        #Log regime drift
        if drift_detected:
            print(f"[Regime Drift] {self.last_regime.value} showing behavioral mutation at {datetime.now()}")

        #Log behavioral overlay
        if over_lay != "NORMAL":
            print(f"[Behavioral Overlay] {over_lay} active at {datetime.now()}")


        self.regime_history.append(reinforced_regime)

        return reinforced_regime
    

    def get_current_regime(self) -> MarketRegime:
        if not self.regime_history:
            return MarketRegime.UNKNOWN
        counts = {r: self.regime_history.count(r) for r in MarketRegime}
        return max(counts, key=counts.get)

    def get_regime_duration_seconds(self) -> float:
        return (datetime.now() - self.last_regime_change).total_seconds()
    
    def get_regime_stability(self) -> float:
        """
        To defer trades in unstable regimes.
        """
        if not self.regime_history:
            return 0.0  #Ensure that we don't divide by zero
        current = self.get_current_regime()
        return round(self.regime_history.count(current) / len(self.regime_history), 2)

    def detect_regime_drift(self) -> bool:
        """
        To log or Simulate regime transitions.
        """
        current = self.get_current_regime()
        confidence = self.signal_calibrator.get_current_confidence()
        update_rate = self.orderbook.get_update_rate()
        liquidity = (
            self.orderbook.get_liquidity_within_bps("bid", 50) +
            self.orderbook.get_liquidity_within_bps("ask", 50)
        )
        volatility = self.orderbook.get_volatility_estimate()
        spoof_score = max([
            self.cancel_window.compute_cancel_impact_score(f['price'], f['side'])
            for f in self.cancel_window._flags
            if f['type'] == "CANCEL_DENSITY_SPIKE"
        ], default=0.0)

        imbalance_bid = self.orderbook.get_order_imbalance("bid")
        imbalance_ask = self.orderbook.get_order_imbalance("ask")
        polarity = imbalance_bid - imbalance_ask

        # Example drift conditions
        if current == MarketRegime.TRENDING and confidence < 0.3 and spoof_score > 0.4:
            return True  # Momentum exhaustion
        if current == MarketRegime.MEAN_REVERTING and volatility > 0.02 and spoof_score > 0.3:
            return True  # Volatile breakout
        if current == MarketRegime.ILLIQUID and update_rate > 1.0 and liquidity > 300:
            return True  # Liquidity recovery
        
        # === Directional drift conditions ===
        if current == MarketRegime.TRENDING:
            # Polarity weakening or reversal
            if abs(polarity) < 0.1:
                return True  # Trend decay
            if polarity < -0.3 and imbalance_bid > 0.6:
                return True  # Bullish trend reversing
            if polarity > 0.3 and imbalance_ask > 0.6:
                return True  # Bearish trend reversing

        return False
    

    def get_behavioral_overlay(self) -> str:
        """
        You can use this overlay in your execution logic to throttle, defer or fade trades if the 
        regime label hasnt changed.
        """
        confidence = self.signal_calibrator.get_current_confidence()
        update_rate = self.orderbook.get_update_rate()
        volatility = self.orderbook.get_volatility_estimate()
        imbalance_bid = self.orderbook.get_order_imbalance("bid")
        imbalance_ask = self.orderbook.get_order_imbalance("ask")

        liquidity = (
            self.orderbook.get_liquidity_within_bps("bid", 50) +
            self.orderbook.get_liquidity_within_bps("ask", 50)
        )
        spoof_score = max([
            self.cancel_window.compute_cancel_impact_score(f['price'], f['side'])
            for f in self.cancel_window._flags
            if f['type'] == "CANCEL_DENSITY_SPIKE"
        ], default=0.0)

        # ==== Core Overalys (High Reflex Priority) ===
        if spoof_score > 0.6 and volatility > 0.03:
            return "LIQUIDITY_VACUUM"
        if update_rate > 2.0 and volatility > 0.02:
            if imbalance_bid > 0.6:
                return "AGGRESSIVE_SWEEP"
            if imbalance_ask > 0.6:
                return "AGGRESSIVE_SWEEP"
        if self.orderbook.get_slip_response_score() > 0.5:
            return "REACTIVE_SLIP"
        
        # === Mid-Tier Overlays ====
        if spoof_score > 0.5:
            if imbalance_bid > 0.6:
                return "LIQUIDITY_MIRAGE"
            elif imbalance_ask > 0.6:
                return "LIQUIDITY_MIRAGE"
            
        if confidence < 0.3 and volatility > 0.02:
            return "MOMENTUM_EXHAUSTION"
        if confidence < 0.4 and volatility < 0.01:
            if imbalance_bid > 0.6:
                return "REVERSION_TRAP"
            elif imbalance_ask > 0.6:
                return "REVERSION_TRAP"
            
        if liquidity < 150 and update_rate < 0.5 and confidence < 0.5:
            return "PASSIVE_FADE"
        if any(f['type'] == "LAYERED_CANCEL" for f in self.cancel_window._flags):
            return "LADDERING_PRESSURE"
        




        # ==== Low Reflex overlays ===
        if volatility < 0.005 and confidence < 0.4:
            return "CHOPPY_NOISE" 
        if self.orderbook.get_midpoint_staleness() > 0.8:
            return "MIDPOINT_STALE"
        if self.orderbook.get_quote_flicker_rate() > 1.5:
            return "QUOTE_FLICKER"
        if self.orderbook.get_depth_retreat_score() > 0.6:
            return "DEPTH_FADE"
        if self.orderbook.get_bid_aggression() > 0.6 and self.orderbook.get_ask_defense() > 0.6:
            return "CROSS_SIDE_TENSION"
        

        return "NORMAL"

    def get_scoring_weights(self) -> tuple[float, float, float, float]:
        """
        Returns weights for the four components used in cancel impact scoring.
        Adjust these weights based on your strategy's sensitivity to each factor.
        """
        regime = self.get_current_regime()
        if regime == MarketRegime.TRENDING:
            # w1 : norm_density
            # w2: dist_from_mid
            # w3: fill_score
            # w4: inv_book_depth

            return (0.3, 0.4, 0.2, 0.1)
        if regime == MarketRegime.MEAN_REVERTING:
            # w1 : norm_density
            # w2: dist_from_mid
            # w3: fill_score
            # w4: inv_book_depth

            return (0.4, 0.3, 0.2, 0.1)
        if regime == MarketRegime.VOLATILE:
            # w1 : norm_density
            # w2: dist_from_mid
            # w3: fill_score
            # w4: inv_book_depth

            return (0.2, 0.2, 0.3, 0.3)
        if regime == MarketRegime.ILLIQUID:
            # w1 : norm_density
            # w2: dist_from_mid
            # w3: fill_score
            # w4: inv_book_depth

            return (0.5, 0.1, 0.1, 0.3)
        else:
            # w1 : norm_density
            # w2: dist_from_mid
            # w3: fill_score
            # w4: inv_book_depth

            return (0.5, 0.2, 0.1, 0.2)
        
    def get_velocity_thresholds(self) -> tuple[float, float]:
        """
        Dynamically compute velocity thresholds for execution reflex.
        Returns (velocity_fast, velocity_slow) in qty/sec.
        """
        update_rate = self.orderbook.get_update_rate()         # Hz
        volatility = self.orderbook.get_volatility_estimate()  # Std dev
        imbalance_bid = self.orderbook.get_order_imbalance("bid")       # [0, 1]
        imbalance_ask = self.orderbook.get_order_imbalance("ask")

        # Normalize inputs
        update_score = min(update_rate / 5.0, 1.0)              # Cap at 5 Hz
        vol_score = min(volatility / 0.02, 1.0)                 # Cap at 2% std dev
        imbalance_score = abs(imbalance_bid - imbalance_ask)              # 0 = balanced, 1 = extreme

        # Composite aggression score
        aggression = 0.4 * update_score + 0.4 * vol_score + 0.2 * imbalance_score

        # Directional bias
        polarity = imbalance_bid - imbalance_ask    # Range [-1, 1]
        polarity_boost = 0.05 * polarity    #Adds/Subtracts up to +- 0.05

        # Map aggression to thresholds
        velocity_fast = 0.3 + aggression * 0.5 + polarity_boost  # Range: 0.25 → 0.85
        velocity_slow = 0.05 + aggression * 0.2 + polarity_boost  # Range: 0.0 → 0.3

        return round(velocity_fast, 3), round(velocity_slow, 3)



    def get_debug_view(self) -> Dict[str, Any]:
        return {
            "current_regime": self.get_current_regime().value,
            "stability": self.get_regime_stability(),
            "velocity_fast": self.get_velocity_thresholds()[0],
            "velocity_slow": self.get_velocity_thresholds()[1],
            "trend_polarity": round(self.orderbook.get_order_imbalance("bid") - self.orderbook.get_order_imbalance("ask"), 4),
            "duration_sec": self.get_regime_duration_seconds(),
            "last_regime": self.last_regime.value,
            "overlay": self.get_behavioral_overlay(),
            "volatility": self.orderbook.get_volatility_estimate(),
            "confidence": self.signal_calibrator.get_current_confidence(),
            "spoof_score": max([
                self.cancel_window.compute_cancel_impact_score(f['price'], f['side'])
                for f in self.cancel_window._flags
                if f['type'] == "CANCEL_DENSITY_SPIKE"
            ], default=0.0),
            "drift_detected": self.detect_regime_drift(),
        }
