import pytest 
from datetime import datetime, timedelta
from dynamic_risk_engine.daily_drawdown_manager import DailyDrawdownManager

def test_record_pnl_and_no_halt():
    manager = DailyDrawdownManager(daily_drawdown_limit=1000.0)

    # Record some PnL
    timestamp = datetime(2023, 10, 1, 10, 0, 0)
    manager.record_pnl(timestamp, 500.0)
    manager.record_pnl(timestamp, -200.0)

    # Check daily PnL
    assert manager.calculate_daily_drawdown('2023-10-01') == 300.0
    assert not manager.is_trading_halted(timestamp)


def test_trading_halted_when_limit_exceeded(capfd):
    manager = DailyDrawdownManager(daily_drawdown_limit=300.0)

    # Record PnL that exceeds the limit
    timestamp = datetime(2023, 10, 1, 10, 0, 0)
    manager.record_pnl(timestamp, -150.0)
    manager.record_pnl(timestamp, -200.0)  # This should trigger the halt

    # Check if trading is halted
    assert manager.is_trading_halted(timestamp)
    
    # Capture printed output
    captured = capfd.readouterr()
    assert "Trading halted for 2023-10-01 due to drawdown limit exceeded: 1000.0" in captured.out


def test_test_trades_returns_zero_drawdown():
    manager = DailyDrawdownManager(daily_drawdown_limit=1000.0)
    random_date = datetime.now().strftime('%Y-%m-%d')
    assert manager.calculate_daily_drawdown(random_date) == 0.0


def test_reset_daily_drawdown():
    manager = DailyDrawdownManager(daily_drawdown_limit=1000.0)

    # Record some PnL
    timestamp = datetime(2023, 10, 1, 10, 0, 0)
    manager.record_pnl(timestamp, 500.0)
    manager.record_pnl(timestamp, -200.0)

    # Reset the daily drawdown
    manager.reset_daily_drawdown(timestamp)

    # Check that the daily PnL is reset
    assert manager.calculate_daily_drawdown('2023-10-01') == 0.0
    assert not manager.is_trading_halted(timestamp)


def test_mulitple_days_handling():
    manager = DailyDrawdownManager(daily_drawdown_limit=300.00)

    today = datetime.now()
    yesterday = today - timedelta(days=1)

    manager.record_pnl(datetime(today, -100))
    manager.yesterday(datetime(yesterday, -200))


    assert not manager.is_trading_halted(today)
    assert manager.is_trading_halted(yesterday)