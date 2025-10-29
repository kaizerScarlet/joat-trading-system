import pytest
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime, timedelta
from dynamic_risk_engine.daily_drawdown_manager_protocol import DailyDrawdownManagerProtocol
from dynamic_risk_engine.daily_drawdown_manager import DailyDrawdownManager
from Execution_layer.binance_adapter_protocol import BinanceExecutionAdapterProtocol


@pytest.mark.asyncio
async def test_record_pnl_and_no_halt():
    
    manager : DailyDrawdownManagerProtocol = DailyDrawdownManager(
        binance_adapter = BinanceExecutionAdapterProtocol,
        daily_drawdown_limit=0.25,
        regime_classifier = MagicMock()
        )
    #Mock the adapters get account method
    manager.account_balance.get_account = AsyncMock(return_value=1000.0)
    await manager.initialize() #This sets drawdown limit


    timestamp = datetime.now()

    manager.record_pnl(timestamp, 500.0)
    manager.record_pnl(timestamp, -200.0)

    assert manager.calculate_daily_drawdown(timestamp) == -200.0
    assert not manager.is_trading_halted(timestamp)

    manager.reset_daily_drawdown(timestamp)

@pytest.mark.asyncio
async def test_trading_halted_when_limit_exceeded(capfd):
    
    manager : DailyDrawdownManagerProtocol = DailyDrawdownManager(
        binance_adapter = BinanceExecutionAdapterProtocol,
        daily_drawdown_limit=0.25,
        regime_classifier = MagicMock()
        )

    #Mock the adapters get account balance
    manager.account_balance.get_account = AsyncMock(return_value=1000.0)
    await manager.initialize() #This sets drawdown limit
    timestamp = datetime.now()

    manager.record_pnl(timestamp, -100.0)
    manager.record_pnl(timestamp, -400.0)  # Should trigger halt

    assert manager.calculate_daily_drawdown(timestamp) == -400.0
    assert manager.is_trading_halted(timestamp)

    captured = capfd.readouterr()
    assert f"Trading halted for {manager._get_day(timestamp)}" in captured.out

    manager.reset_daily_drawdown(timestamp)

@pytest.mark.asyncio
async def test_trades_return_zero_drawdown():
    
    manager : DailyDrawdownManagerProtocol = DailyDrawdownManager(
        binance_adapter = BinanceExecutionAdapterProtocol,
        daily_drawdown_limit=0.25,
        regime_classifier = MagicMock()
        )
    #Mock the adapters get account balance
    manager.account_balance.get_account = AsyncMock(return_value=1000.0)
    await manager.initialize() #This sets drawdown limit
    timestamp = datetime.now()

    assert manager.calculate_daily_drawdown(timestamp) == 0.0
    assert not manager.is_trading_halted(timestamp)

    manager.reset_daily_drawdown(timestamp)

@pytest.mark.asyncio
async def test_reset_daily_drawdown():
    
    manager : DailyDrawdownManagerProtocol = DailyDrawdownManager(
        binance_adapter = BinanceExecutionAdapterProtocol,
        daily_drawdown_limit=0.25,
        regime_classifier = MagicMock()
        )
    #Mock the adapters get account balance
    manager.account_balance.get_account = AsyncMock(return_value=1000.0)
    await manager.initialize()  #This sets drawdown limit
    timestamp = datetime(2023, 10, 1, 10, 0, 0)
    

    manager.record_pnl(timestamp, 500.0)
    manager.record_pnl(timestamp, -200.0)

    manager.reset_daily_drawdown(timestamp)

    assert manager.calculate_daily_drawdown(timestamp) == 0.0
    assert not manager.is_trading_halted(timestamp)

