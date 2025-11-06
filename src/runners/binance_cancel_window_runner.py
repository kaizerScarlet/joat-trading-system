import os
import asyncio
import time
import json
import websockets
from dotenv import load_dotenv
from colorama import Fore, Style, init
init(autoreset=True)

# Core modules
from cancel_window.simple_cancel_window import SimpleCancelWindow
from alpha_scoring.cancel_activity_scorer import CancelActivityScorer
from alpha_scoring.AlphaBlender import AlphaBlender
from alpha_scoring.alpha_pipeline import AlphaSignalPipeline
from market_data.orderbook import OrderBook
from cancel_window.simple_cancel_window import CancelWindowTunerForLayering, CancelWindowTuner
from cancel_window.order_age_distribution import OrderAgeDistribution
from alpha_scoring.order_age_scorer import OrderAgeDistributionScorer
from cancel_window.order_layering_detection import OrderLayeringDetection
from alpha_scoring.Order_layering_scorer import LayeringScoring
from dynamic_risk_engine.cognitive_market_regime_classifier import CognitiveMarketRegimeClassifier, MarketRegime
from dynamic_risk_engine.signal_confidence_calibrator import SignalConfidenceCalibrator

SYMBOL = "BTCUSDT"
BINANCE_WS_URL = "wss://stream.binance.com:9443/stream"

class BinanceCancelWindowRunner:
    def __init__(self,
                 alpha_blender: AlphaBlender,
                 alpha_signal_pipeline: AlphaSignalPipeline,
                 order_layering_scorer: LayeringScoring,
                 cancel_activity_scorer: CancelActivityScorer,
                 order_age_scorer: OrderAgeDistributionScorer,
                 orderbook: OrderBook,
                 cancel_window: SimpleCancelWindow,
                 symbol: str = SYMBOL):
        self.symbol = symbol.lower()
        self.order_age_scorer = order_age_scorer
        self.orderbook = orderbook
        self.cancel_window = cancel_window
        self.cancel_activity_scorer = cancel_activity_scorer
        self.cancel_window.orderbook = self.orderbook
        self.order_layering_scorer = order_layering_scorer
        self.alpha_signal_pipeline = alpha_signal_pipeline
        self.alpha_blender = alpha_blender
        self.ws = None

# ✅ GUI-compatible debug view collector
def collect_debug_views(runner) -> dict:
    def safe_debug(module):
        return module.get_debug_view() if module and hasattr(module, "get_debug_view") else {}

    return {
        # Core cancel window diagnostics
        "cancel_window": safe_debug(runner.cancel_window),
        "cancel_activity": safe_debug(runner.cancel_activity_scorer),
        "order_age_tracker": safe_debug(runner.cancel_window.order_age_tracker),
        "order_age_score": safe_debug(runner.order_age_scorer),
        "layering_tracker": safe_debug(runner.cancel_window.order_layering),
        "layering_score": safe_debug(runner.order_layering_scorer),
        "alpha_blender": safe_debug(runner.alpha_blender),
        "regime_classifier": safe_debug(runner.cancel_window.classifier),

        # Spoof and iceberg modules
        "cancel_density_detector": safe_debug(runner.cancel_density_detector),
        "cancel_density_score": safe_debug(runner.cancel_density_scorer),
        "laddering_tracker": safe_debug(runner.order_laddering_tracker),
        "laddering_score": safe_debug(runner.order_ladder_scorer),
        "iceberg_detector": safe_debug(runner.iceberg_detector),
        "iceberg_score": safe_debug(runner.iceberg_scorer),
        "spoofing_detector": safe_debug(runner.order_spoofing_detector),
        "spoofing_score": safe_debug(runner.order_spoofing_scorer),
        "synthetic_fill_detector": safe_debug(runner.synthetic_fill_detector),
        "synthetic_fill_score": safe_debug(runner.synthetic_fill_scorer),
    }
