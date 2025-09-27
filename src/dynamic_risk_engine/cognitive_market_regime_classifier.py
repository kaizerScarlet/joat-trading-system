from enum import Enum
from collections import deque
from datetime import datetime
from market_data.orderbook import OrderBook
from dynamic_risk_engine.signal_confidence_calibrator import SignalConfidenceCalibrator
from cancel_window.simple_cancel_window import SimpleCancelWindow



class MarketRegime(Enum):
    TRENDING = "trending"
    MEAN_REVERTING = "mean_reverting"
    VOLATILE = "volatile"
    ILLIQUID = "illiquid"
    UNKNOWN = "unknown"


class CognitiveMarketRegimeClassifier:
    def __init__(self, orderbook: OrderBook, signal_calibrator: SignalConfidenceCalibrator, cancel_window: SimpleCancelWindow):
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
        imbalance = self.orderbook.get_order_imbalance()
        liquidity = (
            self.orderbook.get_liquidity_within_bps("bid", 50) +
            self.orderbook.get_liquidity_within_bps("ask", 50)
        )
        update_rate = self.orderbook.get_update_rate()

        if volatility > 0.015 and imbalance > 0.6:
            return MarketRegime.TRENDING
        elif volatility < 0.005 and liquidity > 500:
            return MarketRegime.MEAN_REVERTING
        elif volatility > 0.03:
            return MarketRegime.VOLATILE
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

        imbalance = self.orderbook.get_order_imbalance()
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
        
        #TRENDING: high confidence + strong imbalance
        if confidence > 0.7 and imbalance > 0.6:
            return MarketRegime.TRENDING
        
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

        # Example drift conditions
        if current == MarketRegime.TRENDING and confidence < 0.3 and spoof_score > 0.4:
            return True  # Momentum exhaustion
        if current == MarketRegime.MEAN_REVERTING and volatility > 0.02 and spoof_score > 0.3:
            return True  # Volatile breakout
        if current == MarketRegime.ILLIQUID and update_rate > 1.0 and liquidity > 300:
            return True  # Liquidity recovery

        return False
    

    def get_behavioral_overlay(self) -> str:
        """
        You can use this overlay in your execution logic to throttle, defer or fade trades if the 
        regime label hasnt changed.
        """
        confidence = self.signal_calibrator.get_current_confidence()
        volatility = self.orderbook.get_volatility_estimate()
        spoof_score = max([
            self.cancel_window.compute_cancel_impact_score(f['price'], f['side'])
            for f in self.cancel_window._flags
            if f['type'] == "CANCEL_DENSITY_SPIKE"
        ], default=0.0)

        if spoof_score > 0.6 and volatility > 0.03:
            return "LIQUIDITY_VACUUM"
        if confidence < 0.3 and volatility > 0.02:
            return "MOMENTUM_EXHAUSTION"
        if volatility < 0.005 and confidence < 0.4:
            return "CHOPPY_NOISE"

        return "NORMAL"



