import time
import pytest 
from dynamic_risk_engine.throttle_cooldown_manager import ThrottleCooldownManager

@pytest.fixture
def manager():
    
    m = ThrottleCooldownManager(max_losses=3, cooldown_seconds=5, max_trades_per_minute=3)
    m.reset()
    return m


def test_initial_state(manager):
    manager.reset()
    assert manager.loss_streak == 0
    assert manager.cooldown_until == 0
    assert manager.trade_timestamps == []
    assert manager.can_trade() is True


def test_register_trade_win_resets_loss_streak(manager):
    manager.reset()
    manager.register_trade(-100)
    manager.register_trade(-50)
    assert manager.loss_streak == 2
    manager.register_trade(200)  # Register a win
    assert manager.loss_streak == 0  # Loss streak should reset after a win
    


def test_cooldown_expires_after_duration(manager):
    manager.reset()
    manager.register_trade(-1)
    manager.register_trade(-1)
    manager.register_trade(-1)  # Should trigger cooldown
    assert manager.is_in_cooldown() is True
    
    #simulate time passing
    time.sleep(manager.cooldown_seconds + 1)
    assert manager.is_in_cooldown() is False  # Cooldown should have expired
    assert manager.can_trade() is True  # Should be able to trade again



def test_rate_limit_blocks_trade_when_exceeded(manager):
    manager.reset()
    #simulate 3 trades under one minute
    manager.register_trade(10)
    time.sleep(0.5)
    manager.register_trade(20)
    time.sleep(0.5)
    manager.register_trade(30)
    assert manager.can_trade() is False  # Should be blocked due to rate limit



def test_rate_limit_resets_after_60_seconds(manager):
    manager.reset()
    #simulate 3 trades under one minute
    manager.register_trade(10)
    time.sleep(1)
    manager.register_trade(20)
    time.sleep(1)
    manager.register_trade(30)
    assert manager.can_trade() is False  # Should be blocked due to rate limit
    
    #simulate time passing
    time.sleep(64)
    assert manager.can_trade() is True  # Should be able to trade again after 60 seconds



def test_no_cooldown_on_profitable_trades(manager):
    manager.reset()
    for _ in range(manager.max_losses):
        manager.register_trade(100) # Register profitable trades
    assert manager.is_in_cooldown() is False  # Should not be in cooldown after profitable trades
    assert manager.loss_streak == 0  # Loss streak should not increase
    assert manager.can_trade() is True  # Should be able to trade
    