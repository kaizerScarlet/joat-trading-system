import pytest
import time
from dynamic_risk_engine.cognitive_market_regime_classifier import (
    CognitiveMarketRegimeClassifier, MarketRegime
)
from market_data.orderbook_protocol import OrderBookProtocol
from dynamic_risk_engine.signal_confidence_calibrator_protocol import SignalConfidenceCalibratorProtocol
from cancel_window.simple_cancel_window_protocol import CancelWindowProtocol
from cancel_window.order_age_distribution_protocol import OrderAgeDistributionProtocol
from market_data.orderbook_protocol import OrderBookProtocol
from collections import deque
from datetime import datetime
from dynamic_risk_engine.cognitive_market_regime_classifier_protocol import CognitiveMarketRegimeClassifierProtocol
from dynamic_risk_engine.cognitive_market_regime_classifier import MarketRegime

class MockCognitiveMarketRegimeClassifier(CognitiveMarketRegimeClassifierProtocol):
    def __init__(self):
        self.regime_history = deque([MarketRegime.UNKNOWN], maxlen=20)
        self.last_regime = MarketRegime.UNKNOWN
        self.last_regime_change = datetime.now()

    def get_current_regime(self) -> MarketRegime:
        return self.last_regime

    def get_regime_stability(self) -> float:
        current = self.get_current_regime()
        return round(self.regime_history.count(current) / len(self.regime_history), 2)

    def get_scoring_weights(self) -> tuple[float, float, float, float]:
        return (0.5, 0.2, 0.1, 0.2)

    def update_regime(self) -> MarketRegime:
        regime = MarketRegime.TRENDING
        self.regime_history.append(regime)
        self.last_regime = regime
        self.last_regime_change = datetime.now()
        return regime
    def classify_environment(self) -> MarketRegime:
        return MarketRegime.UNKNOWN
    def reinforce_regime(self, base_regime: MarketRegime) -> MarketRegime:
        return base_regime
    

    


class DummyOrderAgeTracker(OrderAgeDistributionProtocol):
    def get_order_age(self, price: float, side: str) -> float:
        return 0.0

class DummyCancelWindow(CancelWindowProtocol):
    def __init__(self):
        self.fill_events = []
        self._flags = []
        self.orderbook = DummyOrderBook()
        self.regime_classifier = DummyRegimeClassifier()

    def compute_cancel_impact_score(self, price: float, side: str) -> float:
        return 0.5  # or simulate logic if needed

    def get_cancel_density(self, side: str) -> dict:
        return {100: 10000}


class DummyOrderBook(OrderBookProtocol):
    def __init__(self):
        self.price_history =[]
        self.bids = {}
        self.asks = {}
        self.last_update_ts = None
    def get_level_size(self, price: float, side: str) -> float:
        return 1.0
    def _update_midprice(self) -> float:
        return 30000.0
    def get_update_rate(self) -> float:
        return 1.0
    def get_liquidity_within_bps(self, side: str, bps: float) -> float:
        return 1000.0
    def get_volatility_estimate(self) -> float:
        return 0.01
    def get_estimated_volume(self, side: str) -> float:
        return 1000.0
    def get_best_price(self, side: str) -> float:
        return 30000.0 if side == 'bid' else 30001.0
    def get_midprice(self) -> float:
        return 30000.5
    def get_order_imbalance(self, side: str) -> float:
        return 0.6
    def get_slip_response_score(self) -> float:
        return 0.6  # or any float value


    
class DummySignalCalibrator(SignalConfidenceCalibratorProtocol):
    def __init__(self):
        self.signal_history = []

    def get_current_confidence(self) -> float:
        correct = sum(1 for s in self.signal_history if s.get("was_correct"))
        total = len(self.signal_history) or 1
        return correct / total


class DummyRegimeClassifier(CognitiveMarketRegimeClassifierProtocol):
    def get_current_regime(self): return MarketRegime.UNKNOWN
    def get_regime_stability(self): return 1.0
    def get_scoring_weights(self): return (0.5, 0.2, 0.1, 0.2)

@pytest.fixture
def setup_classifier():
    orderbook : OrderBookProtocol = DummyOrderBook()
    signal_calibrator : SignalConfidenceCalibratorProtocol = DummySignalCalibrator()
    cancel_window : CancelWindowProtocol = DummyCancelWindow()
    classifier = CognitiveMarketRegimeClassifier(orderbook, signal_calibrator, cancel_window)
    return classifier, orderbook, signal_calibrator, cancel_window

# ------------------ Environment Classification ------------------

