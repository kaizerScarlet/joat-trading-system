import time #will need to change this at production so that it is the server time taken not my machine time
import pytest
from typing import Dict, Any
from src.market_data.orderbook_protocol import OrderBookProtocol
from src.cancel_window.order_age_distribution_protocol import OrderAgeDistributionProtocol
from src.dynamic_risk_engine.cognitive_market_regime_classifier_protocol import CognitiveMarketRegimeClassifierProtocol, MarketRegime 
from src.cancel_window.simple_cancel_window_protocol import CancelWindowProtocol, CancelWindowTunerProtocol, CancelWindowTunerForLayeringProtocol, AdaptiveThresholdProtocol, FillThresholdTunerProtocol
from src.cancel_window.simple_cancel_window_protocol import CancelWindowProtocol, CancelWindowTunerProtocol, CancelWindowTunerForLayeringProtocol
from src.cancel_window.order_layering_detection_protocol import OrderLayeringDetectionProtocol
from src.cancel_window.order_laddering_detection_protocol import OrderLadderingDetectionProtocol
from src.cancel_window.synthetic_fill_detector_protocol import SyntheticFillDetectorProtocol
from src.cancel_window.order_spoofing_detection_protocol import OrderSpoofingDetectionProtocol
from src.cancel_window.cancel_denisty_detection_protocol import CancelDensityDetectionProtocol
from src.cancel_window.order_iceberg_detection_protocol import OrderIcebergDetectionProtocol
from src.cancel_window.simple_cancel_window import SimpleCancelWindow
from src.cancel_window.simple_cancel_window_protocol import AdaptiveDensityWindowProtocol , AdaptiveThresholdProtocol

# === Dummy Layering Detection ===
class DummyOrderLayeringDetection(OrderLayeringDetectionProtocol):
    def register_order(self, orderid, timestamp, price, size, side): pass
    def cancel_order(self, orderid, timestamp, event_type, price, size, distance_from_best, side): pass
    def register_event(self, orderid, timestamp, event_type, price, size, side): pass

# === Dummy Laddering Detection ===
class DummyOrderLadderingDetection(OrderLadderingDetectionProtocol):
    def register_event(self, orderid, timestamp, event_type, price, size, side): pass

# === Dummy Synthetic Fill Detector ===
class DummySyntheticFillDetection(SyntheticFillDetectorProtocol):
    def register_event(self, orderid, timestamp, event_type, price, size, side): pass

# === Dummy Spoofing Detector ===
class DummyOrderSpoofingDetection(OrderSpoofingDetectionProtocol):
    def register_event(self, orderid, timestamp, event_type, price, size, side): pass

# === Dummy Cancel Density Detector ===
class DummyCancelDensityDetection(CancelDensityDetectionProtocol):
    def detect_spikes(self, current_time=None): return []
    def register_cancel(self, orderid, timestamp, event_type, price, size, side): pass
    def get_density_score(self, side=None, current_time=None): return 0.0
    def get_debug_view(self): return {}

# === Dummy Iceberg Detection ===
class DummyOrderIcebergDetection(OrderIcebergDetectionProtocol):
    def register_event(self, orderid, timestamp, event_type, price, size, side): pass







# === Dummy Adaptive Density Window ===
class DummyAdaptiveDensityWindow(AdaptiveDensityWindowProtocol):
    def __init__(self):
        self.current_window = 100
        self.decay = 0.1
        self.classifier = None

    def update(self, ts: float, recent_cancel_rate: float) -> None:
        pass

    def get_current_window(self) -> int:
        return self.current_window

    def get_debug_view(self) -> Dict[str, Any]:
        return {"current_window_ms": self.current_window, "decay": self.decay}

# === Dummy Adaptive Threshold ===
class DummyAdaptiveThreshold(AdaptiveThresholdProtocol):
    def __init__(self):
        self.threshold = 3
        self.decay = 0.1
        self.classifier = None

    def update(self, volume: float, volatility: float) -> None:
        pass

    def get_threshold(self) -> int:
        return self.threshold

    def get_debug_view(self) -> Dict[str, Any]:
        return {"threshold": self.threshold, "decay": self.decay}

# === Dummy Fill Threshold Tuner ===
class DummyFillThresholdTuner(FillThresholdTunerProtocol):
    def __init__(self):
        self.ratio = 0.9
        self.decay = 0.05
        self.classifier = None

    def update(self, avg_trade_size: float, volatility: float):
        pass

    def get_ratio(self) -> float:
        return self.ratio

    def get_debug_view(self) -> Dict[str, Any]:
        return {"fill_ratio": self.ratio, "decay": self.decay}

# === Dummy Cancel Window Tuner ===
class DummyCancelWindowTuner(CancelWindowTunerProtocol):
    def __init__(self):
        self.ema_latency = 50
        self.ema_alpha = 0.2
        self.min_ms = 50
        self.max_ms = 75
        self.classifier = None

    def update(self, latency_ms: float) -> None:
        pass

    def current_window_ms(self) -> int:
        return self.ema_latency

# === Dummy Cancel Window Tuner for Layering ===
class DummyCancelWindowTunerForLayering(CancelWindowTunerForLayeringProtocol):
    def __init__(self):
        self.ema_latency = 100
        self.ema_alpha = 0.2
        self.min_ms = 100
        self.max_ms = 350
        self.classifier = None

    def update(self, latency_ms: float) -> None:
        pass

    def current_window_ms(self) -> int:
        return self.ema_latency

    def get_debug_view(self) -> Dict[str, Any]:
        return {
            "ema_latency": self.ema_latency,
            "current_window_ms": self.ema_latency,
            "min_ms": self.min_ms,
            "max_ms": self.max_ms,
            "ema_alpha": self.ema_alpha
        }
        



class DummyOrderAgeTracker(OrderAgeDistributionProtocol):
    def get_order_age(self, price: float, side: str) -> float:
        return 0.0

class DummyOrderBook(OrderBookProtocol):
    def get_level_size(self, price: float, side: str) -> float:
        return 1.0
    def update_midprice(self) -> float:
        return 30000.0
    def get_update_rate(self) -> float:
        return 1.0
    def get_liquidity_within_bps(self, side: str, bps: float) -> float:
        return 1000.0
    def get_volatility_estimate(self) -> float:
        return 0.001
    def get_estimated_volume(self, side: str) -> float:
        return 100.0
    def get_best_price(self, side: str) -> float:
        return 30000.0 if side == 'bid' else 30001.0
    def get_midprice(self) -> float:
        return 30000.5
    def get_tick_size(self):
        return 0.1  # or any realistic float

class DummyRegimeClassifier(CognitiveMarketRegimeClassifierProtocol):
    def get_current_regime(self): return MarketRegime.UNKNOWN
    def get_regime_stability(self): return 1.0
    def get_scoring_weights(self): return (0.5, 0.2, 0.1, 0.2)
    def get_behavioral_overlay(self): return "NORMAL"
    def get_debug_view(self):
        return {"spoof_score": 0.0, "volatility": 0.001}


#test fast cancel on bid side
def test_fast_cancel_flag_bid():
    tuner_for_layering = DummyCancelWindowTunerForLayering()
    cw : CancelWindowProtocol = SimpleCancelWindow(
        tuner = DummyCancelWindowTuner(),
        order_age_tracker=DummyOrderAgeTracker(),
        order_book=DummyOrderBook(),
        classifier=DummyRegimeClassifier(),
        order_layering = DummyOrderLayeringDetection(),
        order_ladder_tracker = DummyOrderLadderingDetection(),
        synthetic_fill_detector = DummySyntheticFillDetection(),
        order_spoofing = DummyOrderSpoofingDetection(),
        order_cancel_density = DummyCancelDensityDetection(),
        order_iceberg_detection = DummyOrderIcebergDetection(),
        cancel_density_threshold_bid = DummyAdaptiveThreshold(),
        cancel_density_threshold_ask = DummyAdaptiveThreshold(),
        cancel_density_window_ms = DummyAdaptiveDensityWindow()



        )
    

    #add level at t0
    cw.process_l2_update({"E": 1000, "b": [["30000", "1.0"]], "a": []})
    # cancel same level 20ms later
    cw.process_l2_update({"E": 1020, "b": [["30000", "0"]], "a": []})

    flags = cw.get_flags()
    spoof_flags = [f for f in flags if f["type"] == "CANCEL_SPOOF"]
    print(flags)
    assert spoof_flags, "Expected CANCEL_SPOOF flag"
    assert flags and flags[0]["type"] == "CANCEL_SPOOF"
    assert flags[0]["latency_ms"] == 20
    
    debug = cw.get_debug_view()
    assert debug["cancel_density_bid"][30000.0] == 1


