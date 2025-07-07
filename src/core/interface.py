#src/core/interface.py
#this defines the system's core orchestrator behaviour

from abc import ABC, abstractmethod
from typing import Dict, Any

class TradingStrategy(ABC):
    @abstractmethod
    def generate_signals(self, market_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Takes in market data and output a signal dict with entries like:
        {'side': 'buy', 'price': 23250, 'qty':0.1}
        """
        pass

class OrderExecutor(ABC):
    @abstractmethod
    def place_order(self, signal:Dict[str, Any]) -> Dict[str, Any]:
        """
        Places an order given a trading signal. Returns the order response.
        """
        pass