def test_environment_trending(setup_classifier):
    classifier, ob, _, _ = setup_classifier
    ob.price_history.extend([100, 101, 102, 103, 104, 105])
    ob.bids = {99.95: 300, 99.9: 200}
    ob.asks = {100.05: 100, 100.1: 50}
    ob.last_update_ts = time.time() - 0.1
    ob.get_volatility_estimate = lambda: 0.02
    ob.get_order_imbalance = lambda side: 0.7 if side == "bid" else 0.3 
    ob._update_midprice()
    assert classifier.classify_environment() == MarketRegime.TRENDING

def test_environment_mean_reverting(setup_classifier):
    classifier, ob, _, _ = setup_classifier
    ob.price_history.extend([100, 100.05, 99.95, 100])
    ob.bids = {99.95: 300, 99.9: 200}
    ob.asks = {100.05: 300, 100.1: 200}
    ob.last_update_ts = time.time() - 0.1
    ob.get_volatility_estimate = lambda: 0.004
    ob._update_midprice()
    assert classifier.classify_environment() == MarketRegime.MEAN_REVERTING

def test_environment_volatile(setup_classifier):
    classifier, ob, _, _ = setup_classifier
    ob.price_history.extend([100, 110, 90, 115])
    ob.bids = {99.95: 200}
    ob.asks = {100.05: 200}
    ob.last_update_ts = time.time() - 0.1
    ob.get_volatility_estimate = lambda: 0.04
    ob.get_order_imbalance = lambda side: 0.7 if side == "bid" else 0.3
    ob._update_midprice()
    assert classifier.classify_environment() == MarketRegime.VOLATILE

def test_environment_illiquid(setup_classifier):
    classifier, ob, _, _ = setup_classifier
    ob.bids = {99.5: 1}
    ob.asks = {100.5: 1}
    ob.last_update_ts = time.time() - 5
    ob.price_history.extend([99.5, 100.5])
    ob.get_liquidity_within_bps = lambda side, bps: 30.0  # Total = 60.0
    ob.get_update_rate = lambda: 0.2
    ob._update_midprice()
    assert classifier.classify_environment() == MarketRegime.ILLIQUID

def test_environment_unknown(setup_classifier):
    classifier, ob, _, _ = setup_classifier
    ob.price_history.clear()
    ob.bids.clear()
    ob.asks.clear()
    ob.last_update_ts = None
    ob.get_liquidity_within_bps = lambda side, bps: 30.0
    ob.get_update_rate = lambda: 0.2

    ob._update_midprice()

    # Patch: Ensure classifier checks for emptiness first
    # If not already in your classifier:
    # if not self.orderbook.price_history or not self.orderbook.bids or not self.orderbook.asks:
    #     return MarketRegime.UNKNOWN

    assert classifier.classify_environment() == MarketRegime.UNKNOWN


# ------------------ Reinforcement Logic ------------------
def test_reinforce_to_volatile_on_high_spoof_score(setup_classifier):
    classifier, ob, _, cw = setup_classifier

    # Step 1: Volatility
    ob.price_history.extend([100, 150, 80, 160, 70])
    
    # Step 2: Shallow book depth
    ob.bids = {100: 0.1}  # Very shallow
    ob.asks = {101: 200}
    
    # Step 3: Recent update
    ob.last_update_ts = time.time() - 0.1
    ob._update_midprice()
    ob.get_volatility_estimate = lambda: 0.04


    # Step 4: Fill events at spoofed price
    cw.fill_events = [{'price': 100, 'side': 'bid'}] * 10

    # Step 5: High cancel density
    cw._flags.append({
        "type": "CANCEL_DENSITY_SPIKE",
        "price": 100,
        "side": "bid",
        "timestamp": 123456,
        "cancel_count": 1000,
        "orderid": "spoof123"
    })

    spoof_score = classifier.cancel_window.compute_cancel_impact_score(100, "bid")
    print(f"Adjusted spoof score: {spoof_score}")
    assert spoof_score > 0.25
    assert classifier.reinforce_regime(MarketRegime.MEAN_REVERTING) == MarketRegime.VOLATILE




def test_reinforce_to_mean_reverting_on_low_confidence(setup_classifier):
    classifier, ob, sc, _ = setup_classifier

    # Step 1: Stronger signal decay
    sc.signal_history.extend([{'signal_id': 's1', 'was_correct': False}] * 50)

    # Step 2: Flat price history
    ob.price_history.extend([100, 100.0005, 99.9995])
    
    # Step 3: Balanced book
    ob.bids = {99.95: 200}
    ob.asks = {100.05: 200}
    
    # Step 4: Recent update
    ob.last_update_ts = time.time() - 0.1
    ob._update_midprice()

    confidence = classifier.signal_calibrator.get_current_confidence()
    print(f"Current confidence: {confidence}")
    assert confidence < 0.4
    assert classifier.reinforce_regime(MarketRegime.TRENDING) == MarketRegime.MEAN_REVERTING






