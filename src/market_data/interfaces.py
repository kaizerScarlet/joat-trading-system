#src/market_data/interfaces.py
from abc import ABC, abstractmethod

class MarketDataFeed(ABC):
    @abstractmethod
    def connect(self): pass

    @abstractmethod
    def subscribe(self, symbol: str): pass

    @abstractmethod
    def on_message(self, message:dict): pass

    @abstractmethod
    def disconnect(self): pass