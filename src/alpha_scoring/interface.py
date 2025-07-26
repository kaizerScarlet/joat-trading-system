from abc import ABC, abstractmethod


class BaseAlphaScorer(ABC):
    @abstractmethod
    def score(self, data: dict) -> float:
        pass