def test_reinforce_to_trending_on_high_confidence_and_imbalance(setup_classifier):
    classifier, ob, sc, _ = setup_classifier
    sc.signal_history.extend([{'signal_id': 's1', 'was_correct': True}] * 10)
    ob.bids = {99.95: 300}
    ob.asks = {100.05: 10}
    ob.price_history.extend([100, 101, 102])
    ob.last_update_ts = time.time() - 0.1
    ob.get_order_imbalance = lambda side: 0.7 if side == "bid" else 0.3
    ob.get_volatility_estimate = lambda: 0.02


    ob._update_midprice()
    assert classifier.reinforce_regime(MarketRegime.UNKNOWN) == MarketRegime.TRENDING

def test_reinforce_to_illiquid_on_low_liquidity_and_update_rate(setup_classifier):
    classifier, ob, _, _ = setup_classifier
    ob.bids = {99.5: 1}
    ob.asks = {100.5: 1}
    ob.last_update_ts = time.time() - 5
    ob.price_history.extend([99.5, 100.5])  # Ensure price history is non-empty
    ob.get_liquidity_within_bps = lambda side, bps: 30.0
    ob.get_update_rate = lambda: 0.2
    ob.midprice = 100.0

    ob._update_midprice()
    assert classifier.reinforce_regime(MarketRegime.TRENDING) == MarketRegime.ILLIQUID

def test_low_spoof_score_does_not_trigger_volatile(setup_classifier):
    classifier, ob, _, cw = setup_classifier
    ob.price_history.extend([100, 101, 102])
    ob.bids = {100: 100}
    ob.asks = {101: 100}
    ob.last_update_ts = time.time() - 0.1
    ob._update_midprice()

    cw._flags.append({
        "type": "CANCEL_DENSITY_SPIKE",
        "price": 100,
        "side": "bid",
        "timestamp": 123456,
        "cancel_count": 1,
        "orderid": "low_spoof"
    })

    assert classifier.reinforce_regime(MarketRegime.MEAN_REVERTING) != MarketRegime.VOLATILE

# ------------------ Temporal Memory ------------------

def test_update_regime_adds_to_history(setup_classifier):
    classifier, ob, _, _ = setup_classifier
    ob.price_history.extend([100, 101, 102])
    ob.bids = {99.95: 300}
    ob.asks = {100.05: 300}
    ob.last_update_ts = time.time() - 0.1
    ob._update_midprice()
    regime = classifier.update_regime()
    assert regime in classifier.regime_history

def test_get_current_regime_majority_vote(setup_classifier):
    classifier, _, _, _ = setup_classifier
    classifier.regime_history.extend([
        MarketRegime.TRENDING,
        MarketRegime.TRENDING,
        MarketRegime.MEAN_REVERTING
    ])
    assert classifier.get_current_regime() == MarketRegime.TRENDING


def test_regime_drift_from_trending_due_to_exhaustion(setup_classifier):
    classifier, ob, sc, cw = setup_classifier

    classifier.regime_history.extend([MarketRegime.TRENDING] * 5)
    sc.signal_history.extend([{'signal_id': 's1', 'was_correct': False}] * 30)

    cw.fill_events = [{'price': 100, 'side': 'bid'}] * 50
    cw._flags = [{
        "type": "CANCEL_DENSITY_SPIKE",
        "price": 100,
        "side": "bid",
        "timestamp": time.time(),
        "cancel_count": 10000,
        "orderid": "spoof1"
    }]

    # Ensure spoof price dominates cancel density
    classifier.cancel_window.get_cancel_density = lambda side: {100: 10000}

    ob.bids = {99.9: 100}
    ob.asks = {100.1: 100}
    ob.last_update_ts = time.time() - 0.1
    ob._update_midprice()

    classifier.orderbook.get_level_size = lambda price, side: 0.1 if price == 100 and side == "bid" else 100

    spoof_score = classifier.cancel_window.compute_cancel_impact_score(100, "bid")
    print(f"[Test] Spoof score computed: {spoof_score}")
    assert spoof_score > 0.4
    drift = classifier.detect_regime_drift()
    assert drift is True