@pytest.mark.asyncio
async def test_multiple_days_handling():

    manager : DailyDrawdownManagerProtocol = DailyDrawdownManager(
        binance_adapter = BinanceExecutionAdapterProtocol,
        daily_drawdown_limit=0.25,
        regime_classifier = MagicMock(),
        )
    #Mock the adapters get account balance
    manager.account_balance.get_account = AsyncMock(return_value=1000.0)
    await manager.initialize()  #This sets drawdown limit
    base_time = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    today = base_time
    yesterday = today - timedelta(days=1)

    #Today small loss should not trigger halt
    manager.record_pnl(today, 0.0)# Peak Through
    manager.record_pnl(today, -100.0) #Peak Through

    #Yesterday: simulate drawdown from peak to trough
    manager.record_pnl(yesterday, 100.0)    #Peak
    manager.record_pnl(yesterday, -400.0)   #Trough -> Drawdown = -500.0

    #Validate trading status
    assert not manager.is_trading_halted(today)
    assert manager.is_trading_halted(yesterday)

    #Validate drawdown values
    assert manager.calculate_daily_drawdown(today) == -100.0
    assert manager.calculate_daily_drawdown(yesterday) == -400.0

    manager.reset_daily_drawdown(today)
    manager.reset_daily_drawdown(yesterday)


@pytest.mark.asyncio
async def test_drawdown_curve_accuracy():

    manager : DailyDrawdownManagerProtocol = DailyDrawdownManager(
        binance_adapter = BinanceExecutionAdapterProtocol,
        daily_drawdown_limit=0.25,
        regime_classifier = MagicMock()
        )
    #Mock the adapters get account balance
    manager.account_balance.get_account = AsyncMock(return_value=1000.0)
    await manager.initialize() #This sets drawdown limit
    timestamp = datetime.now()

    manager.record_pnl(timestamp, 100.0)
    manager.record_pnl(timestamp, -50.0)
    manager.record_pnl(timestamp, -100.0)

    curve = manager.get_drawdown_curve(timestamp)
    assert curve == [100.0, 50.0, -50.0]


@pytest.mark.asyncio
async def test_empty_day_drawdown():

    manager : DailyDrawdownManagerProtocol = DailyDrawdownManager(
        binance_adapter = BinanceExecutionAdapterProtocol,
        daily_drawdown_limit=0.25,
        regime_classifier = MagicMock()
        )
    manager.account_balance.get_account = AsyncMock(return_value=1000.0)
    await manager.initialize()

    timestamp = datetime.now()
    assert manager.calculate_daily_drawdown(timestamp) == 0.0
    assert not manager.is_trading_halted(timestamp)


@pytest.mark.asyncio
async def test_reset_clears_state():

    manager : DailyDrawdownManagerProtocol = DailyDrawdownManager(
        binance_adapter = BinanceExecutionAdapterProtocol,
        daily_drawdown_limit=0.25,
        regime_classifier = MagicMock()
        )
    manager.account_balance.get_account = AsyncMock(return_value=1000.0)
    await manager.initialize()

    timestamp = datetime.now()
    manager.record_pnl(timestamp, 100.0)
    manager.record_pnl(timestamp, -400.0)
    manager.reset_daily_drawdown(timestamp)

    assert manager.calculate_daily_drawdown(timestamp) == 0.0
    assert not manager.is_trading_halted(timestamp)



@pytest.mark.asyncio
async def test_status_snapshot():

    manager : DailyDrawdownManagerProtocol = DailyDrawdownManager(
        binance_adapter = BinanceExecutionAdapterProtocol,
        daily_drawdown_limit=0.25,
        regime_classifier = MagicMock()
        )
    manager.account_balance.get_account = AsyncMock(return_value=1000.0)
    await manager.initialize()

    timestamp = datetime.now()
    manager.record_pnl(timestamp, 100.0)
    manager.record_pnl(timestamp, -400.0)

    status = manager.get_status(timestamp)
    assert status["trading_halted"] is True
    assert status["current_drawdown"] == -400.0
    assert status["pnl_events"] == 2
    assert status["cumulative_pnl"] == -300.0


@pytest.mark.asyncio
async def test_drawdown_equals_limit_triggers_halt():

    manager : DailyDrawdownManagerProtocol = DailyDrawdownManager(
        binance_adapter = BinanceExecutionAdapterProtocol,
        daily_drawdown_limit=0.25,
        regime_classifier = MagicMock()
        )
    manager.account_balance.get_account = AsyncMock(return_value=1000.0)
    await manager.initialize()

    timestamp = datetime.now()
    manager.record_pnl(timestamp, 0.0)
    manager.record_pnl(timestamp, -250.0)  # Exactly at limit

    assert manager.is_trading_halted(timestamp)

