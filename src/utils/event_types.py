# utils/event_types.py
from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict


class Channel(str, Enum):
    """Uniform channel names used inside the engine."""
    BOOK = "book" # order-book depth snapshots / deltas
    TRADE = "trade" # public trades / T & S


@dataclass(slots=True)
class Event:
    """
    Normalized market-event object.
    Everything inside the engine is moved as 'Event', never raw dicts
    """
    ts: int     #epoch-ms from the exchange
    symbol: str #e.g "BTCUSDT"
    channel: Channel   #BOOK | Trade
    payload: Dict[str, Any] # original JSON payload