from typing import Protocol, Dict, Any, Optional, Callable, runtime_checkable, Tuple
from enum import Enum, auto


class ErrorCategory(Enum):
    NETWORK         = auto()
    AUTHENTICATION  = auto()
    RATE_LIMIT      = auto()
    ORDER_REJECTION = auto()
    VALIDATION      = auto()
    SYSTEM          = auto()
    UNKNOWN         = auto()


class ErrorSeverity(Enum):
    LOW      = auto()
    MEDIUM   = auto()
    HIGH     = auto()
    CRITICAL = auto()


@runtime_checkable
class ComprehensiveErrorRecoveryManagerProtocol(Protocol):

    on_critical_error:    Optional[Callable]
    on_recovery_success:  Optional[Callable]
    on_recovery_failure:  Optional[Callable]

    async def handle_error(
        self,
        error: Exception,
        context: Optional[Dict[str, Any]] = None,
    ) -> Tuple[bool, str]:
        """
        Handle an error and attempt recovery.

        Returns:
            (success, message) — True if recovery succeeded, False otherwise.
        """
        ...

    def should_block_order(self) -> Tuple[bool, str]:
        """
        Returns (blocked, reason).
        True if the error state is severe enough to block new order placement.
        """
        ...

    def get_recovery_stats(self) -> Dict[str, Any]:
        """Returns counts of recoveries attempted, succeeded, and failed."""
        ...

    def reset(self) -> None:
        """Reset error counters and unblock order placement."""
        ...