#test fast cancel on ask side
def test_fast_cancel_flag_ask():
    tuner_for_layering = DummyCancelWindowTunerForLayering()
    cw : CancelWindowProtocol = SimpleCancelWindow(
        tuner = DummyCancelWindowTuner(),
        order_age_tracker=DummyOrderAgeTracker(),
        order_book=DummyOrderBook(),
        classifier=DummyRegimeClassifier(),
        order_layering = DummyOrderLayeringDetection(),
        order_ladder_tracker = DummyOrderLadderingDetection(),
        synthetic_fill_detector = DummySyntheticFillDetection(),
        order_spoofing = DummyOrderSpoofingDetection(),
        order_cancel_density = DummyCancelDensityDetection(),
        order_iceberg_detection = DummyOrderIcebergDetection(),
        cancel_density_threshold_bid = DummyAdaptiveThreshold(),
        cancel_density_threshold_ask = DummyAdaptiveThreshold(),
        cancel_density_window_ms = DummyAdaptiveDensityWindow()



        )

    #add level at t0
    cw.process_l2_update({"E": 1000, "b": [],   "a": [["30000", "1.0"]]})
    # cancel same level 20ms later
    cw.process_l2_update({"E": 1020, "b": [],   "a": [["30000", "0"]]})

    flags = cw.get_flags()
    print(flags)
    assert flags and flags[0]["type"] == "CANCEL_SPOOF"
    assert flags[0]["latency_ms"] == 20



#Test True fill flag on ask side
def test_true_fill_flag_ask():
    tuner_for_layering = DummyCancelWindowTunerForLayering()
    cw : CancelWindowProtocol = SimpleCancelWindow(
        tuner = DummyCancelWindowTuner(),
        order_age_tracker=DummyOrderAgeTracker(),
        order_book=DummyOrderBook(),
        classifier=DummyRegimeClassifier(),
        order_layering = DummyOrderLayeringDetection(),
        order_ladder_tracker = DummyOrderLadderingDetection(),
        synthetic_fill_detector = DummySyntheticFillDetection(),
        order_spoofing = DummyOrderSpoofingDetection(),
        order_cancel_density = DummyCancelDensityDetection(),
        order_iceberg_detection = DummyOrderIcebergDetection(),
        cancel_density_threshold_bid = DummyAdaptiveThreshold(),
        cancel_density_threshold_ask = DummyAdaptiveThreshold(),
        cancel_density_window_ms = DummyAdaptiveDensityWindow()



        )
    #1. add order
    cw.process_l2_update({"E": 1000, "a": [["30050", "2.0"]], "b":[]})
    #2. Cancel order 20ms later
    cw.process_l2_update({"E": 1020, "a": [["30050", "0"]], "b": []})
    #3. Trade hits that price 40ms after cancel
    cw.process_trade({
        "T": 1060,
        "p": "30050",
        "q": "2.0",
        "m": False # buyer is taker
        })
    flags = cw.get_flags()
    print(flags)
    assert any(f["type"] == "TRUE_FILL" for f in flags)

#Test True fill flag bid
def test_true_fill_flag_bid():
    tuner_for_layering = DummyCancelWindowTunerForLayering()
    cw : CancelWindowProtocol = SimpleCancelWindow(
        tuner = DummyCancelWindowTuner(),
        order_age_tracker=DummyOrderAgeTracker(),
        order_book=DummyOrderBook(),
        classifier=DummyRegimeClassifier(),
        order_layering = DummyOrderLayeringDetection(),
        order_ladder_tracker = DummyOrderLadderingDetection(),
        synthetic_fill_detector = DummySyntheticFillDetection(),
        order_spoofing = DummyOrderSpoofingDetection(),
        order_cancel_density = DummyCancelDensityDetection(),
        order_iceberg_detection = DummyOrderIcebergDetection(),
        cancel_density_threshold_bid = DummyAdaptiveThreshold(),
        cancel_density_threshold_ask = DummyAdaptiveThreshold(),
        cancel_density_window_ms = DummyAdaptiveDensityWindow()



        )
    #1. add order
    cw.process_l2_update({"E": 1000, "b": [["30050", "2.0"]], "a":[]})
    #2. Cancel order 20ms later
    cw.process_l2_update({"E": 1020, "b": [["30050", "0"]], "a": []})
    #3. Trade hits that price 40ms after cancel
    cw.process_trade({
        "T": 1060,
        "p": "30050",
        "q": "2.0",
        "m": True   #seller is taker
        })
    flags = cw.flush_flags()
    print(flags)
    assert any(f["type"] == "TRUE_FILL" for f in flags)

#Test partial fill flag bid side
#@pytest.mark.asyncio
def test_partial_fill_flag_bid():
    """
    Order is added -> partially removed via  trade smaller than original size
    in <window_ms. Expect PARTIAL_FILL, not TRUE_FILL.
    """
    tuner_for_layering = DummyCancelWindowTunerForLayering()
    cw : CancelWindowProtocol = SimpleCancelWindow(
        tuner = DummyCancelWindowTuner(),
        order_age_tracker=DummyOrderAgeTracker(),
        order_book=DummyOrderBook(),
        classifier=DummyRegimeClassifier(),
        order_layering = DummyOrderLayeringDetection(),
        order_ladder_tracker = DummyOrderLadderingDetection(),
        synthetic_fill_detector = DummySyntheticFillDetection(),
        order_spoofing = DummyOrderSpoofingDetection(),
        order_cancel_density = DummyCancelDensityDetection(),
        order_iceberg_detection = DummyOrderIcebergDetection(),
        cancel_density_threshold_bid = DummyAdaptiveThreshold(),
        cancel_density_threshold_ask = DummyAdaptiveThreshold(),
        cancel_density_window_ms = DummyAdaptiveDensityWindow()



        )
    #1. add 2 BTC ask @ 30 070
    cw.process_l2_update({"E": 1_000, "b": [["30070", "2.0"]], "a":[]})

    #2. cancel level 20ms later
    cw.process_l2_update({"E": 1_020, "b": [["30070", "0"]], "a": []})
    #3. only 0.5 BTC trades through -> partial
    cw.process_trade({
        "T": 1_040,
        "p": "30070",
        "q": "0.5",
        "m": True     #taker is seller-> hitting bid
    })

    flags = cw.get_flags()
    print(flags)
    types = [f["type"] for f in flags]
    assert "PARTIAL_FILL" in types
    assert "TRUE_FILL" not in types 


#Test partial fill flag ask side
#@pytest.mark.asyncio
def test_partial_fill_flag_ask():
    """
    Order is added -> partially removed via  trade smaller than original size
    in <window_ms. Expect PARTIAL_FILL, not TRUE_FILL.
    """
    tuner_for_layering = DummyCancelWindowTunerForLayering()
    cw : CancelWindowProtocol = SimpleCancelWindow(
        tuner = DummyCancelWindowTuner(),
        order_age_tracker=DummyOrderAgeTracker(),
        order_book=DummyOrderBook(),
        classifier=DummyRegimeClassifier(),
        order_layering = DummyOrderLayeringDetection(),
        order_ladder_tracker = DummyOrderLadderingDetection(),
        synthetic_fill_detector = DummySyntheticFillDetection(),
        order_spoofing = DummyOrderSpoofingDetection(),
        order_cancel_density = DummyCancelDensityDetection(),
        order_iceberg_detection = DummyOrderIcebergDetection(),
        cancel_density_threshold_bid = DummyAdaptiveThreshold(),
        cancel_density_threshold_ask = DummyAdaptiveThreshold(),
        cancel_density_window_ms = DummyAdaptiveDensityWindow()



        )
    #1. add 2 BTC ask @ 30 070
    cw.process_l2_update({"E": 1_000, "a": [["30070", "2.0"]], "b":[]})

    #2. cancel level 20ms later
    cw.process_l2_update({"E": 1_020, "a": [["30070", "0"]], "b": []})
    #3. only 0.5 BTC trades through -> partial
    cw.process_trade({
        "T": 1_040,
        "p": "30070",
        "q": "0.5",
        "m": False  #taker is buyer -> hitting ask
    })

    flags = cw.get_flags()
    print(flags)
    types = [f["type"] for f in flags]
    assert "PARTIAL_FILL" in types
    assert "TRUE_FILL" not in types 