def test_regime_drift_from_mean_reverting_to_volatile(setup_classifier):
    classifier, ob, sc, cw = setup_classifier

    classifier.regime_history.extend([MarketRegime.MEAN_REVERTING] * 5)

    ob.price_history.extend([100, 120, 80, 130])
    ob.bids = {99.9: 100}
    ob.asks = {100.1: 100}
    ob.last_update_ts = time.time() - 0.1
    ob._update_midprice()
    ob.get_volatility_estimate = lambda: 0.04


    cw.fill_events = [{'price': 100, 'side': 'ask'}] * 50
    cw._flags = [{
        "type": "CANCEL_DENSITY_SPIKE",
        "price": 100,
        "side": "ask",
        "timestamp": time.time(),
        "cancel_count": 10000,
        "orderid": "breakout_spoof"
    }]

    classifier.cancel_window.get_cancel_density = lambda side: {100: 10000}
    classifier.orderbook.get_level_size = lambda price, side: 0.1 if price == 100 and side == "ask" else 100

    spoof_score = classifier.cancel_window.compute_cancel_impact_score(100, "ask")
    print(f"[Test] Spoof score computed: {spoof_score}")
    assert spoof_score > 0.3

    drift = classifier.detect_regime_drift()
    assert drift is True

def test_behavioral_overlay_liquidity_vacuum(setup_classifier):
    classifier, ob, sc, cw = setup_classifier
    classifier.cancel_window.compute_cancel_impact_score = lambda price, side: 0.7

    sc.signal_history.extend([{'signal_id': 's1', 'was_correct': True}] * 10)
    ob.price_history.extend([100, 180, 70, 190, 65])
    
    ob.bids = {99.9: 100}
    ob.asks = {100.1: 100}
    ob.last_update_ts = time.time() - 0.1
    ob._update_midprice()
    ob.get_volatility_estimate = lambda: 0.04


    cw.fill_events = [{'price': 100, 'side': 'bid'}] * 50
    cw._flags = [{
        "type": "CANCEL_DENSITY_SPIKE",
        "price": 100,
        "side": "bid",
        "timestamp": time.time(),
        "cancel_count": 10000,
        "orderid": "vacuum_spoof"
    }]

    classifier.cancel_window.get_cancel_density = lambda side: {100: 10000}
    classifier.orderbook.get_level_size = lambda price, side: 0.1 if price == 100 and side == "bid" else 100

    overlay = classifier.get_behavioral_overlay()
    print(f"[Test] Overlay computed: {overlay}")
    assert overlay == "LIQUIDITY_VACUUM"





def test_behavioral_overlay_momentum_exhaustion(setup_classifier):
    classifier, ob, sc, cw = setup_classifier

    sc.signal_history.extend([{'signal_id': 's1', 'was_correct': False}] * 40)
    ob.price_history.extend([100, 110, 90, 115])
    ob.last_update_ts = time.time() - 0.1
    ob._update_midprice()
    ob.get_volatility_estimate = lambda: 0.04
    ob.get_slip_response_score = lambda: 0.0



    overlay = classifier.get_behavioral_overlay()
    assert overlay == "MOMENTUM_EXHAUSTION"



def test_behavioral_overlay_choppy_noise(setup_classifier):
    classifier, ob, sc, cw = setup_classifier

    sc.signal_history.extend([{'signal_id': 's1', 'was_correct': False}] * 30)
    ob.price_history.extend([100, 100.01, 99.99, 100.02])
    ob.last_update_ts = time.time() - 0.1
    ob._update_midprice()
    ob.get_volatility_estimate = lambda: 0.003
    ob.get_slip_response_score = lambda: 0.0



    overlay = classifier.get_behavioral_overlay()
    assert overlay == "CHOPPY_NOISE"



def test_debug_view_snapshot(setup_classifier):
    classifier, ob, sc, cw = setup_classifier
    ob.price_history.extend([100, 101, 102])
    ob.bids = {99.95: 300}
    ob.asks = {100.05: 300}
    sc.signal_history.extend([{'signal_id': 's1', 'was_correct': True}] * 10)
    cw._flags.append({
        "type": "CANCEL_DENSITY_SPIKE",
        "price": 100,
        "side": "bid",
        "timestamp": time.time(),
        "cancel_count": 1000,
        "orderid": "debug_spoof"
    })
    ob._update_midprice()
    debug = classifier.get_debug_view()
    print(debug)
    assert "current_regime" in debug
    assert "spoof_score" in debug
    assert isinstance(debug["stability"], float)




def test_scoring_weights_per_regime(setup_classifier):
    classifier, _, _, _ = setup_classifier
    for regime in MarketRegime:
        classifier.regime_history.clear()
        classifier.regime_history.extend([regime] * 5)
        weights = classifier.get_scoring_weights()
        print(f"{regime.value}: {weights}")
        assert sum(weights) <= 1.1  # Allow rounding


def test_regime_duration_tracking(setup_classifier):
    classifier, ob, _, _ = setup_classifier
    ob.price_history.extend([100, 101, 102])
    ob.bids = {99.95: 300}
    ob.asks = {100.05: 300}
    ob._update_midprice()
    classifier.update_regime()
    time.sleep(0.1)
    duration = classifier.get_regime_duration_seconds()
    print(f"Duration: {duration}")
    assert duration > 0.05
