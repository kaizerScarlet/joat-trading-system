from typing import Protocol, Dict, Any, List, Tuple, Optional, runtime_checkable
from dynamic_risk_engine.cognitive_market_regime_classifier_protocol import CognitiveMarketRegimeClassifierProtocol, MarketRegime
from market_data.orderbook_protocol import OrderBookProtocol
from cancel_window.order_age_distribution_protocol import OrderAgeDistributionProtocol
from cancel_window.order_layering_detection_protocol import OrderLayeringDetectionProtocol
from cancel_window.order_laddering_detection_protocol import OrderLadderingDetectionProtocol
from cancel_window.synthetic_fill_detector_protocol import SyntheticFillDetectorProtocol
from cancel_window.order_spoofing_detection_protocol import OrderSpoofingDetectionProtocol
from cancel_window.cancel_denisty_detection_protocol import CancelDensityDetectionProtocol
from cancel_window.order_iceberg_detection_protocol import OrderIcebergDetectionProtocol
from cancel_window.cancel_window_tuner import CancelWindowTuner
from cancel_window.simple_cancel_window import AdaptiveDensityWindow , AdaptiveThreshold




@runtime_checkable
class CancelWindowProtocol(Protocol):
    tuner: CancelWindowTuner | None
    order_layering: OrderLayeringDetectionProtocol
    order_ladder_tracker: OrderLadderingDetectionProtocol
    synthetic_fill_detector: SyntheticFillDetectorProtocol
    order_spoofing: OrderSpoofingDetectionProtocol
    order_cancel_density: CancelDensityDetectionProtocol
    order_iceberg_detection: OrderIcebergDetectionProtocol
    order_age_tracker: OrderAgeDistributionProtocol
    order_book: OrderBookProtocol
    classifier: CognitiveMarketRegimeClassifierProtocol


    adaptive: bool
    window_ms: int | None

    _flags: List[Dict[str, Any]]
    bids: Dict[float, float]
    asks: Dict[float, float]

    add_ts: Dict[tuple[str, float], int]

    order_ids: Dict[Tuple[str, float], str]

    cancel_cache: Dict[Tuple[str, float], Tuple[int, float]]

    reduction_history: Dict[Tuple[str, float], List[float]]

    cancel_timestamps: Dict[Tuple[str, float], List[int]]

    reduction_timestamps: Dict[Tuple[str, float], List[int]]

    cancel_density_threshold_bid: AdaptiveThreshold
    cancel_density_threshold_ask: AdaptiveThreshold
    cancel_density_window_ms: AdaptiveDensityWindow


    cancel_events: list
    fill_events: list
    midprice: float

    market_type: str

    

    def _next_id(self) -> str:
        """Generates Unique ID for orders"""
        ...
        
    def process_l2_update(self, msg: Dict[str, Any]) -> None:
        """Processes L2 depth updates and detects cancel-based spoofing, iceberg, laddering, and density flags."""
        ...

    def process_trade(self, trade_msg: Dict[str, Any]) -> None:
        """Processes trade messages and matches them to recent cancels to flag fills and spoof behavior."""
        ...

    def register_cancel(self, timestamp: int, price: float, side: str, size: float) -> None:
        """Registers a cancel event and triggers spoof detection features."""
        ...

    def flush_flags(self) -> List[Dict[str, Any]]:
        """Returns and clears current flags (destructive). Use in streaming mode."""
        ...

    def get_flags(self) -> List[Dict[str, Any]]:
        """Returns current flags without clearing (non-destructive). Use for inspection/debugging."""
        ...

    def snapshot_state(self) -> Dict[str, Any]:
        """Returns a snapshot of internal state including flags, cancel cache, and density metrics."""
        ...

    def compute_cancel_density(self) -> Dict[Tuple[str, float], int]:
        """Computes cancel density per (side, price) level within the current window."""
        ...

    def get_cancel_density(self, side: str) -> Dict[float, int]:
        """Returns cancel density per price for a given side."""
        ...

    def get_normalized_cancel_density(self) -> Dict[str, float]:
        """Returns normalized cancel density metrics and composite score."""
        ...

    def compute_cancel_impact_score(self, price: float, side: str) -> float:
        """Returns a weighted score for cancel impact at a given price and side."""
        ...

    def set_cancel_density_params(self, initial_threshold: int, initial_window_ms: int) -> None:
        """Sets initial cancel density thresholds and evaluation window."""
        ...

    def get_window_ms(self) -> int:
        """Returns the current adaptive cancel window in milliseconds."""
        ...

    def update_midprice(self, mid_price: Optional[float] = None) -> float:
        """Updates or retrieves midprice for scoring purposes."""
        ...

    def flush(self) -> None:
        """Clears cancel and fill event buffers."""
        ...
    def get_debug_view(self) -> Dict[str, Any]:
        """Returns a debug view of internal parameters and state."""
        ...
    def reset(self):
        """Resets internal state and parameters to initial configuration."""
        ...
