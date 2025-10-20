from typing import Protocol, Dict, runtime_checkable, Any

@runtime_checkable
class OrderLadderingScoringProtocol(Protocol):
     def compute_score(self, current_time: int = None) -> Dict[str, float]:
          """Compute Ladder Score"""