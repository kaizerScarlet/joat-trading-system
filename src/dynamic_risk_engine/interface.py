# src/risk/interface.py
# defines how risk is handled dynamically per JOAT system

from abc import ABC, abstractmethod 
from typing import Dict

class RiskEngine(ABC):
    @abstractmethod
    def assess(self, signal: Dict) -> bool:
        """
        Returns True if trade passes risk checks, False otherwise.
        """
        pass

    @abstractmethod
    def get_dynamic_position_size(self, signal:Dict) -> float:
        """
        Return position size based on performance metrics drawdown limits, etc.
        """
        pass