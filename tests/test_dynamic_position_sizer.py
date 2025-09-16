import pytest
from unittest.mock import AsyncMock
from dynamic_risk_engine.dynamic_position_sizer import DynamicPositionSizer

@pytest.mark.asyncio
async def test_default_initialization():
    sizer = DynamicPositionSizer()
    sizer.drawdown.account_balance.get_account = AsyncMock(return_value=100000)
    sizer.win_rate.win_rate = lambda: 0.5
    sizer.confidence.get_current_confidence = lambda: 0.5
    sizer.win_rate.average_rrr = lambda: 2.0  # ✅ Prevent ZeroDivisionError

    await sizer.initialize()
    assert isinstance(sizer.max_risk_per_trade, float)
    assert sizer.max_risk_per_trade > 0

@pytest.mark.asyncio
async def test_position_size_basic_calculation():
    sizer = DynamicPositionSizer()

    #Mock drawdown to prevent real API calls
    sizer.drawdown.account_balance.get_account = AsyncMock(return_value=100000)

    # Mock performance and confidence before initialization
    sizer.win_rate.win_rate = lambda: 0.5
    sizer.win_rate.average_rrr = lambda: 2.0  # ✅ Prevent ZeroDivisionError
    sizer.confidence.get_current_confidence = lambda: 1.0

    await sizer.initialize()

    # Mock remaining dependencies

    sizer.account_balance.get_account_balance = AsyncMock(return_value=100000)
    sizer.volatility.get_volatility_estimate = lambda: 1.0
    sizer.drawdown.get_daily_drawdown_limit = lambda: 1.0

    position_size = await sizer.calculate_position_size(stop_loss_distance=10)
    expected_risk = 100000 * sizer.max_risk_per_trade * 1.0 * (0.5 + 0.5) * 1.0 * 1.0
    expected_size = expected_risk / 10
    assert round(position_size, 4) == round(expected_size, 4)

@pytest.mark.asyncio
async def test_zero_stop_loss_returns_zero():
    sizer = DynamicPositionSizer()

    #Mock drawdown to prevent real API calls
    sizer.drawdown.account_balance.get_account = AsyncMock(return_value=100000)

    #Mock account balance and performance metrics to prevent real calls
    sizer.account_balance.get_account_balance = AsyncMock(return_value=100000)
    sizer.win_rate.win_rate = lambda: 0.5
    sizer.win_rate.average_rrr = lambda: 2.0  # ✅ Prevent ZeroDivisionError
    sizer.confidence.get_current_confidence = lambda: 0.5

    await sizer.initialize()
    position_size = await sizer.calculate_position_size(stop_loss_distance=0)
    assert position_size == 0.0

@pytest.mark.asyncio
async def test_low_confidence_reduces_sizer():
    sizer = DynamicPositionSizer()

    #Mock account balance adapters to prevent real API calls
    sizer.account_balance.get_account_balance = AsyncMock(return_value=100000)

    #mock drawdown to prevent real API calls
    sizer.drawdown.account_balance.get_account = AsyncMock(return_value=100000)

    #Mock performance and volatility before initialization
    sizer.win_rate.win_rate = lambda: 0.5
    sizer.win_rate.average_rrr = lambda: 2.0  # ✅ Prevent ZeroDivisionError
    sizer.volatility.get_volatility_estimate = lambda: 1.0
    sizer.drawdown.get_daily_drawdown_limit = lambda: 1.0
    
    await sizer.initialize()
   

    sizer.confidence.get_current_confidence = lambda: 1.0
    high_conf_size = await sizer.calculate_position_size(10)

    sizer.confidence.get_current_confidence = lambda: 0.5
    low_conf_size = await sizer.calculate_position_size(10)

    assert low_conf_size < high_conf_size

@pytest.mark.asyncio
async def test_low_win_rate_reduces_sizer():
    sizer = DynamicPositionSizer()
    
      #mock drawdown to prevent real API calls
    sizer.drawdown.account_balance.get_account = AsyncMock(return_value=100000)
    #Mock account balance adapters to prevent real API calls
    sizer.account_balance.get_account_balance = AsyncMock(return_value=100000)
    
  

    #Mock confidence and volatility before initialization
    sizer.confidence.get_current_confidence = lambda: 1.0
    sizer.volatility.get_volatility_estimate = lambda: 1.0
    sizer.drawdown.get_daily_drawdown_limit = lambda: 1.0
    sizer.win_rate.average_rrr = lambda: 2.0  # ✅ Prevent ZeroDivisionError

    sizer.win_rate.win_rate = lambda: 0.8
    await sizer.initialize()
    high_win_size = await sizer.calculate_position_size(10)

    sizer.win_rate.win_rate = lambda: 0.2
    await sizer.initialize()
    low_win_size = await sizer.calculate_position_size(10)

    assert low_win_size < high_win_size

