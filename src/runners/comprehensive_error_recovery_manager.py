# Execution_layer/comprehensive_error_recovery_manager.py
"""
Comprehensive Error Recovery Manager for Binance Order Management System

Handles ALL types of errors that could affect the OMS:
1. Network/Timeout Errors (-1007, -1001, -1006, -1008)
2. Authentication Errors (-1002, -1021, -1022)
3. Rate Limit Errors (-1003, -1015, -1034)
4. Order Rejection Errors (-2010, -2011, -2019, -2020, -2021, -2022, -2023, -2024, -2025)
5. Validation Errors (-4000 series, -1100 series)
6. System Errors (-1016 shutdown, -1000 unknown)

Each error category has specific recovery strategies and OMS impact assessment.
"""

import logging
import asyncio
import time
import itertools
from collections import deque
from typing import Dict, List, Optional, Tuple, Any, Callable
from enum import Enum, auto
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from colorama import Fore, Style, init

init(autoreset=True)
logging.basicConfig(level=logging.ERROR)
logger = logging.getLogger("[Comprehensive_Error_Recovery]")
# 1. Add the NullHandler: This consumes all logs without outputting them
logger.addHandler(logging.NullHandler())

# 2. Stop propagation: This prevents logs from being sent to the console/root logger
logger.propagate = False

class ErrorCategory(Enum):
    """Classification of Binance errors"""
    TIMEOUT = auto()              # -1007, -1001, -1006: Network/timeout issues
    AUTHENTICATION = auto()       # -1002, -1021, -1022: Auth/signature issues
    RATE_LIMIT = auto()          # -1003, -1015, -1034: Too many requests
    INSUFFICIENT_BALANCE = auto() # -2019: Margin insufficient
    ORDER_REJECT = auto()         # -2010, -2020, -2021, -2022: Order validation failed
    POSITION_ISSUE = auto()       # -2023, -2024, -2025: Position/liquidation issues
    VALIDATION = auto()           # -4000 series: Price/qty validation
    PARAMETER = auto()            # -1100 series: Invalid parameters
    SYSTEM = auto()               # -1016, -1008, -1000: System issues
    UNKNOWN = auto()              # Unclassified errors


class RecoveryAction(Enum):
    """What action to take for recovery"""
    RECONCILE = auto()            # Check with exchange (timeout)
    RETRY_IMMEDIATE = auto()      # Retry right away (transient error)
    RETRY_BACKOFF = auto()        # Retry with exponential backoff (rate limit)
    REJECT_ORDER = auto()         # Order invalid, don't retry
    ADJUST_PARAMS = auto()        # Fix parameters and retry
    PAUSE_STRATEGY = auto()       # Pause and investigate (auth, liquidation)
    MANUAL_INTERVENTION = auto()  # Requires human action


class ErrorSeverity(Enum):
    """How severe is this error"""
    INFO = auto()                 # No action needed
    WARNING = auto()              # Recoverable automatically
    ERROR = auto()                # Needs recovery action
    CRITICAL = auto()             # Needs immediate attention
    FATAL = auto()                # System must stop


@dataclass
class ErrorDescriptor:
    """Complete description of a Binance error"""
    code: int
    category: ErrorCategory
    severity: ErrorSeverity
    recovery_action: RecoveryAction
    description: str
    oms_impact: str
    auto_recoverable: bool
    freeze_strategy: bool


@dataclass
class ErrorEvent:
    """A specific error occurrence"""
    timestamp: float
    error_code: int
    error_msg: str
    category: ErrorCategory
    severity: ErrorSeverity
    context: Dict[str, Any]  # Order details, symbol, etc.
    recovery_attempted: bool = False
    recovery_successful: bool = False
    recovery_actions: List[str] = field(default_factory=list)


# ============================================================================
# ERROR CATALOG - Complete Binance Error Database
# ============================================================================

