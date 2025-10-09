import pytest
from unittest.mock import AsyncMock
from dynamic_risk_engine.dynamic_position_sizer import DynamicPositionSizer
from dynamic_risk_engine.dynamic_position_sizer_protocol import DynamicPositionSizerProtocol
from dynamic_risk_engine.signal_confidence_calibrator_protocol import SignalConfidenceCalibratorProtocol
from dynamic_risk_engine.performance_tracker_protocol import PerformanceTrackerProtocol
from market_data.orderbook_protocol import OrderBookProtocol
from dynamic_risk_engine.daily_drawdown_manager_protocol import DailyDrawdownManagerProtocol
from Execution_layer.binance_adapter_protocol import BinanceExecutionAdapterProtocol


from unittest.mock import AsyncMock, MagicMock

@pytest.mark.asyncio
async def test_default_initialization():
    mock_adapter = MagicMock()
    mock_adapter.get_account_balance = AsyncMock(return_value=100000)

    mock_confidence = MagicMock()
    mock_confidence.get_current_confidence = MagicMock(return_value=0.8)

    mock_tracker = MagicMock()
    mock_tracker.win_rate = MagicMock(return_value=0.65)
    mock_tracker.average_rrr = MagicMock(return_value=2.0)

    mock_orderbook = MagicMock()
    mock_orderbook.get_volatility_estimate = MagicMock(return_value=0.01)

    mock_drawdown = MagicMock()
    mock_drawdown.initialize = AsyncMock()
    mock_drawdown.get_daily_drawdown_limit = MagicMock(return_value=-0.1)

    sizer = DynamicPositionSizer(
        binance_adapter=mock_adapter,
        confidence=mock_confidence,
        performance_tracker=mock_tracker,
        orderbook=mock_orderbook,
        binance_Execution_adapter=mock_adapter,
        drawdown=mock_drawdown
    )

    await sizer.initialize()
    assert sizer.max_risk_per_trade > 0

import pytest
from unittest.mock import AsyncMock, MagicMock
from dynamic_risk_engine.dynamic_position_sizer import DynamicPositionSizer
from dynamic_risk_engine.dynamic_position_sizer_protocol import DynamicPositionSizerProtocol

@pytest.mark.asyncio
async def test_position_size_basic_calculation():
    # Create mock instances for all dependencies
    mock_adapter = MagicMock()
    mock_adapter.get_account_balance = AsyncMock(return_value=100000)

    mock_confidence = MagicMock()
    mock_confidence.get_current_confidence = MagicMock(return_value=1.0)

    mock_tracker = MagicMock()
    mock_tracker.win_rate = MagicMock(return_value=0.5)
    mock_tracker.average_rrr = MagicMock(return_value=2.0)

    mock_orderbook = MagicMock()
    mock_orderbook.get_volatility_estimate = MagicMock(return_value=1.0)

    mock_drawdown = MagicMock()
    mock_drawdown.initialize = AsyncMock()
    mock_drawdown.get_daily_drawdown_limit = MagicMock(return_value=1.0)

    # Instantiate the sizer with mocks
    sizer: DynamicPositionSizerProtocol = DynamicPositionSizer(
        binance_adapter=mock_adapter,
        confidence=mock_confidence,
        performance_tracker=mock_tracker,
        orderbook=mock_orderbook,
        binance_Execution_adapter=mock_adapter,
        drawdown=mock_drawdown
    )

    await sizer.initialize()

    # Run the sizing logic
    position_size = await sizer.calculate_position_size(stop_loss_distance=10)

    # Compute expected result
    expected_risk = 100000 * sizer.max_risk_per_trade * 1.0 * (0.5 + 0.5) * 1.0 * 1.0
    expected_size = expected_risk / 10

    assert round(position_size, 4) == round(expected_size, 4)


from unittest.mock import AsyncMock, MagicMock
from dynamic_risk_engine.dynamic_position_sizer import DynamicPositionSizer

