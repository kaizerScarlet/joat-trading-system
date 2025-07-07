#src/infra/interface.py
#interfaces for infrastructure (exchange connectors, logging, storage)

from abc import ABC, abstractmethod
from typing import Dict, Any

class ExchangeInterface(ABC):
    @abstractmethod
    def get_orderbook(self, symbol: str) -> Dict[str, Any]:
        pass
    
    @abstractmethod
    def get_position(self, symbol: str) -> Dict[str, Any]:
        pass

    @abstractmethod
    def place_order(self, order: Dict[str, Any]) -> Dict[str, Any]:
        pass