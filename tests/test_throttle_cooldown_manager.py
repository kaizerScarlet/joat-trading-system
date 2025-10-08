import time
import pytest 
from dynamic_risk_engine.throttle_cooldown_manager import ThrottleCooldownManager
from dynamic_risk_engine.throttle_cooldown_manager_protocol import ThrottleCooldownManagerProtocol


@pytest.fixture
def manager():
    
    m: ThrottleCooldownManagerProtocol = ThrottleCooldownManager(max_losses=3, cooldown_seconds=5, max_trades_per_minute=3)
    m.reset()
    return m


def test_initial_state(manager):
    manager.reset()
    assert manager.loss_streak == 0
    assert manager.cooldown_until == 0
    assert len(manager.trade_timestamps) == 0
    assert manager.can_trade() is True


def test_register_trade_win_resets_loss_streak(manager):
    manager.reset()
    manager.register_trade_result(-100)
    manager.register_trade_result(-50)
    assert manager.loss_streak == 2
    manager.register_trade_result(200)  # Register a win
    assert manager.loss_streak == 0  # Loss streak should reset after a win
    


def test_cooldown_expires_after_duration(manager):
    manager.reset()
    manager.register_trade_result(-1)
    manager.register_trade_result(-1)
    manager.register_trade_result(-1)  # Should trigger cooldown
    assert manager.is_in_cooldown() is True
    
    #simulate time passing
    time.sleep(manager.cooldown_seconds + 1)
    assert manager.is_in_cooldown() is False  # Cooldown should have expired
    assert manager.can_trade() is True  # Should be able to trade again



def test_rate_limit_blocks_trade_when_exceeded_profits(manager):
    manager.reset()
    #simulate 3 trades under one minute
    manager.register_trade_result(10)
    time.sleep(0.5)
    manager.register_trade_result(20)
    time.sleep(0.5)
    manager.register_trade_result(30)
    assert manager.can_trade() is True  # Should not be blocked due to rate limit not affected by profitable trades

def test_rate_limit_blocks_trade_when_exceeded_losses(manager):
    manager.reset()
    #simulate 3 trades under one minute
    manager.register_trade_result(-10)
    time.sleep(0.5)
    manager.register_trade_result(-20)
    time.sleep(0.5)
    manager.register_trade_result(-30)
    assert manager.can_trade() is False  # Should be blocked due to rate limit affected by losses

def test_rate_limit_resets_after_60_seconds_losses(manager):
    manager.reset()
    #simulate 3 trades under one minute
    manager.register_trade_result(-10)
    time.sleep(1)
    manager.register_trade_result(-20)
    time.sleep(1)
    manager.register_trade_result(-30)
    assert manager.can_trade() is False  # Should be blocked due to rate limit
    
    #simulate time passing
    time.sleep(64)
    assert manager.can_trade() is True  # Should be able to trade again after 60 seconds

def test_rate_limit_resets_after_60_seconds_profits(manager):
    manager.reset()
    #simulate 3 trades under one minute
    manager.register_trade_result(10)
    time.sleep(1)
    manager.register_trade_result(20)
    time.sleep(1)
    manager.register_trade_result(30)
    assert manager.can_trade() is True  # Should not be blocked due to rate limit due to profits
    
    #simulate time passing
    time.sleep(64)
    assert manager.can_trade() is True  # Should be able to trade again after 60 seconds


def test_no_cooldown_on_profitable_trades(manager):
    manager.reset()
    for _ in range(manager.max_losses):
        manager.register_trade_result(100) # Register profitable trades
    assert manager.is_in_cooldown() is False  # Should not be in cooldown after profitable trades
    assert manager.loss_streak == 0  # Loss streak should not increase
    assert manager.can_trade() is True  # Should be able to trade


def test_diagnostic_snapshot(manager):
    manager.reset()
    manager.register_trade_result(-50)
    diag = manager.get_diagnostic()
    assert diag["loss_streak"] == 1
    assert diag["in_cooldown"] is False
    assert diag["conversion_rate"] >= 0.0
    assert diag["fill_weight"] >= 0.0


def test_throttle_triggered_by_order_volume(manager):
    manager.reset()
    for _ in range(manager.max_orders_per_10s + 1):
        manager.record_order(volume=1.0)
    assert manager.is_throttled() is True

    