# Test iceberg cancel flag emitted ask side
def test_iceberg_cancel_flag_emitted_ask():
    tuner_for_layering = DummyCancelWindowTunerForLayering()
    cw : CancelWindowProtocol = SimpleCancelWindow(
        tuner = DummyCancelWindowTuner(),
        order_age_tracker=DummyOrderAgeTracker(),
        order_book=DummyOrderBook(),
        classifier=DummyRegimeClassifier(),
        order_layering = DummyOrderLayeringDetection(),
        order_ladder_tracker = DummyOrderLadderingDetection(),
        synthetic_fill_detector = DummySyntheticFillDetection(),
        order_spoofing = DummyOrderSpoofingDetection(),
        order_cancel_density = DummyCancelDensityDetection(),
        order_iceberg_detection = DummyOrderIcebergDetection(),
        cancel_density_threshold_bid = DummyAdaptiveThreshold(),
        cancel_density_threshold_ask = DummyAdaptiveThreshold(),
        cancel_density_window_ms = DummyAdaptiveDensityWindow()



        )
    base_ts = 100000
    #simulate  3 quick size reductions at same price, no  trades
    #1. Add new ask level at 30090 with size 4.0
    cw.process_l2_update({"E": base_ts, "a": [["30090", "4.0"]], "b": []})
    #2. reduce to 3.0
    cw.process_l2_update({"E": base_ts + 10, "a": [["30090", " 3.0"]], "b": []})
    #3. reduce again to 2.0
    cw.process_l2_update({"E": base_ts + 20, "a": [["30090", "2.0"]], "b": []})
    #4. Cancel (set at 0)
    cw.process_l2_update({"E": base_ts + 30, "a": [["30090", "0"]], "b": []})

    flags = cw.get_flags()
    print(flags)
    assert any(f["type"] == "ICEBERG_CANCEL" for f in flags)
    assert flags[0]["type"] == "ICEBERG_CANCEL"
    assert flags[0]["price"] == 30090.0
    assert flags[0]["side"] == "ask"
    assert "reductions" in flags[0]
    assert len(flags[0]["reductions"]) == 2

#Test iceberg cancel flag emitted bid side
def test_iceberg_cancel_flag_emitted_bid():
    tuner_for_layering = DummyCancelWindowTunerForLayering()
    cw : CancelWindowProtocol = SimpleCancelWindow(
        tuner = DummyCancelWindowTuner(),
        order_age_tracker=DummyOrderAgeTracker(),
        order_book=DummyOrderBook(),
        classifier=DummyRegimeClassifier(),
        order_layering = DummyOrderLayeringDetection(),
        order_ladder_tracker = DummyOrderLadderingDetection(),
        synthetic_fill_detector = DummySyntheticFillDetection(),
        order_spoofing = DummyOrderSpoofingDetection(),
        order_cancel_density = DummyCancelDensityDetection(),
        order_iceberg_detection = DummyOrderIcebergDetection(),
        cancel_density_threshold_bid = DummyAdaptiveThreshold(),
        cancel_density_threshold_ask = DummyAdaptiveThreshold(),
        cancel_density_window_ms = DummyAdaptiveDensityWindow()



        )

    base_ts = 100000
    #simulate  3 quick size reductions at same price, no  trades
    #1. Add new ask level at 30090 with size 4.0
    cw.process_l2_update({"E": base_ts, "b": [["30090", "4.0"]], "a": []})
    #2. reduce to 3.0
    cw.process_l2_update({"E": base_ts + 10, "b": [["30090", " 3.0"]], "a": []})
    #3. reduce again to 2.0
    cw.process_l2_update({"E": base_ts + 20, "b": [["30090", "2.0"]], "a": []})
    #4. Cancel (set at 0)
    cw.process_l2_update({"E": base_ts + 30, "b": [["30090", "0"]], "a": []})

    flags = cw.get_flags()
    iceberg_flags = [f for f in flags if f['type'] == 'ICEBERG_CANCEL']
    print(flags)
    assert any(f["type"] == "ICEBERG_CANCEL" for f in flags)
    assert flags[0]["type"] == "ICEBERG_CANCEL"
    assert flags[0]["price"] == 30090.0
    assert flags[0]["side"] == "bid"
    assert "reductions" in flags[0]
    assert len(flags[0]["reductions"]) == 2


#Test no iceberg if only one reduction ask
def test_no_iceberg_if_only_one_reduction_ask():
    tuner_for_layering = DummyCancelWindowTunerForLayering()
    cw : CancelWindowProtocol = SimpleCancelWindow(
        tuner = DummyCancelWindowTuner(),
        order_age_tracker=DummyOrderAgeTracker(),
        order_book=DummyOrderBook(),
        classifier=DummyRegimeClassifier(),
        order_layering = DummyOrderLayeringDetection(),
        order_ladder_tracker = DummyOrderLadderingDetection(),
        synthetic_fill_detector = DummySyntheticFillDetection(),
        order_spoofing = DummyOrderSpoofingDetection(),
        order_cancel_density = DummyCancelDensityDetection(),
        order_iceberg_detection = DummyOrderIcebergDetection(),
        cancel_density_threshold_bid = DummyAdaptiveThreshold(),
        cancel_density_threshold_ask = DummyAdaptiveThreshold(),
        cancel_density_window_ms = DummyAdaptiveDensityWindow()



        )

    base_ts = 100000
    #simulate  3 quick size reductions at same price, no  trades
    #1. Add new ask level at 30090 with size 5.0
    cw.process_l2_update({"E": base_ts, "a": [["30090", "5.0"]], "b": []})
    #3. reduce to 2.0
    cw.process_l2_update({"E": base_ts + 20, "a": [["30090", "2.0"]], "b": []})
    #4. Cancel (set at 0)
    cw.process_l2_update({"E": base_ts + 30, "a": [["30090", "0"]], "b": []})
    
    flags = cw.get_flags()
    iceberg_flags = [f for f in flags if f["type"] == "ICEBERG_CANCEL"]
    assert len(iceberg_flags) == 0
    assert flags[0]["type"] == "CANCEL_SPOOF"


#Test no iceberg if only one reduction bid
def test_no_iceberg_if_only_one_reduction_bid():
    tuner_for_layering = DummyCancelWindowTunerForLayering()
    cw : CancelWindowProtocol = SimpleCancelWindow(
        tuner = DummyCancelWindowTuner(),
        order_age_tracker=DummyOrderAgeTracker(),
        order_book=DummyOrderBook(),
        classifier=DummyRegimeClassifier(),
        order_layering = DummyOrderLayeringDetection(),
        order_ladder_tracker = DummyOrderLadderingDetection(),
        synthetic_fill_detector = DummySyntheticFillDetection(),
        order_spoofing = DummyOrderSpoofingDetection(),
        order_cancel_density = DummyCancelDensityDetection(),
        order_iceberg_detection = DummyOrderIcebergDetection(),
        cancel_density_threshold_bid = DummyAdaptiveThreshold(),
        cancel_density_threshold_ask = DummyAdaptiveThreshold(),
        cancel_density_window_ms = DummyAdaptiveDensityWindow()



        )
    base_ts = 100000
    #simulate  3 quick size reductions at same price, no  trades
    #1. Add new ask level at 30090 with size 5.0
    cw.process_l2_update({"E": base_ts, "b": [["30090", "5.0"]], "a": []})
    #3. reduce to 2.0
    cw.process_l2_update({"E": base_ts + 20, "b": [["30090", "2.0"]], "a": []})
    #4. Cancel (set at 0)
    cw.process_l2_update({"E": base_ts + 30, "b": [["30090", "0"]], "a": []})
    
    flags = cw.get_flags()

    iceberg_flags = [f for f in flags if f["type"] == "ICEBERG_CANCEL"]
    assert len(iceberg_flags) == 0
    assert flags[0]["type"] == "CANCEL_SPOOF"