def create_mock_sizer(balance=100000, confidence=1.0, win_rate=0.5, rrr=2.0, volatility=1.0, drawdown_limit=1.0):
    mock_adapter = MagicMock()
    mock_adapter.get_account_balance = AsyncMock(return_value=balance)

    mock_confidence = MagicMock()
    mock_confidence.get_current_confidence = MagicMock(return_value=confidence)

    mock_tracker = MagicMock()
    mock_tracker.win_rate = MagicMock(return_value=win_rate)
    mock_tracker.average_rrr = MagicMock(return_value=rrr)

    mock_orderbook = MagicMock()
    mock_orderbook.get_volatility_estimate = MagicMock(return_value=volatility)

    mock_drawdown = MagicMock()
    mock_drawdown.initialize = AsyncMock()
    mock_drawdown.get_daily_drawdown_limit = MagicMock(return_value=drawdown_limit)

    sizer = DynamicPositionSizer(
        binance_adapter=mock_adapter,
        confidence=mock_confidence,
        performance_tracker=mock_tracker,
        orderbook=mock_orderbook,
        binance_Execution_adapter=mock_adapter,
        drawdown=mock_drawdown
    )
    return sizer

@pytest.mark.asyncio
async def test_zero_stop_loss_returns_zero():
    sizer = create_mock_sizer()
    await sizer.initialize()
    position_size = await sizer.calculate_position_size(stop_loss_distance=0)
    assert position_size == 0.0

@pytest.mark.asyncio
async def test_low_confidence_reduces_sizer():
    sizer = create_mock_sizer(confidence=1.0)
    await sizer.initialize()
    high_conf_size = await sizer.calculate_position_size(10)

    sizer.confidence.get_current_confidence = MagicMock(return_value=0.5)
    low_conf_size = await sizer.calculate_position_size(10)

    assert low_conf_size < high_conf_size

@pytest.mark.asyncio
async def test_low_win_rate_reduces_sizer():
    sizer = create_mock_sizer(win_rate=0.8)
    await sizer.initialize()
    high_win_size = await sizer.calculate_position_size(10)

    sizer.win_rate.win_rate = MagicMock(return_value=0.2)
    await sizer.initialize()
    low_win_size = await sizer.calculate_position_size(10)

    assert low_win_size < high_win_size

@pytest.mark.asyncio
async def test_position_size_rounding():
    sizer = create_mock_sizer(balance=123456.78, confidence=0.75, win_rate=0.66)
    await sizer.initialize()
    size = await sizer.calculate_position_size(7.25)
    assert isinstance(size, float)
    assert len(str(size).split('.')[-1]) <= 4

@pytest.mark.asyncio
async def test_drawdown_scaling_reduces_position_size():
    sizer = create_mock_sizer(drawdown_limit=-0.25)
    await sizer.initialize()
    deep_drawdown_size = await sizer.calculate_position_size(10)

    sizer.drawdown.get_daily_drawdown_limit = MagicMock(return_value=-0.05)
    shallow_drawdown_size = await sizer.calculate_position_size(10)

    assert deep_drawdown_size < shallow_drawdown_size


@pytest.mark.asyncio
async def test_volatility_increases_position_size():
    sizer = create_mock_sizer(volatility=0.2)
    await sizer.initialize()
    low_vol_size = await sizer.calculate_position_size(10)

    sizer.volatility.get_volatility_estimate = MagicMock(return_value=0.8)
    high_vol_size = await sizer.calculate_position_size(10)

    assert high_vol_size > low_vol_size


@pytest.mark.asyncio
async def test_confidence_win_rate_interaction():
    sizer = create_mock_sizer(confidence=0.3, win_rate=0.3)
    await sizer.initialize()
    low_combo_size = await sizer.calculate_position_size(10)

    sizer.confidence.get_current_confidence = MagicMock(return_value=0.9)
    sizer.win_rate.win_rate = MagicMock(return_value=0.9)
    high_combo_size = await sizer.calculate_position_size(10)

    assert high_combo_size > low_combo_size


@pytest.mark.asyncio
async def test_sizing_diagnostics_structure():
    sizer = create_mock_sizer(balance=100000.0, confidence=1.0, win_rate=0.5, volatility=1.0, drawdown_limit=1.0)
    await sizer.initialize()
    diagnostics = await sizer.get_sizing_diagnostics(stop_loss_distance=10)

    assert "position_size" in diagnostics
    assert diagnostics["stop_loss_distance"] == 10
    assert isinstance(diagnostics["balance"], float)