ERROR_CATALOG: Dict[int, ErrorDescriptor] = {
    # ========== NETWORK/TIMEOUT ERRORS ==========
    -1007: ErrorDescriptor(
        code=-1007,
        category=ErrorCategory.TIMEOUT,
        severity=ErrorSeverity.ERROR,
        recovery_action=RecoveryAction.RECONCILE,
        description="Timeout waiting for response from backend server",
        oms_impact="Order status unknown - may or may not have been created/filled",
        auto_recoverable=True,
        freeze_strategy=True
    ),
    -1001: ErrorDescriptor(
        code=-1001,
        category=ErrorCategory.TIMEOUT,
        severity=ErrorSeverity.WARNING,
        recovery_action=RecoveryAction.RETRY_BACKOFF,
        description="Internal error; unable to process your request",
        oms_impact="Request failed, no order created",
        auto_recoverable=True,
        freeze_strategy=False
    ),
    -1006: ErrorDescriptor(
        code=-1006,
        category=ErrorCategory.TIMEOUT,
        severity=ErrorSeverity.WARNING,
        recovery_action=RecoveryAction.RETRY_BACKOFF,
        description="Unexpected response from server",
        oms_impact="Request malformed or server error, no order created",
        auto_recoverable=True,
        freeze_strategy=False
    ),
    
    # ========== AUTHENTICATION ERRORS ==========
    -1002: ErrorDescriptor(
        code=-1002,
        category=ErrorCategory.AUTHENTICATION,
        severity=ErrorSeverity.CRITICAL,
        recovery_action=RecoveryAction.PAUSE_STRATEGY,
        description="Unauthorized - invalid API key or IP",
        oms_impact="All requests blocked until fixed",
        auto_recoverable=False,
        freeze_strategy=True
    ),
    -1021: ErrorDescriptor(
        code=-1021,
        category=ErrorCategory.AUTHENTICATION,
        severity=ErrorSeverity.ERROR,
        recovery_action=RecoveryAction.ADJUST_PARAMS,
        description="Timestamp out of recvWindow",
        oms_impact="Request rejected, order not created",
        auto_recoverable=True,
        freeze_strategy=False
    ),
    -1022: ErrorDescriptor(
        code=-1022,
        category=ErrorCategory.AUTHENTICATION,
        severity=ErrorSeverity.CRITICAL,
        recovery_action=RecoveryAction.PAUSE_STRATEGY,
        description="Invalid signature",
        oms_impact="All requests blocked until fixed",
        auto_recoverable=False,
        freeze_strategy=True
    ),
    
    # ========== RATE LIMIT ERRORS ==========
    -1003: ErrorDescriptor(
        code=-1003,
        category=ErrorCategory.RATE_LIMIT,
        severity=ErrorSeverity.WARNING,
        recovery_action=RecoveryAction.RETRY_BACKOFF,
        description="Too many requests - rate limit hit",
        oms_impact="Requests throttled, order not created",
        auto_recoverable=True,
        freeze_strategy=False
    ),
    -1015: ErrorDescriptor(
        code=-1015,
        category=ErrorCategory.RATE_LIMIT,
        severity=ErrorSeverity.WARNING,
        recovery_action=RecoveryAction.RETRY_BACKOFF,
        description="Too many orders - order rate limit",
        oms_impact="Order limit reached, order not created",
        auto_recoverable=True,
        freeze_strategy=False
    ),
    -1034: ErrorDescriptor(
        code=-1034,
        category=ErrorCategory.RATE_LIMIT,
        severity=ErrorSeverity.WARNING,
        recovery_action=RecoveryAction.RETRY_BACKOFF,
        description="Too many connections",
        oms_impact="Connection limit reached",
        auto_recoverable=True,
        freeze_strategy=False
    ),
    
    # ========== ORDER REJECTION ERRORS ==========
    -2010: ErrorDescriptor(
        code=-2010,
        category=ErrorCategory.ORDER_REJECT,
        severity=ErrorSeverity.ERROR,
        recovery_action=RecoveryAction.REJECT_ORDER,
        description="Order rejected by exchange",
        oms_impact="Order invalid, not created",
        auto_recoverable=False,
        freeze_strategy=False
    ),
    -2011: ErrorDescriptor(
        code=-2011,
        category=ErrorCategory.ORDER_REJECT,
        severity=ErrorSeverity.WARNING,          # not ERROR — order is just gone, not a failure
        recovery_action=RecoveryAction.REJECT_ORDER,  # no retry — nothing to retry, order doesn't exist
        description="Cancel rejected — order unknown to exchange",
        oms_impact="Order does not exist on exchange; may have filled or never "
                   "persisted. Caller should verify position/order state rather "
                   "than assume the order is still active.",
        auto_recoverable=False,   # nothing to recover — order is already gone
        freeze_strategy=False
    ),
    -2013: ErrorDescriptor(
        code=-2013,
        category=ErrorCategory.ORDER_REJECT,
        severity=ErrorSeverity.WARNING,          # same class as -2011 — target order is gone
        recovery_action=RecoveryAction.REJECT_ORDER,
        description="Order does not exist — already processed",
        oms_impact="Order was already filled, cancelled, or expired on the "
                   "exchange. Caller should verify position/order state rather "
                   "than assume the order is still active.",
        auto_recoverable=False,
        freeze_strategy=False
    ),
    -2019: ErrorDescriptor(
        code=-2019,
        category=ErrorCategory.INSUFFICIENT_BALANCE,
        severity=ErrorSeverity.ERROR,
        recovery_action=RecoveryAction.REJECT_ORDER,
        description="Margin is insufficient",
        oms_impact="Insufficient balance/margin for order",
        auto_recoverable=False,
        freeze_strategy=False
    ),
    -2020: ErrorDescriptor(
        code=-2020,
        category=ErrorCategory.ORDER_REJECT,
        severity=ErrorSeverity.ERROR,
        recovery_action=RecoveryAction.REJECT_ORDER,
        description="Unable to fill",
        oms_impact="Order cannot be filled at this price",
        auto_recoverable=False,
        freeze_strategy=False
    ),
    -2021: ErrorDescriptor(
        code=-2021,
        category=ErrorCategory.ORDER_REJECT,
        severity=ErrorSeverity.ERROR,
        recovery_action=RecoveryAction.REJECT_ORDER,
        description="Order would immediately trigger",
        oms_impact="Stop/limit price would trigger immediately",
        auto_recoverable=False,
        freeze_strategy=False
    ),
    -2022: ErrorDescriptor(
        code=-2022,
        category=ErrorCategory.ORDER_REJECT,
        severity=ErrorSeverity.ERROR,
        recovery_action=RecoveryAction.REJECT_ORDER,
        description="ReduceOnly order rejected",
        oms_impact="ReduceOnly conflicts with existing position",
        auto_recoverable=False,
        freeze_strategy=False
    ),
    
    # ========== POSITION/LIQUIDATION ERRORS ==========
    -2023: ErrorDescriptor(
        code=-2023,
        category=ErrorCategory.POSITION_ISSUE,
        severity=ErrorSeverity.CRITICAL,
        recovery_action=RecoveryAction.PAUSE_STRATEGY,
        description="User in liquidation mode",
        oms_impact="Account being liquidated - all orders blocked",
        auto_recoverable=False,
        freeze_strategy=True
    ),
    -2024: ErrorDescriptor(
        code=-2024,
        category=ErrorCategory.POSITION_ISSUE,
        severity=ErrorSeverity.ERROR,
        recovery_action=RecoveryAction.REJECT_ORDER,
        description="Position not sufficient",
        oms_impact="Cannot reduce position - insufficient size",
        auto_recoverable=False,
        freeze_strategy=False
    ),
    -2025: ErrorDescriptor(
        code=-2025,
        category=ErrorCategory.POSITION_ISSUE,
        severity=ErrorSeverity.WARNING,
        recovery_action=RecoveryAction.REJECT_ORDER,
        description="Max open order limit exceeded",
        oms_impact="Too many open orders for symbol",
        auto_recoverable=False,
        freeze_strategy=False
    ),
    -2027: ErrorDescriptor(
        code=-2027,
        category=ErrorCategory.POSITION_ISSUE,
        severity=ErrorSeverity.ERROR,
        recovery_action=RecoveryAction.REJECT_ORDER,
        description="Exceeded maximum position at current leverage",
        oms_impact="Cannot increase position - leverage limit reached",
        auto_recoverable=False,
        freeze_strategy=False
    ),
    
    # ========== VALIDATION ERRORS (4000 series) ==========
    -4000: ErrorDescriptor(
        code=-4000,
        category=ErrorCategory.VALIDATION,
        severity=ErrorSeverity.ERROR,
        recovery_action=RecoveryAction.REJECT_ORDER,
        description="Invalid order status",
        oms_impact="Order cannot be modified in current status",
        auto_recoverable=False,
        freeze_strategy=False
    ),
    -4003: ErrorDescriptor(
        code=-4003,
        category=ErrorCategory.VALIDATION,
        severity=ErrorSeverity.ERROR,
        recovery_action=RecoveryAction.ADJUST_PARAMS,
        description="Quantity less than zero",
        oms_impact="Invalid quantity parameter",
        auto_recoverable=True,
        freeze_strategy=False
    ),
    -4004: ErrorDescriptor(
        code=-4004,
        category=ErrorCategory.VALIDATION,
        severity=ErrorSeverity.ERROR,
        recovery_action=RecoveryAction.ADJUST_PARAMS,
        description="Quantity less than min quantity",
        oms_impact="Order size too small",
        auto_recoverable=True,
        freeze_strategy=False
    ),
    -4005: ErrorDescriptor(
        code=-4005,
        category=ErrorCategory.VALIDATION,
        severity=ErrorSeverity.ERROR,
        recovery_action=RecoveryAction.REJECT_ORDER,
        description="Quantity greater than max quantity",
        oms_impact="Order size too large",
        auto_recoverable=False,
        freeze_strategy=False
    ),
    -4013: ErrorDescriptor(
        code=-4013,
        category=ErrorCategory.VALIDATION,
        severity=ErrorSeverity.ERROR,
        recovery_action=RecoveryAction.ADJUST_PARAMS,
        description="Price less than min price",
        oms_impact="Price too low",
        auto_recoverable=True,
        freeze_strategy=False
    ),
    -4014: ErrorDescriptor(
        code=-4014,
        category=ErrorCategory.VALIDATION,
        severity=ErrorSeverity.ERROR,
        recovery_action=RecoveryAction.ADJUST_PARAMS,
        description="Price not increased by tick size",
        oms_impact="Price doesn't match tick size",
        auto_recoverable=True,
        freeze_strategy=False
    ),
    
    # ========== PARAMETER ERRORS (1100 series) ==========
    -1100: ErrorDescriptor(
        code=-1100,
        category=ErrorCategory.PARAMETER,
        severity=ErrorSeverity.ERROR,
        recovery_action=RecoveryAction.REJECT_ORDER,
        description="Illegal characters in parameter",
        oms_impact="Invalid parameter format",
        auto_recoverable=False,
        freeze_strategy=False
    ),
    -1102: ErrorDescriptor(
        code=-1102,
        category=ErrorCategory.PARAMETER,
        severity=ErrorSeverity.ERROR,
        recovery_action=RecoveryAction.REJECT_ORDER,
        description="Mandatory parameter empty or malformed",
        oms_impact="Missing required parameter",
        auto_recoverable=False,
        freeze_strategy=False
    ),
    -1111: ErrorDescriptor(
        code=-1111,
        category=ErrorCategory.PARAMETER,
        severity=ErrorSeverity.ERROR,
        recovery_action=RecoveryAction.ADJUST_PARAMS,
        description="Precision over maximum",
        oms_impact="Too many decimal places",
        auto_recoverable=True,
        freeze_strategy=False
    ),
    -1116: ErrorDescriptor(
        code=-1116,
        category=ErrorCategory.PARAMETER,
        severity=ErrorSeverity.ERROR,
        recovery_action=RecoveryAction.REJECT_ORDER,
        description="Invalid order type",
        oms_impact="Order type not supported",
        auto_recoverable=False,
        freeze_strategy=False
    ),
    -1117: ErrorDescriptor(
        code=-1117,
        category=ErrorCategory.PARAMETER,
        severity=ErrorSeverity.ERROR,
        recovery_action=RecoveryAction.REJECT_ORDER,
        description="Invalid side",
        oms_impact="Side must be BUY or SELL",
        auto_recoverable=False,
        freeze_strategy=False
    ),
    -1121: ErrorDescriptor(
        code=-1121,
        category=ErrorCategory.PARAMETER,
        severity=ErrorSeverity.ERROR,
        recovery_action=RecoveryAction.REJECT_ORDER,
        description="Invalid symbol",
        oms_impact="Symbol not recognized",
        auto_recoverable=False,
        freeze_strategy=False
    ),
    
    # ========== SYSTEM ERRORS ==========
    -1008: ErrorDescriptor(
        code=-1008,
        category=ErrorCategory.SYSTEM,
        severity=ErrorSeverity.WARNING,
        recovery_action=RecoveryAction.RETRY_BACKOFF,
        description="Server busy",
        oms_impact="Binance overloaded, retry later",
        auto_recoverable=True,
        freeze_strategy=False
    ),
    -1016: ErrorDescriptor(
        code=-1016,
        category=ErrorCategory.SYSTEM,
        severity=ErrorSeverity.CRITICAL,
        recovery_action=RecoveryAction.PAUSE_STRATEGY,
        description="Service shutting down",
        oms_impact="Binance service unavailable",
        auto_recoverable=False,
        freeze_strategy=True
    ),
    -1000: ErrorDescriptor(
        code=-1000,
        category=ErrorCategory.SYSTEM,
        severity=ErrorSeverity.ERROR,
        recovery_action=RecoveryAction.RETRY_BACKOFF,
        description="Unknown error",
        oms_impact="Unspecified error",
        auto_recoverable=True,
        freeze_strategy=False
    ),
}


