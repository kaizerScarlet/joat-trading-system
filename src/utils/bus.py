#utils/bus.py
"""
process-local pub-sub queue so producers (webSocket feed,  replay runner)
and Consumers (CancelWindow, RiskEngine, Strategy) stay decoupled.
"""
import asyncio
from typing import cast
from utils.event_types import Event 

#Single global queue; adjust maxsize to your expected burst traffic.
BUS: asyncio.Queue[Event] = cast(
    asyncio.Queue[Event],
    asyncio.Queue(maxsize=50_000)
)