#Test no iceberg if cancel outside window on the ask side
def test_no_iceberg_if_cancel_outside_window_ask():
    tuner_for_layering = DummyCancelWindowTunerForLayering()
    cw : CancelWindowProtocol = SimpleCancelWindow(
        tuner = DummyCancelWindowTuner(),
        order_age_tracker=DummyOrderAgeTracker(),
        order_book=DummyOrderBook(),
        classifier=DummyRegimeClassifier(),
        order_layering = DummyOrderLayeringDetection(),
        order_ladder_tracker = DummyOrderLadderingDetection(),
        synthetic_fill_detector = DummySyntheticFillDetection(),
        order_spoofing = DummyOrderSpoofingDetection(),
        order_cancel_density = DummyCancelDensityDetection(),
        order_iceberg_detection = DummyOrderIcebergDetection(),
        cancel_density_threshold_bid = DummyAdaptiveThreshold(),
        cancel_density_threshold_ask = DummyAdaptiveThreshold(),
        cancel_density_window_ms = DummyAdaptiveDensityWindow()



        )
    base_ts = 100000
    #simulate  3 quick size reductions at same price, no  trades
    #1. Add new ask level at 30090 with size 5.0
    cw.process_l2_update({"E": base_ts, "a": [["30090", "5.0"]], "b": []})
    #3. reduce to 2.0
    cw.process_l2_update({"E": base_ts + 20, "a": [["30090", "2.0"]], "b": []})
    #4. Cancel (set at 0)
    cw.process_l2_update({"E": base_ts + 100, "a": [["30090", "0"]], "b": []})
    
    flags = cw.get_flags()
    #No iceberg or spoof because outside window
    assert len(flags) == 0


#Test no iceberg if cancel outside window on the bid side
def test_no_iceberg_if_cancel_outside_window_bid():
    tuner_for_layering = DummyCancelWindowTunerForLayering()
    cw : CancelWindowProtocol = SimpleCancelWindow(
        tuner = DummyCancelWindowTuner(),
        order_age_tracker=DummyOrderAgeTracker(),
        order_book=DummyOrderBook(),
        classifier=DummyRegimeClassifier(),
        order_layering = DummyOrderLayeringDetection(),
        order_ladder_tracker = DummyOrderLadderingDetection(),
        synthetic_fill_detector = DummySyntheticFillDetection(),
        order_spoofing = DummyOrderSpoofingDetection(),
        order_cancel_density = DummyCancelDensityDetection(),
        order_iceberg_detection = DummyOrderIcebergDetection(),
        cancel_density_threshold_bid = DummyAdaptiveThreshold(),
        cancel_density_threshold_ask = DummyAdaptiveThreshold(),
        cancel_density_window_ms = DummyAdaptiveDensityWindow()



        )

    base_ts = 100000
    #simulate  3 quick size reductions at same price, no  trades
    #1. Add new ask level at 30090 with size 5.0
    cw.process_l2_update({"E": base_ts, "b": [["30090", "5.0"]], "a": []})
    #3. reduce to 2.0
    cw.process_l2_update({"E": base_ts + 20, "b": [["30090", "2.0"]], "a": []})
    #4. Cancel (set at 0)
    cw.process_l2_update({"E": base_ts + 100, "b": [["30090", "0"]], "a": []})
    
    flags = cw.get_flags()
    #No iceberg or spoof because outside window
    assert len(flags) == 0


#Test Cancel Density flag ask side
def test_high_cancel_density_flag_ask():
    tuner_for_layering = DummyCancelWindowTunerForLayering()
    cw : CancelWindowProtocol = SimpleCancelWindow(
        tuner = DummyCancelWindowTuner(),
        order_age_tracker=DummyOrderAgeTracker(),
        order_book=DummyOrderBook(),
        classifier=DummyRegimeClassifier(),
        order_layering = DummyOrderLayeringDetection(),
        order_ladder_tracker = DummyOrderLadderingDetection(),
        synthetic_fill_detector = DummySyntheticFillDetection(),
        order_spoofing = DummyOrderSpoofingDetection(),
        order_cancel_density = DummyCancelDensityDetection(),
        order_iceberg_detection = DummyOrderIcebergDetection(),
        cancel_density_threshold_bid = DummyAdaptiveThreshold(),
        cancel_density_threshold_ask = DummyAdaptiveThreshold(),
        cancel_density_window_ms = DummyAdaptiveDensityWindow()



        )
    cw.set_cancel_density_params(
        cancel_density_window_ms=DummyAdaptiveDensityWindow(),
        cancel_density_threshold_bid=DummyAdaptiveThreshold(),
        cancel_density_threshold_ask=DummyAdaptiveThreshold()
    )


    base_ts = 100000
    #simulate  3 quick size reductions at same price, no  trades
    #1. Add new ask level at 30090 with size 5.0
    cw.process_l2_update({"E": base_ts, "a": [["30090", "5.0"]], "b": []})
    #2. Cancel to 0
    cw.process_l2_update({"E": base_ts + 20, "a": [["30090", "0"]], "b": []})
    #3. add
    cw.process_l2_update({"E": base_ts + 30, "a": [["30090", "2.0"]], "b": []})
    #4  Cancel
    cw.process_l2_update({"E": base_ts + 40, "a": [["30090", "0"]], "b": []})
    #5. Add
    cw.process_l2_update({"E": base_ts + 50, "a": [["30090", "2.0"]], "b": []})
    #6. Cancel
    cw.process_l2_update({"E": base_ts + 60, "a": [["30090", "0"]], "b": []})
    
    flags = cw.get_flags()
    
    #Should contain HIGH_CANCEL_DENSITY
    density_flags = [f for f in flags if f["type"] ==  "CANCEL_DENSITY_SPIKE"]
    assert len(density_flags) > 0
    print("Test Passed. High_CANCEL_DENSITY triggered", density_flags)

def test_high_cancel_density_flag_ask2():
    tuner_for_layering = DummyCancelWindowTunerForLayering()
    cw : CancelWindowProtocol = SimpleCancelWindow(
        tuner = DummyCancelWindowTuner(),
        order_age_tracker=DummyOrderAgeTracker(),
        order_book=DummyOrderBook(),
        classifier=DummyRegimeClassifier(),
        order_layering = DummyOrderLayeringDetection(),
        order_ladder_tracker = DummyOrderLadderingDetection(),
        synthetic_fill_detector = DummySyntheticFillDetection(),
        order_spoofing = DummyOrderSpoofingDetection(),
        order_cancel_density = DummyCancelDensityDetection(),
        order_iceberg_detection = DummyOrderIcebergDetection(),
        cancel_density_threshold_bid = DummyAdaptiveThreshold(),
        cancel_density_threshold_ask = DummyAdaptiveThreshold(),
        cancel_density_window_ms = DummyAdaptiveDensityWindow()



        )
    cw.set_cancel_density_params(
        cancel_density_window_ms=DummyAdaptiveDensityWindow(),
        cancel_density_threshold_bid=DummyAdaptiveThreshold(),
        cancel_density_threshold_ask=DummyAdaptiveThreshold()
    )


    base_ts = 100000
    # Add and cancel 3 times within 100ms
    cw.process_l2_update({"E": base_ts, "a": [["30090", "5.0"]], "b": []})
    cw.process_l2_update({"E": base_ts + 10, "a": [["30090", "0"]], "b": []})
    cw.process_l2_update({"E": base_ts + 20, "a": [["30090", "2.0"]], "b": []})
    cw.process_l2_update({"E": base_ts + 30, "a": [["30090", "0"]], "b": []})
    cw.process_l2_update({"E": base_ts + 40, "a": [["30090", "2.0"]], "b": []})
    cw.process_l2_update({"E": base_ts + 60, "a": [["30090", "0"]], "b": []})

    # Trigger density evaluation
    cw.process_l2_update({"E": base_ts + 70, "a": [], "b": []})

    flags = cw.get_flags()
    print(flags)
    density_flags = [f for f in flags if f["type"] == "CANCEL_DENSITY_SPIKE"]
    assert density_flags, "Expected CANCEL_DENSITY_SPIKE flag"


