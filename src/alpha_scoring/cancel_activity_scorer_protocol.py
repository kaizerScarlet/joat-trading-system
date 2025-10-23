from typing import Protocol, Dict, runtime_checkable

@runtime_checkable
class CancelActivityScorerProtocol(Protocol):
    def register_events(
        self,
        timestamp: int,
        event_type: str,
        price: float,
        size: float,
        side: str,
        distance_from_best: float
    ) -> None:
        """Registers cancel-related events for scoring (spoof, fill, wipe, repost, etc)."""
        ...

    def compute_score(
        self,
        current_time: int,
        side: str
    ) -> Dict[str, float]:
        """Returns normalized cancel aggression scores per side based on recent activity."""
        ...

    def reset(self) -> None:
        """Clears internal state and resets EMA smoothing."""
        ...


    def get_debug_view(self) -> Dict[str, Dict]:
        """Returns internal state for debugging purposes."""
        ...
        