@pytest.mark.asyncio
async def test_position_size_rounding():
    sizer = DynamicPositionSizer()
    #Mock account balance adapters to prevent real API calls
    sizer.account_balance.get_account_balance = AsyncMock(return_value=123456.78)
    #mock drawdown to prevent real API calls
    sizer.drawdown.account_balance.get_account = AsyncMock(return_value=100000)

    #Mock performance and confidence before initialization
    sizer.win_rate.win_rate = lambda: 0.66
    sizer.win_rate.average_rrr = lambda: 2.0  # ✅ Prevent ZeroDivisionError
    sizer.confidence.get_current_confidence = lambda: 0.75
    sizer.volatility.get_volatility_estimate = lambda: 1.0
    sizer.drawdown.get_daily_drawdown_limit = lambda: 1.0
    await sizer.initialize()
    

    size = await sizer.calculate_position_size(7.25)
    assert isinstance(size, float)
    assert len(str(size).split('.')[-1]) <= 4

@pytest.mark.asyncio
async def test_drawdown_scaling_reduces_position_size():
    sizer = DynamicPositionSizer()
    #Mock account balance adapters to prevent real API calls
    sizer.account_balance.get_account_balance = AsyncMock(return_value=100000)
    #mock drawdown to prevent real API calls
    sizer.drawdown.account_balance.get_account = AsyncMock(return_value=100000)
    sizer.confidence.get_current_confidence = lambda: 1.0
    sizer.win_rate.win_rate = lambda: 0.5
    sizer.volatility.get_volatility_estimate = lambda: 1.0
    
    await sizer.initialize()


    sizer.drawdown.get_daily_drawdown_limit = lambda: -0.25
    deep_drawdown_size = await sizer.calculate_position_size(10)

    sizer.drawdown.get_daily_drawdown_limit = lambda: -0.05
    shallow_drawdown_size = await sizer.calculate_position_size(10)

    assert deep_drawdown_size < shallow_drawdown_size

@pytest.mark.asyncio
async def test_volatility_increases_position_size():
    sizer = DynamicPositionSizer()
   
    # Mock drawdown to prevent real API calls
    sizer.drawdown.account_balance.get_account = AsyncMock(return_value=100000)
    # Mock account balance and performance metrics to prevent real calls
    sizer.account_balance.get_account_balance = AsyncMock(return_value=100000)

    #Mock confidence and win rate before initialization
    sizer.confidence.get_current_confidence = lambda: 1.0
    sizer.win_rate.win_rate = lambda: 0.5
    sizer.drawdown.get_daily_drawdown_limit = lambda: 1.0
    sizer.volatility.get_volatility_estimate = lambda: 0.2
    
    await sizer.initialize()
    sizer.volatility.get_volatility_estimate = lambda: 0.2
    low_vol_size = await sizer.calculate_position_size(10)

    sizer.volatility.get_volatility_estimate = lambda: 0.8
    high_vol_size = await sizer.calculate_position_size(10)

    assert high_vol_size > low_vol_size

@pytest.mark.asyncio
async def test_confidence_win_rate_interaction():
    sizer = DynamicPositionSizer()
    # Mock account balance adapters to prevent real API calls
    sizer.account_balance.get_account_balance = AsyncMock(return_value=100000)
    # Mock drawdown to prevent real API calls
    sizer.drawdown.account_balance.get_account = AsyncMock(return_value=100000)
    sizer.volatility.get_volatility_estimate = lambda: 1.0
    sizer.drawdown.get_daily_drawdown_limit = lambda: 1.0
    sizer.win_rate.average_rrr = lambda: 2.0  # ✅ Prevent ZeroDivisionError
    await sizer.initialize()
    

    sizer.confidence.get_current_confidence = lambda: 0.3
    sizer.win_rate.win_rate = lambda: 0.3
    low_combo_size = await sizer.calculate_position_size(10)

    sizer.confidence.get_current_confidence = lambda: 0.9
    sizer.win_rate.win_rate = lambda: 0.9
    high_combo_size = await sizer.calculate_position_size(10)

    assert high_combo_size > low_combo_size

@pytest.mark.asyncio
async def test_sizing_diagnostics_structure():
    sizer = DynamicPositionSizer()
    # Mock account balance adapters to prevent real API calls
     # Mock drawdown to prevent real API calls
    sizer.account_balance.get_account_balance = AsyncMock(return_value=100000.0)
    sizer.drawdown.account_balance.get_account = AsyncMock(return_value=100000.0)

    sizer.confidence.get_current_confidence = lambda: 1.0
    sizer.win_rate.win_rate = lambda: 0.5
    sizer.volatility.get_volatility_estimate = lambda: 1.0
    sizer.drawdown.get_daily_drawdown_limit = lambda: 1.0
    await sizer.initialize()

    diagnostics = await sizer.get_sizing_diagnostics(stop_loss_distance=10)
    assert "position_size" in diagnostics
    assert diagnostics["stop_loss_distance"] == 10
    assert isinstance(diagnostics["balance"], float)