def test_high_cancel_density_flag_ask2():
    tuner_for_layering = DummyCancelWindowTunerForLayering()
    cw : CancelWindowProtocol = SimpleCancelWindow(
        tuner = DummyCancelWindowTuner(),
        order_age_tracker=DummyOrderAgeTracker(),
        order_book=DummyOrderBook(),
        classifier=DummyRegimeClassifier(),
        order_layering = DummyOrderLayeringDetection(),
        order_ladder_tracker = DummyOrderLadderingDetection(),
        synthetic_fill_detector = DummySyntheticFillDetection(),
        order_spoofing = DummyOrderSpoofingDetection(),
        order_cancel_density = DummyCancelDensityDetection(),
        order_iceberg_detection = DummyOrderIcebergDetection(),
        cancel_density_threshold_bid = DummyAdaptiveThreshold(),
        cancel_density_threshold_ask = DummyAdaptiveThreshold(),
        cancel_density_window_ms = DummyAdaptiveDensityWindow()



        )
    cw.set_cancel_density_params(
        cancel_density_window_ms=DummyAdaptiveDensityWindow(),
        cancel_density_threshold_bid=DummyAdaptiveThreshold(),
        cancel_density_threshold_ask=DummyAdaptiveThreshold()
    )


    base_ts = 100000
    # Add and cancel 3 times within 100ms
    cw.process_l2_update({"E": base_ts, "a": [["30090", "5.0"]], "b": []})
    cw.process_l2_update({"E": base_ts + 10, "a": [["30090", "0"]], "b": []})
    cw.process_l2_update({"E": base_ts + 20, "a": [["30090", "2.0"]], "b": []})
    cw.process_l2_update({"E": base_ts + 30, "a": [["30090", "0"]], "b": []})
    cw.process_l2_update({"E": base_ts + 40, "a": [["30090", "2.0"]], "b": []})
    cw.process_l2_update({"E": base_ts + 60, "a": [["30090", "0"]], "b": []})

    # Manually trigger density evaluation
    cw._detect_cancel_density_spike(base_ts + 70)

    flags = cw.get_flags()
    print(flags)
    density_flags = [f for f in flags if f["type"] == "CANCEL_DENSITY_SPIKE"]
    assert density_flags, "Expected CANCEL_DENSITY_SPIKE flag"


#Test Cancel Density flag bid side
def test_high_cancel_density_flag_bid():
    tuner_for_layering = DummyCancelWindowTunerForLayering()
    cw : CancelWindowProtocol = SimpleCancelWindow(
        tuner = DummyCancelWindowTuner(),
        order_age_tracker=DummyOrderAgeTracker(),
        order_book=DummyOrderBook(),
        classifier=DummyRegimeClassifier(),
        order_layering = DummyOrderLayeringDetection(),
        order_ladder_tracker = DummyOrderLadderingDetection(),
        synthetic_fill_detector = DummySyntheticFillDetection(),
        order_spoofing = DummyOrderSpoofingDetection(),
        order_cancel_density = DummyCancelDensityDetection(),
        order_iceberg_detection = DummyOrderIcebergDetection(),
        cancel_density_threshold_bid = DummyAdaptiveThreshold(),
        cancel_density_threshold_ask = DummyAdaptiveThreshold(),
        cancel_density_window_ms = DummyAdaptiveDensityWindow()



        )
    cw.set_cancel_density_params(
        cancel_density_window_ms=DummyAdaptiveDensityWindow(),
        cancel_density_threshold_bid=DummyAdaptiveThreshold(),
        cancel_density_threshold_ask=DummyAdaptiveThreshold()
    )


    base_ts = 100000
    #simulate  3 quick size reductions at same price, no  trades
    #1. Add new ask level at 30090 with size 5.0
    cw.process_l2_update({"E": base_ts, "b": [["30090", "5.0"]], "a": []})
    #2. Cancel to 0
    cw.process_l2_update({"E": base_ts + 20, "b": [["30090", "0"]], "a": []})
    #3. add
    cw.process_l2_update({"E": base_ts + 30, "b": [["30090", "2.0"]], "a": []})
    #4  Cancel
    cw.process_l2_update({"E": base_ts + 40, "b": [["30090", "0"]], "a": []})
    #5. Add
    cw.process_l2_update({"E": base_ts + 50, "b": [["30090", "2.0"]], "a": []})
    #6. Cancel
    cw.process_l2_update({"E": base_ts + 60, "b": [["30090", "0"]], "a": []})
    
    flags = cw.get_flags()
    
    #Should contain HIGH_CANCEL_DENSITY
    density_flags = [f for f in flags if f["type"] ==  "CANCEL_DENSITY_SPIKE"]
    assert len(density_flags) > 0
    print("Test Passed. High_CANCEL_DENSITY triggered", density_flags)
def test_high_cancel_density_flag_bid3():
    tuner_for_layering = DummyCancelWindowTunerForLayering()
    cw : CancelWindowProtocol = SimpleCancelWindow(
        tuner = DummyCancelWindowTuner(),
        order_age_tracker=DummyOrderAgeTracker(),
        order_book=DummyOrderBook(),
        classifier=DummyRegimeClassifier(),
        order_layering = DummyOrderLayeringDetection(),
        order_ladder_tracker = DummyOrderLadderingDetection(),
        synthetic_fill_detector = DummySyntheticFillDetection(),
        order_spoofing = DummyOrderSpoofingDetection(),
        order_cancel_density = DummyCancelDensityDetection(),
        order_iceberg_detection = DummyOrderIcebergDetection(),
        cancel_density_threshold_bid = DummyAdaptiveThreshold(),
        cancel_density_threshold_ask = DummyAdaptiveThreshold(),
        cancel_density_window_ms = DummyAdaptiveDensityWindow()



        )
    cw.set_cancel_density_params(
        cancel_density_window_ms=DummyAdaptiveDensityWindow(),
        cancel_density_threshold_bid=DummyAdaptiveThreshold(),
        cancel_density_threshold_ask=DummyAdaptiveThreshold()
    )


    base_ts = 100000
    cw.process_l2_update({"E": base_ts, "b": [["30090", "5.0"]], "a": []})
    cw.process_l2_update({"E": base_ts + 10, "b": [["30090", "0"]], "a": []})
    cw.process_l2_update({"E": base_ts + 20, "b": [["30090", "2.0"]], "a": []})
    cw.process_l2_update({"E": base_ts + 30, "b": [["30090", "0"]], "a": []})
    cw.process_l2_update({"E": base_ts + 40, "b": [["30090", "2.0"]], "a": []})
    cw.process_l2_update({"E": base_ts + 60, "b": [["30090", "0"]], "a": []})

    flags = cw.get_flags()
    print(flags)
    density_flags = [f for f in flags if f["type"] == "CANCEL_DENSITY_SPIKE"]
    assert len(density_flags) > 0



#@pytest.mark.skip(reason="REGISTER_CANCEL missing positional arguments, correct it first")
#Test Compute cancel density correctly
def test_cancel_density_computation():
    tuner_for_layering = DummyCancelWindowTunerForLayering()
    cw : CancelWindowProtocol = SimpleCancelWindow(
        tuner = DummyCancelWindowTuner(),
        order_age_tracker=DummyOrderAgeTracker(),
        order_book=DummyOrderBook(),
        classifier=DummyRegimeClassifier(),
        order_layering = DummyOrderLayeringDetection(),
        order_ladder_tracker = DummyOrderLadderingDetection(),
        synthetic_fill_detector = DummySyntheticFillDetection(),
        order_spoofing = DummyOrderSpoofingDetection(),
        order_cancel_density = DummyCancelDensityDetection(),
        order_iceberg_detection = DummyOrderIcebergDetection(),
        cancel_density_threshold_bid = DummyAdaptiveThreshold(),
        cancel_density_threshold_ask = DummyAdaptiveThreshold(),
        cancel_density_window_ms = DummyAdaptiveDensityWindow()



        )

    # Simple 10 cancels at level 100, 5 at  101, 1 at 102
    for _ in range(10):
        cw.register_cancel(price=100.0, side='ask', timestamp=123456789, size=1.0)
    for _ in range(5):
        cw.register_cancel(price=102.0, side='ask', timestamp=123456789, size=1.0)
    cw.register_cancel(price=103.0, side='ask', timestamp=123456789, size=1.0)


    density = cw.get_cancel_density('ask')
    assert density[100.0] == 10
    assert density[102.0] == 5
    assert density[103.0] == 1