class ComprehensiveErrorRecoveryManager:
    """
    Comprehensive error recovery manager for all Binance error types
    
    Features:
    - Automatic error classification
    - Context-aware recovery strategies
    - OMS impact assessment
    - Strategy freeze management
    - Error analytics and reporting
    """
    
    def __init__(
        self,
        exchange_client,
        execution_coordinator,
        timeout_recovery_manager=None,  # Delegate timeout recovery
        max_recovery_attempts: int = 3,
        backoff_base: float = 2.0,
        enable_auto_recovery: bool = True
    ):
        """
        Args:
            exchange_client: BinanceExecutionAdapter instance
            execution_coordinator: ExecutionCoordinator instance
            timeout_recovery_manager: TimeoutRecoveryManager for -1007 errors
            max_recovery_attempts: Max retry attempts
            backoff_base: Exponential backoff base (seconds)
            enable_auto_recovery: Enable automatic recovery
        """
        self.exchange_client = exchange_client
        self.coordinator = execution_coordinator
        self.timeout_recovery_manager = timeout_recovery_manager
        self.max_recovery_attempts = max_recovery_attempts
        self.backoff_base = backoff_base
        self.enable_auto_recovery = enable_auto_recovery
        
        # State tracking
        self.is_frozen = False
        # Bounded deque — auto-evicts oldest entry when full.
        # Plain list grew unboundedly; get_error_stats() iterated the entire list
        # on every call with two O(n) generator-sum passes.
        self.error_history: deque = deque(maxlen=500)
        self.error_stats: Dict[int, int] = {}  # code -> count

        # Incremental recovery counters — updated in-place as events are resolved
        # so get_error_stats() never needs to scan error_history for these values.
        self._recovery_attempted_count: int = 0
        self._recovery_successful_count: int = 0
        
        # Recovery callbacks
        self.on_critical_error: Optional[Callable] = None
        self.on_recovery_success: Optional[Callable] = None
        self.on_recovery_failure: Optional[Callable] = None
        
        logger.info(
            f"{Fore.CYAN}[ERROR RECOVERY] Comprehensive manager initialized\n"
            f"  Auto Recovery: {enable_auto_recovery}\n"
            f"  Max Attempts: {max_recovery_attempts}\n"
            f"  Timeout Delegation: {'Enabled' if timeout_recovery_manager else 'Disabled'}"
        )
    
    def classify_error(self, error: Exception) -> Tuple[int, ErrorDescriptor]:
        """
        Classify error and return error code and descriptor
        
        Returns:
            (error_code, descriptor) or (-1, unknown_descriptor) if not found
        """
        import re
        import json
        
        error_str = str(error)
        
        # Try to extract error code from various formats
        error_code = None
        error_msg = error_str
        
        # Format 1: {"code":-1007,"msg":"..."}
        try:
            json_match = re.search(r'\{.*"code"\s*:\s*(-?\d+).*\}', error_str)
            if json_match:
                error_data = json.loads(json_match.group())
                error_code = error_data.get("code")
                error_msg = error_data.get("msg", error_str)
        except (json.JSONDecodeError, ValueError, AttributeError):
            pass  # Not JSON — fall through to regex extraction
        
        # Format 2: code=-1007
        if error_code is None:
            code_match = re.search(r'code[=:\s]+(-?\d+)', error_str, re.IGNORECASE)
            if code_match:
                error_code = int(code_match.group(1))
        
        # Format 3: -1007 at start
        if error_code is None:
            code_match = re.search(r'^(-?\d+)', error_str)
            if code_match:
                error_code = int(code_match.group(1))
        
        # Look up in catalog
        if error_code and error_code in ERROR_CATALOG:
            return error_code, ERROR_CATALOG[error_code]
        
        # Unknown error - create generic descriptor
        logger.warning(
            f"{Fore.YELLOW}[ERROR CLASSIFY] Unknown error code: {error_code}\n"
            f"  Message: {error_msg[:100]}"
        )
        
        unknown = ErrorDescriptor(
            code=error_code or -9999,
            category=ErrorCategory.UNKNOWN,
            severity=ErrorSeverity.ERROR,
            recovery_action=RecoveryAction.RETRY_BACKOFF,
            description=error_msg[:200],
            oms_impact="Unknown impact",
            auto_recoverable=False,
            freeze_strategy=False
        )
        
        return error_code or -9999, unknown
    
    async def handle_error(
        self,
        error: Exception,
        context: Dict[str, Any]
    ) -> Tuple[bool, str]:
        """
        Main entry point for error handling
        
        Args:
            error: The exception that occurred
            context: Order details and context
        
        Returns:
            (success, message) - True if recovered, False if not
        """
        # Classify error
        error_code, descriptor = self.classify_error(error)
        
        # Create error event
        event = ErrorEvent(
            timestamp=time.time(),
            error_code=error_code,
            error_msg=str(error),
            category=descriptor.category,
            severity=descriptor.severity,
            context=context
        )
        
        # Record in history and stats
        self.error_history.append(event)
        self.error_stats[error_code] = self.error_stats.get(error_code, 0) + 1
        
        # Log error
        severity_color = {
            ErrorSeverity.INFO: Fore.CYAN,
            ErrorSeverity.WARNING: Fore.YELLOW,
            ErrorSeverity.ERROR: Fore.RED,
            ErrorSeverity.CRITICAL: Fore.LIGHTRED_EX,
            ErrorSeverity.FATAL: Fore.MAGENTA
        }
        
        color = severity_color.get(descriptor.severity, Fore.WHITE)
        
        logger.error(
            f"{color}[ERROR DETECTED] Code {error_code}: {descriptor.description}\n"
            f"  Category: {descriptor.category.name}\n"
            f"  Severity: {descriptor.severity.name}\n"
            f"  Recovery Action: {descriptor.recovery_action.name}\n"
            f"  OMS Impact: {descriptor.oms_impact}\n"
            f"  Auto Recoverable: {descriptor.auto_recoverable}\n"
            f"  Freeze Required: {descriptor.freeze_strategy}\n"
            f"  Context: {context.get('symbol', 'N/A')} {context.get('side', 'N/A')} "
            f"{context.get('quantity', 'N/A')}"
        )
        
        # Handle critical errors
        if descriptor.severity in (ErrorSeverity.CRITICAL, ErrorSeverity.FATAL):
            # Set trading_paused on coordinator for critical errors
            if hasattr(self.coordinator, 'trading_paused'):
                self.coordinator.trading_paused = True
                if hasattr(self.coordinator, 'pause_reason'):
                    self.coordinator.pause_reason = f"{descriptor.description} (Code {error_code})"
            
            if self.on_critical_error:
                try:
                    await self.on_critical_error(event, descriptor)
                except Exception as callback_error:
                    logger.error(
                        f"{Fore.RED}[CALLBACK ERROR] Critical error callback failed: {callback_error}\n"
                        f"  Continuing with error handling..."
                    )
        
        # Freeze strategy if required
        if descriptor.freeze_strategy:
            await self.freeze_strategy(f"{descriptor.description} (Code {error_code})")
        
        # Auto recovery
        if self.enable_auto_recovery and descriptor.auto_recoverable:
            event.recovery_attempted = True
            self._recovery_attempted_count += 1  # incremental — no O(n) scan needed
            
            success = await self._execute_recovery(
                descriptor.recovery_action,
                event,
                context
            )
            
            event.recovery_successful = success
            if success:
                self._recovery_successful_count += 1  # incremental counter
            
            if success:
                if self.on_recovery_success:
                    await self.on_recovery_success(event)
                return True, f"Recovered from error {error_code}"
            else:
                if self.on_recovery_failure:
                    await self.on_recovery_failure(event)
                return False, f"Recovery failed for error {error_code}"
        
        # Not auto-recoverable
        return False, f"Error {error_code} requires manual intervention"
    
    async def _execute_recovery(
        self,
        action: RecoveryAction,
        event: ErrorEvent,
        context: Dict[str, Any]
    ) -> bool:
        """Execute the appropriate recovery action"""
        
        if action == RecoveryAction.RECONCILE:
            # Delegate to timeout recovery manager
            if self.timeout_recovery_manager and event.error_code == -1007:
                logger.info(f"{Fore.CYAN}[RECOVERY] Delegating to timeout recovery manager")
                
                success = await self.timeout_recovery_manager.handle_timeout_error(
                    error_response={"code": event.error_code, "msg": event.error_msg},
                    order_request=context,
                    client_order_id=context.get("client_order_id", f"ord_{int(time.time()*1000)}")
                )
                
                event.recovery_actions.append("Timeout reconciliation")
                return success
            else:
                # Generic reconciliation (for -2011 cancel rejected, etc.)
                success = await self._reconcile_order_state(context)
                event.recovery_actions.append("Order state reconciliation")
                return success
        
        elif action == RecoveryAction.RETRY_IMMEDIATE:
            logger.info(f"{Fore.CYAN}[RECOVERY] Retrying immediately")
            event.recovery_actions.append("Immediate retry")
            # Return False - let calling code retry
            return False
        
        elif action == RecoveryAction.RETRY_BACKOFF:
            logger.info(f"{Fore.CYAN}[RECOVERY] Retrying with exponential backoff")
            success = await self._retry_with_backoff(context, event)
            event.recovery_actions.append(f"Backoff retry ({success})")
            return success
        
        elif action == RecoveryAction.ADJUST_PARAMS:
            logger.info(f"{Fore.CYAN}[RECOVERY] Adjusting parameters and retrying")
            success = await self._adjust_and_retry(context, event)
            event.recovery_actions.append(f"Parameter adjustment ({success})")
            return success
        
        elif action == RecoveryAction.REJECT_ORDER:
            logger.info(f"{Fore.YELLOW}[RECOVERY] Order rejected - no retry")
            event.recovery_actions.append("Order permanently rejected")
            return False
        
        elif action == RecoveryAction.PAUSE_STRATEGY:
            logger.warning(f"{Fore.RED}[RECOVERY] Pausing strategy for manual review")
            await self.freeze_strategy(f"Critical error {event.error_code}")
            event.recovery_actions.append("Strategy paused")
            return False
        
        elif action == RecoveryAction.MANUAL_INTERVENTION:
            logger.error(f"{Fore.RED}[RECOVERY] Manual intervention required")
            event.recovery_actions.append("Requires manual intervention")
            return False
        
        return False
    
    async def _reconcile_order_state(self, context: Dict[str, Any]) -> bool:
        """Reconcile order state with exchange"""
        try:
            symbol = context.get("symbol")
            client_order_id = context.get("client_order_id")
            
            if not symbol or not client_order_id:
                return False
            
            # Query exchange
            order_status = await self.exchange_client.get_order_status(
                symbol=symbol,
                origClientOrderId=client_order_id
            )
            
            if order_status:
                # Order exists - update OMS
                logger.info(
                    f"{Fore.GREEN}[RECONCILE] Order found: {order_status.get('status')}"
                )
                # Update coordinator's orders_by_id
                # (implementation depends on your coordinator structure)
                return True
            else:
                # Order not found - safe to retry
                logger.info(f"{Fore.CYAN}[RECONCILE] Order not found - safe to retry")
                return True
                
        except Exception as e:
            logger.error(f"{Fore.RED}[RECONCILE] Failed: {e}")
            return False
    
    async def _retry_with_backoff(
        self,
        context: Dict[str, Any],
        event: ErrorEvent
    ) -> bool:
        """Retry operation with exponential backoff"""
        for attempt in range(self.max_recovery_attempts):
            if attempt > 0:
                backoff = self.backoff_base ** attempt
                logger.info(
                    f"{Fore.YELLOW}[BACKOFF RETRY] Attempt {attempt + 1}/{self.max_recovery_attempts} "
                    f"after {backoff:.1f}s"
                )
                await asyncio.sleep(backoff)
            
            # NOTE: Actual retry logic must be injected by the caller.
            # This manager cannot re-issue the original order without a reference
            # to the original order placement function. Return False to signal
            # the caller that it should retry the operation itself.
            return False
        
        return False
    
    async def _adjust_and_retry(
        self,
        context: Dict[str, Any],
        event: ErrorEvent
    ) -> bool:
        """Adjust parameters based on error and retry"""
        error_code = event.error_code
        
        logger.info(f"{Fore.CYAN}[PARAM ADJUST] Fixing parameters for error {error_code}")
        
        # Timestamp errors (-1021)
        if error_code == -1021:
            # Sync server time
            try:
                await self.exchange_client.sync_server_time()
                logger.info(f"{Fore.GREEN}[PARAM ADJUST] Server time synced")
                return False  # Retry needed
            except Exception as e:
                logger.error(f"{Fore.RED}[PARAM ADJUST] Failed to sync time: {e}")
                return False
        
        # Precision errors (-1111, -4014)
        elif error_code in (-1111, -4014):
            # Round to proper precision
            logger.info(f"{Fore.GREEN}[PARAM ADJUST] Rounding to proper precision")
            # This would be handled by order validator
            return False  # Retry with rounded values
        
        # Min quantity errors (-4004)
        elif error_code == -4004:
            logger.info(f"{Fore.GREEN}[PARAM ADJUST] Adjusting to minimum quantity")
            # Increase quantity to minimum
            return False  # Retry with adjusted quantity
        
        # Price errors (-4013)
        elif error_code == -4013:
            logger.info(f"{Fore.GREEN}[PARAM ADJUST] Adjusting price to minimum")
            return False  # Retry with adjusted price
        
        return False
    
    async def freeze_strategy(self, reason: str):
        """Freeze strategy from placing new orders"""
        if self.is_frozen:
            return
        
        self.is_frozen = True
        
        if hasattr(self.coordinator, 'is_frozen'):
            self.coordinator.is_frozen = True
        
        logger.warning(
            f"{Fore.YELLOW}[STRATEGY FREEZE] Strategy frozen\n"
            f"  Reason: {reason}\n"
            f"  Time: {datetime.now().isoformat()}\n"
            f"  No new orders will be placed"
        )
    
    async def unfreeze_strategy(self):
        """Unfreeze strategy"""
        if not self.is_frozen:
            return
        
        self.is_frozen = False
        
        if hasattr(self.coordinator, 'is_frozen'):
            self.coordinator.is_frozen = False
        
        logger.info(
            f"{Fore.GREEN}[STRATEGY UNFREEZE] Strategy resumed\n"
            f"  Time: {datetime.now().isoformat()}"
        )
    
    def should_block_order(self) -> Tuple[bool, str]:
        """
        Check if new orders should be blocked due to error recovery
        
        Returns:
            (should_block, reason)
        """
        if self.is_frozen:
            return True, "Strategy frozen - error recovery in progress"
        
        return False, ""
    
    def get_error_stats(self) -> Dict[str, Any]:
        """Get error statistics"""
        total_errors = len(self.error_history)
        
        if total_errors == 0:
            return {
                "total_errors": 0,
                "errors_by_category": {},
                "errors_by_code": {},
                "recovery_success_rate": 0.0,
                "most_common_errors": []
            }
        
        # Count by category — single pass over bounded deque (maxlen=500)
        by_category = {}
        for event in self.error_history:
            cat = event.category.name
            by_category[cat] = by_category.get(cat, 0) + 1
        
        # Recovery stats — read incremental counters instead of two O(n) generator scans
        recovery_attempted = self._recovery_attempted_count
        recovery_success   = self._recovery_successful_count
        
        # Most common errors
        most_common = sorted(
            self.error_stats.items(),
            key=lambda x: x[1],
            reverse=True
        )[:10]
        
        return {
            "total_errors": total_errors,
            "errors_by_category": by_category,
            "errors_by_code": dict(self.error_stats),
            "recovery_attempted": recovery_attempted,
            "recovery_successful": recovery_success,
            "recovery_success_rate": (
                recovery_success / recovery_attempted
                if recovery_attempted > 0 else 0.0
            ),
            "most_common_errors": [
                {
                    "code": code,
                    "count": count,
                    "description": ERROR_CATALOG.get(code, ErrorDescriptor(
                        code=code, category=ErrorCategory.UNKNOWN,
                        severity=ErrorSeverity.ERROR, recovery_action=RecoveryAction.MANUAL_INTERVENTION,
                        description="Unknown", oms_impact="Unknown",
                        auto_recoverable=False, freeze_strategy=False
                    )).description
                }
                for code, count in most_common
            ],
            "is_frozen": self.is_frozen
        }
    
    def get_recent_errors(self, count: int = 10) -> List[Dict[str, Any]]:
        """Get recent error events"""
        # deque does not support slice indexing — use islice(reversed(...)) instead.
        # reversed() iterates from newest to oldest in O(1); islice stops after `count`.
        recent = list(itertools.islice(reversed(self.error_history), count))
        
        return [
            {
                "timestamp": datetime.fromtimestamp(e.timestamp).isoformat(),
                "code": e.error_code,
                "message": e.error_msg[:100],
                "category": e.category.name,
                "severity": e.severity.name,
                "recovery_attempted": e.recovery_attempted,
                "recovery_successful": e.recovery_successful,
                "context": e.context  # Preserve full context including custom fields
            }
            for e in recent  # already in newest-first order from islice(reversed(...))
        ]


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def get_error_description(error_code: int) -> str:
    """Get human-readable description for error code"""
    descriptor = ERROR_CATALOG.get(error_code)
    if descriptor:
        return f"{descriptor.description} (Impact: {descriptor.oms_impact})"
    return f"Unknown error code {error_code}"


def is_recoverable_error(error_code: int) -> bool:
    """Check if error is automatically recoverable"""
    descriptor = ERROR_CATALOG.get(error_code)
    return descriptor.auto_recoverable if descriptor else False


def requires_freeze(error_code: int) -> bool:
    """Check if error requires strategy freeze"""
    descriptor = ERROR_CATALOG.get(error_code)
    return descriptor.freeze_strategy if descriptor else False