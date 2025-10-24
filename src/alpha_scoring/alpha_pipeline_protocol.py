from typing import Protocol, Dict, Any, runtime_checkable
from alpha_scoring.Alphablender_protocol import AlphaBlenderProtocol
from alpha_scoring.cancel_activity_scorer_protocol import CancelActivityScorerProtocol
from alpha_scoring.cancel_density_scorer_protocol import CancelDensityScorerProtocol
from alpha_scoring.order_age_distribution_scorer_protocol import OrderAgeDistributionScorerProtocol
from alpha_scoring.Order_layering_scorer_protocol import LayeringScoringProtocol
from alpha_scoring.order_laddering_scorer_protocol import OrderLadderingScoringProtocol
from alpha_scoring.order_iceberg_scorer_protocol import IcebergScorerProtocol
from alpha_scoring.order_spoofing_scorer_protocol import OrderSpoofingScorerProtocol
from alpha_scoring.synthetic_fill_scorer_protocol import SyntheticFillScorerProtocol

@runtime_checkable
class AlphaSignalPipelineProtocol(Protocol):
    cancel_scorer: CancelActivityScorerProtocol
    cancel_density_scorer: CancelDensityScorerProtocol
    layering_scorer: LayeringScoringProtocol
    age_scorer:OrderAgeDistributionScorerProtocol
    blender: AlphaBlenderProtocol
    order_ladder_scorer: OrderLadderingScoringProtocol
    order_spoofing_scorer: OrderSpoofingScorerProtocol
    synthetic_fill_scorer: SyntheticFillScorerProtocol
    iceberg_scorer: IcebergScorerProtocol
    blender: AlphaBlenderProtocol

    def update_market(self, timestamp: int, market_snapshot: Dict[str, Any]) -> None:
        """Feeds market snapshot into scorers and updates signal values per side."""
        ...

    def get_alpha_signal(self) -> Dict[str, float]:
        """Returns the current blended alpha signal per side."""
        ...

    def trade_feedback(self, signal_dict: Dict[str, float], pnl: float, side: str) -> None:
        """Updates signal performance tracking based on trade outcome and adjusts weights if adaptive."""
        ...

    def get_debug(self) -> Dict[str, Any]:
        """Returns internal diagnostics including weights, signals, scores, and performance history."""
        ...

    def reset(self) -> None:
        """Resets all scorers and blender state for a fresh scoring cycle."""
        ...