#@pytest.mark.skip(reason="REGISTER_CANCEL missing positional arguments, correct it first")
#Test Normalize Cancel Density
def test_normalized_cancel_density():
    tuner_for_layering = DummyCancelWindowTunerForLayering()
    cw : CancelWindowProtocol = SimpleCancelWindow(
        tuner = DummyCancelWindowTuner(),
        order_age_tracker=DummyOrderAgeTracker(),
        order_book=DummyOrderBook(),
        classifier=DummyRegimeClassifier(),
        order_layering = DummyOrderLayeringDetection(),
        order_ladder_tracker = DummyOrderLadderingDetection(),
        synthetic_fill_detector = DummySyntheticFillDetection(),
        order_spoofing = DummyOrderSpoofingDetection(),
        order_cancel_density = DummyCancelDensityDetection(),
        order_iceberg_detection = DummyOrderIcebergDetection(),
        cancel_density_threshold_bid = DummyAdaptiveThreshold(),
        cancel_density_threshold_ask = DummyAdaptiveThreshold(),
        cancel_density_window_ms = DummyAdaptiveDensityWindow()



        )
    for price, count in [(100.0, 10), (101.0, 5), (102.0, 1)]:
        for _ in range(count):
           cw.register_cancel(price=price, side='ask', timestamp=0, size=1.0)
    
    norm = cw.get_normalized_cancel_density()
    assert norm['num_cancels'] == 16
    assert norm['time_window_ms'] == 0 #since all timestamps were 0
    assert norm['cancel_density_per_sec'] > 0
    assert norm['cancel_density_per_price'] > 0
    assert norm['normalized_score'] > 0


#@pytest.mark.skip(reason="REGISTER_CAMCEL missing positional arguments, correct it")
#Test Clear Density after Flush
def test_cancel_density_flush():
    tuner_for_layering = DummyCancelWindowTunerForLayering()
    window : CancelWindowProtocol = SimpleCancelWindow(
        tuner = DummyCancelWindowTuner(),
        order_age_tracker=DummyOrderAgeTracker(),
        order_book=DummyOrderBook(),
        classifier=DummyRegimeClassifier(),
        order_layering = DummyOrderLayeringDetection(),
        order_ladder_tracker = DummyOrderLadderingDetection(),
        synthetic_fill_detector = DummySyntheticFillDetection(),
        order_spoofing = DummyOrderSpoofingDetection(),
        order_cancel_density = DummyCancelDensityDetection(),
        order_iceberg_detection = DummyOrderIcebergDetection(),
        cancel_density_threshold_bid = DummyAdaptiveThreshold(),
        cancel_density_threshold_ask = DummyAdaptiveThreshold(),
        cancel_density_window_ms = DummyAdaptiveDensityWindow()



        )
    window.register_cancel(price=100.0,side='ask', timestamp=0, size=5.0)

    window.flush()
    density = window.get_cancel_density('ask')
    assert density == {}



# Test for Icerberg Cancels
def test_iceberg_cancel_detection():
    tuner_for_layering = DummyCancelWindowTunerForLayering()
    cw : CancelWindowProtocol = SimpleCancelWindow(
        tuner = DummyCancelWindowTuner(),
        order_age_tracker=DummyOrderAgeTracker(),
        order_book=DummyOrderBook(),
        classifier=DummyRegimeClassifier(),
        order_layering = DummyOrderLayeringDetection(),
        order_ladder_tracker = DummyOrderLadderingDetection(),
        synthetic_fill_detector = DummySyntheticFillDetection(),
        order_spoofing = DummyOrderSpoofingDetection(),
        order_cancel_density = DummyCancelDensityDetection(),
        order_iceberg_detection = DummyOrderIcebergDetection(),
        cancel_density_threshold_bid = DummyAdaptiveThreshold(),
        cancel_density_threshold_ask = DummyAdaptiveThreshold(),
        cancel_density_window_ms = DummyAdaptiveDensityWindow()



        )
    ts = 100
    for _ in range(5):
        cw.register_cancel(price= 101.0, side='ask', timestamp=ts, size=2.5)
        ts += 10
    flags = cw.get_flags()
    assert any(f['type'] == 'ICEBERG_CANCEL' for f in flags)


#Test for Orderflow impact scoring
# #Test case 1: High Density + Near mid High Score = high score

#Test-only Mock
class MockOrderBook:
    def get_level_size(self, price, side):
        if price == 100.1:
            return 1.0 #Fixed Book depth
        return 1000.0
#@pytest.mark.skip(reason="UPDATE_BOOK, COMPUTE_IMPACT_SCORE not implemented yet, also has incorrect parameters for REGISTER_CANCEL")
def test_high_impact_cancel():
    tuner_for_layering = DummyCancelWindowTunerForLayering()
    cw : CancelWindowProtocol = SimpleCancelWindow(
        tuner = DummyCancelWindowTuner(),
        order_age_tracker=DummyOrderAgeTracker(),
        order_book=DummyOrderBook(),
        classifier=DummyRegimeClassifier(),
        order_layering = DummyOrderLayeringDetection(),
        order_ladder_tracker = DummyOrderLadderingDetection(),
        synthetic_fill_detector = DummySyntheticFillDetection(),
        order_spoofing = DummyOrderSpoofingDetection(),
        order_cancel_density = DummyCancelDensityDetection(),
        order_iceberg_detection = DummyOrderIcebergDetection(),
        cancel_density_threshold_bid = DummyAdaptiveThreshold(),
        cancel_density_threshold_ask = DummyAdaptiveThreshold(),
        cancel_density_window_ms = DummyAdaptiveDensityWindow()



        )
    cw.update_midprice(mid_price=100.0)
    #cw.orderbook = MockOrderBook() #Inject Mock dependency
    cw.fill_events = [{'price': 101.0, 'side':'ask'}] * 3
    cw.register_cancel(price=100.1, side='ask',timestamp=0 ,size=5)
    cw.register_cancel(price=100.1, side='ask',timestamp=0 ,size=5)
    cw.register_cancel(price=100.1, side='ask',timestamp=0, size=5)

    score = cw.compute_cancel_impact_score(price=100.1, side='ask')
    assert score >= 0.7


#Test case 2: Far from mid + low = low score
#@pytest.mark.skip(reason="UPDATE_BOOK, COMPUTE_CANCEL_IMPACT_SCORE npt implemented yet, aslo has incorrect parameters for REGISTER_CANCEL")
def test_low_impact_cancel():
    tuner_for_layering = DummyCancelWindowTunerForLayering()
    cw : CancelWindowProtocol = SimpleCancelWindow(
        tuner = DummyCancelWindowTuner(),
        order_age_tracker=DummyOrderAgeTracker(),
        order_book=DummyOrderBook(),
        classifier=DummyRegimeClassifier(),
        order_layering = DummyOrderLayeringDetection(),
        order_ladder_tracker = DummyOrderLadderingDetection(),
        synthetic_fill_detector = DummySyntheticFillDetection(),
        order_spoofing = DummyOrderSpoofingDetection(),
        order_cancel_density = DummyCancelDensityDetection(),
        order_iceberg_detection = DummyOrderIcebergDetection(),
        cancel_density_threshold_bid = DummyAdaptiveThreshold(),
        cancel_density_threshold_ask = DummyAdaptiveThreshold(),
        cancel_density_window_ms = DummyAdaptiveDensityWindow()



        )
    cw.update_midprice(mid_price=100.0)
    
    #cw.orderbook = MockOrderBook() #Inject Mock dependency
    cw.fill_events = [{'price': 101.0, 'side':'ask'}] * 3
    cw.register_cancel(price=101.0, side='ask',timestamp=123456789 ,size=1)

    score = cw.compute_cancel_impact_score(price=102.0, side='ask')
    assert score <= 0.2



#Test Case 3: Score adjusts After Book Update
#@pytest.mark.skip(reason="UPDATE_BOOK, COMPUTE_CANCEL_IMPACT_SCORE not implemented yet, also has incorrect parameters for REGISTER_CANCEL")
def test_score_changes_with_book():
    tuner_for_layering = DummyCancelWindowTunerForLayering()
    cw : CancelWindowProtocol = SimpleCancelWindow(
        tuner = DummyCancelWindowTuner(),
        order_age_tracker=DummyOrderAgeTracker(),
        order_book=DummyOrderBook(),
        classifier=DummyRegimeClassifier(),
        order_layering = DummyOrderLayeringDetection(),
        order_ladder_tracker = DummyOrderLadderingDetection(),
        synthetic_fill_detector = DummySyntheticFillDetection(),
        order_spoofing = DummyOrderSpoofingDetection(),
        order_cancel_density = DummyCancelDensityDetection(),
        order_iceberg_detection = DummyOrderIcebergDetection(),
        cancel_density_threshold_bid = DummyAdaptiveThreshold(),
        cancel_density_threshold_ask = DummyAdaptiveThreshold(),
        cancel_density_window_ms = DummyAdaptiveDensityWindow()



        )
    cw.update_midprice(mid_price=100.0)
    #cw.orderbook = MockOrderBook() #Inject Mock dependency
    cw.fill_events = [{'price': 101.0, 'side':'ask'}] * 3
    cw.register_cancel(price=101.0, side='ask',timestamp=123456789, size=1)
    score1 = cw.compute_cancel_impact_score(101.0, 'ask')

    cw.update_midprice(mid_price=100.5) #Price Moves away from cancel
    score2 = cw.compute_cancel_impact_score(100.2, 'ask')

    assert score2 < score1 # Cancel less relevant now



def test_snapshot_state_integrity():
    tuner_for_layering = DummyCancelWindowTunerForLayering()
    window : CancelWindowProtocol = SimpleCancelWindow(
        tuner = DummyCancelWindowTuner(),
        order_age_tracker=DummyOrderAgeTracker(),
        order_book=DummyOrderBook(),
        classifier=DummyRegimeClassifier(),
        order_layering = DummyOrderLayeringDetection(),
        order_ladder_tracker = DummyOrderLadderingDetection(),
        synthetic_fill_detector = DummySyntheticFillDetection(),
        order_spoofing = DummyOrderSpoofingDetection(),
        order_cancel_density = DummyCancelDensityDetection(),
        order_iceberg_detection = DummyOrderIcebergDetection(),
        cancel_density_threshold_bid = DummyAdaptiveThreshold(),
        cancel_density_threshold_ask = DummyAdaptiveThreshold(),
        cancel_density_window_ms = DummyAdaptiveDensityWindow()



        )
    window.bids = {30000.0: 1.0}
    window.asks = {30001.0: 1.0}
    window.cancel_cache = {("bid", 30000.0): (1000, 1.0)}
    window._flags.append({"type": "TEST_FLAG"})
    snapshot = window.snapshot_state()
    assert snapshot["flag_count"] == 1
    assert snapshot["bids"] == 1
    assert snapshot["asks"] == 1
    assert snapshot["cancel_cache"] == 1
    assert snapshot["flags"][0]["type"] == "TEST_FLAG"



#Window Tunning Tool Test Cases
#Test Case 1: Load Config and Apply
@pytest.mark.skip(reason="CancelConfig() function not implemented yet")
def test_config_load():
    config = CancelConfig(window_size = 2.0, density_thresh=0.2)
    cw : CancelWindowProtocol = SimpleCancelWindow(order_age_tracker=DummyOrderAgeTracker(),
        order_book=DummyOrderBook(),
        classifier=DummyRegimeClassifier()
        )
    assert cw.config.density_thresh == 0.2



#Test Case 2 Replay maintains order
@pytest.mark.skip(reason="CancelWindowReplayer() function not implemented")
def test_replay_preserves_order():
    replayer = CancelWindowReplayer(data_path='test_orderflow.csv')
    events = replayer.get_events()
    assert events[0].timestamp <= events[1].timestamp   #sorted


#Test Case 3: Tuning increases F1 score
@pytest.mark.skip(reason="SimpleCancelWindowTuner() not implemented")
def test_optimizer_improves_performance():
    tuner = SimpleCancelWindowTuner(...)
    f1_before = tuner.evaluate_baseline()
    f1_after = tuner.optimize()
    assert f1_after > f1_before

# ====== TEST SYNTHETICS

import unittest
from unittest.mock import MagicMock
from cancel_window.simple_cancel_window import SimpleCancelWindow, CancelWindowTuner
from cancel_window.order_layering_detection import OrderLayeringDetection

class TestSyntheticFillDetection(unittest.TestCase):
    def setUp(self):
        self.tuner = CancelWindowTuner(classifier= DummyRegimeClassifier())
        self.layering = OrderLayeringDetection(tuner=self.tuner, regime_classifier = MagicMock())
        self.orderbook = MagicMock()
        self.orderbook.get_best_price.side_effect = lambda side: 100.0 if side == "ask" else 99.0
        self.orderbook.get_tick_size.return_value = 0.1
        self.orderbook.get_level_size.return_value = 0.0  # ✅ critical for synthetic fill confidence
        self.orderbook.get_volatility_estimate.return_value = 0.2


        self.age_tracker = MagicMock()
        self.classifier = MagicMock()

        tuner_for_layering = DummyCancelWindowTunerForLayering()
        self.window : CancelWindowProtocol = SimpleCancelWindow(
        tuner = DummyCancelWindowTuner(),
        order_age_tracker=DummyOrderAgeTracker(),
        order_book=DummyOrderBook(),
        classifier=DummyRegimeClassifier(),
        order_layering = DummyOrderLayeringDetection(),
        order_ladder_tracker = DummyOrderLadderingDetection(),
        synthetic_fill_detector = DummySyntheticFillDetection(),
        order_spoofing = DummyOrderSpoofingDetection(),
        order_cancel_density = DummyCancelDensityDetection(),
        order_iceberg_detection = DummyOrderIcebergDetection(),
        cancel_density_threshold_bid = DummyAdaptiveThreshold(),
        cancel_density_threshold_ask = DummyAdaptiveThreshold(),
        cancel_density_window_ms = DummyAdaptiveDensityWindow(),
        market_type = "futures"



        )


        assert isinstance(self.window.order_layering_tracker, DummyOrderLayeringDetection)







    def test_synthetic_true_fill(self):
        ts = 100000
        price = 99.5
        qty = 10.0
        side = "bid"
        key = (side, price)

        # First order: high confidence, full fill
        self.window.cancel_cache[("bid", 99.5)] = (ts - 50, 10.0)
        trade_msg_1 = {"T": ts, "p": "99.5", "q": "10.0", "m": True}
        self.window.process_trade(trade_msg_1)

        # Second order: same price, lower qty, lower confidence
        self.window.cancel_cache[("bid", 99.5)] = (ts - 200, 10.0)
        trade_msg_2 = {"T": ts + 10, "p": "99.5", "q": "5.0", "m": True}
        self.window.process_trade(trade_msg_2)

        # Assert both flags
        flags = [f for f in self.window._flags if f["type"] in ("SYNTHETIC_TRUE_FILL", "SYNTHETIC_PARTIAL_FILL", "SYNTHETIC_WEAK_FILL")]
        print("Flags emitted:", [f["type"] for f in flags])
        self.assertEqual(len(flags), 2)




    def test_synthetic_partial_fill(self):
        ts = 100000
        price = 99.5
        side = "bid"
        key = (side, price)

        # Setup cancel cache
        self.window.cancel_cache[key] = (ts - 50, 10.0)

        # Process trade with partial fill
        trade_msg = {"T": ts, "p": str(price), "q": "5.0", "m": True}
        self.window.process_trade(trade_msg)

        # Assert partial fill emitted
        flags = [f for f in self.window._flags if f["type"] == "SYNTHETIC_PARTIAL_FILL"]
        print("Emitted flags:", [f["type"] for f in self.window._flags])
        self.assertEqual(len(flags), 1)



    def test_synthetic_weak_fill(self):
        ts = 100000
        price = 99.5
        qty = 1.0
        side = "bid"
        key = (side, price)

        self.window.cancel_cache[key] = (ts - 50, 10.0)
        trade_msg = {"T": ts, "p": str(price), "q": str(qty), "m": True}

        self.window.process_trade(trade_msg)

        flags = [f for f in self.window._flags if f["type"] == "SYNTHETIC_WEAK_FILL"]
        self.assertEqual(len(flags), 1)



    def test_synthetic_ladder_fill(self):
        ts = 100000
        price = 99.5
        qty = 10.0
        side = "bid"
        key = (side, price)

        self.window.cancel_cache[key] = (ts - 50, 10.0)
        self.window.active_ladder = {
            "side": side,
            "prices": {price},
            "timestamp": ts - 100,
            "filled": False
        }

        trade_msg = {"T": ts, "p": str(price), "q": str(qty), "m": True}
        self.window.process_trade(trade_msg)

        flags = [f for f in self.window._flags if f["type"] == "SYNTHETIC_LADDER_FILL"]
        self.assertEqual(len(flags), 1)



    def test_synthetic_layer_fill(self):
        ts = 100000
        prices = [99.5, 99.6, 99.7]
        side = "bid"

        for i, price in enumerate(prices):
            key = (side, price)
            orderid = self.window._next_id()
            self.window.order_ids[key] = orderid

            # Register order and cancel
            self.layering.register_order(orderid, ts - 100 - i * 10, price, 10.0, side)
            self.layering.register_cancel(orderid, ts - 50 - i * 10, "cancel", price, 10.0, side)
            self.window.cancel_cache[key] = (ts - 50 - i * 10, 10.0)

            # Process trade and register fill
            trade_msg = {"T": ts + i * 5, "p": str(price), "q": "10.0", "m": True}
            self.window.process_trade(trade_msg)
            self.layering.register_fill(orderid, ts + i * 5, "SYNTHETIC_LAYER_FILL", price, 10.0, side)

            # Force refresh layering cache
            self.layering.force_refresh_layering_cache()

            # Assert layered fills
            flags = [f for f in self.window._flags if f["type"] == "SYNTHETIC_LAYER_FILL"]
            print("Layered flags:", [(f["price"], f["type"]) for f in flags])
            self.assertEqual(len(flags), 3)





    def test_synthetic_fill_no_cancel(self):
        ts = 100000
        price = 99.9
        qty = 10.0
        side = "bid"

        trade_msg = {"T": ts, "p": str(price), "q": str(qty), "m": True}
        self.window.process_trade(trade_msg)

        flags = [f for f in self.window._flags if f["type"] == "SYNTHETIC_FILL_NO_CANCEL"]
        self.assertEqual(len(flags), 1)



    def test_synthetic_ladder_fill_expired(self):
        ts = 100000
        price = 99.5
        qty = 10.0
        side = "bid"

        self.window.active_ladder = {
            "side": side,
            "prices": {price},
            "timestamp": ts - 1000,
            "filled": False
        }

        trade_msg = {"T": ts, "p": str(price), "q": str(qty), "m": True}
        self.window.process_trade(trade_msg)

        flags = [f for f in self.window._flags if f["type"] == "SYNTHETIC_LADDER_FILL_EXPIRED"]
        self.assertEqual(len(flags), 1)


def test_synthetic_true_fill_emission():
    cw = SimpleCancelWindow(
        tuner=DummyCancelWindowTuner(),
        order_age_tracker=DummyOrderAgeTracker(),
        order_book=DummyOrderBook(),
        classifier=DummyRegimeClassifier(),
        order_layering=DummyOrderLayeringDetection(),
        order_ladder_tracker=DummyOrderLadderingDetection(),
        synthetic_fill_detector=DummySyntheticFillDetection(),
        order_spoofing=DummyOrderSpoofingDetection(),
        order_cancel_density=DummyCancelDensityDetection(),
        order_iceberg_detection=DummyOrderIcebergDetection(),
        cancel_density_threshold_bid=DummyAdaptiveThreshold(),
        cancel_density_threshold_ask=DummyAdaptiveThreshold(),
        cancel_density_window_ms=DummyAdaptiveDensityWindow(),
        market_type="futures"
    )

    # Simulate a cancel, then a trade that fully fills it
    key = ("bid", 100.0)
    cw.cancel_cache[key] = (100000, 10.0)
    trade_msg = {"T": 100050, "p": "100.0", "q": "10.0", "m": True}
    cw.process_trade(trade_msg)

    flags = [f for f in cw._flags if f["type"] == "SYNTHETIC_TRUE_FILL"]
    assert len(flags) == 1



def test_synthetic_partial_fill_emission():
    cw = SimpleCancelWindow(
        tuner=DummyCancelWindowTuner(),
        order_age_tracker=DummyOrderAgeTracker(),
        order_book=DummyOrderBook(),
        classifier=DummyRegimeClassifier(),
        order_layering=DummyOrderLayeringDetection(),
        order_ladder_tracker=DummyOrderLadderingDetection(),
        synthetic_fill_detector=DummySyntheticFillDetection(),
        order_spoofing=DummyOrderSpoofingDetection(),
        order_cancel_density=DummyCancelDensityDetection(),
        order_iceberg_detection=DummyOrderIcebergDetection(),
        cancel_density_threshold_bid=DummyAdaptiveThreshold(),
        cancel_density_threshold_ask=DummyAdaptiveThreshold(),
        cancel_density_window_ms=DummyAdaptiveDensityWindow(),
        market_type="futures"
    )

    # Simulate a cancel, then a smaller trade
    key = ("bid", 99.5)
    cw.cancel_cache[key] = (100000, 10.0)
    trade_msg = {"T": 100050, "p": "99.5", "q": "5.0", "m": True}
    cw.process_trade(trade_msg)

    flags = [f for f in cw._flags if f["type"] == "SYNTHETIC_PARTIAL_FILL"]
    assert len(flags) == 1



def test_synthetic_weak_fill_emission():
    cw = SimpleCancelWindow(
        tuner=DummyCancelWindowTuner(),
        order_age_tracker=DummyOrderAgeTracker(),
        order_book=DummyOrderBook(),
        classifier=DummyRegimeClassifier(),
        order_layering=DummyOrderLayeringDetection(),
        order_ladder_tracker=DummyOrderLadderingDetection(),
        synthetic_fill_detector=DummySyntheticFillDetection(),
        order_spoofing=DummyOrderSpoofingDetection(),
        order_cancel_density=DummyCancelDensityDetection(),
        order_iceberg_detection=DummyOrderIcebergDetection(),
        cancel_density_threshold_bid=DummyAdaptiveThreshold(),
        cancel_density_threshold_ask=DummyAdaptiveThreshold(),
        cancel_density_window_ms=DummyAdaptiveDensityWindow(),
        market_type="futures"
    )

    key = ("bid", 99.5)
    cw.cancel_cache[key] = (100000, 10.0)
    trade_msg = {"T": 100050, "p": "99.5", "q": "1.0", "m": True}
    cw.process_trade(trade_msg)

    flags = [f for f in cw._flags if f["type"] == "SYNTHETIC_WEAK_FILL"]
    assert len(flags) == 1


def test_multiple_flag_types_emitted():
    cw = SimpleCancelWindow(
        tuner=DummyCancelWindowTuner(),
        order_age_tracker=DummyOrderAgeTracker(),
        order_book=DummyOrderBook(),
        classifier=DummyRegimeClassifier(),
        order_layering=DummyOrderLayeringDetection(),
        order_ladder_tracker=DummyOrderLadderingDetection(),
        synthetic_fill_detector=DummySyntheticFillDetection(),
        order_spoofing=DummyOrderSpoofingDetection(),
        order_cancel_density=DummyCancelDensityDetection(),
        order_iceberg_detection=DummyOrderIcebergDetection(),
        cancel_density_threshold_bid=DummyAdaptiveThreshold(),
        cancel_density_threshold_ask=DummyAdaptiveThreshold(),
        cancel_density_window_ms=DummyAdaptiveDensityWindow(),
        market_type="futures"
    )

    # true fill
    cw.cancel_cache[("bid", 100.0)] = (100000, 10.0)
    cw.process_trade({"T": 100050, "p": "100.0", "q": "10.0", "m": True})
    # weak fill
    cw.cancel_cache[("bid", 99.5)] = (100000, 10.0)
    cw.process_trade({"T": 100050, "p": "99.5", "q": "1.0", "m": True})
    # no cancel
    cw.process_trade({"T": 100100, "p": "99.9", "q": "5.0", "m": True})

    types = [f["type"] for f in cw._flags]
    assert "SYNTHETIC_TRUE_FILL" in types
    assert "SYNTHETIC_WEAK_FILL" in types
    assert "SYNTHETIC_FILL_NO_CANCEL" in types
