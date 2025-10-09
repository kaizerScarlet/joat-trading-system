import time
import pytest
from dynamic_risk_engine.cognitive_market_regime_classifier import MarketRegime 
from dynamic_risk_engine.throttle_cooldown_manager import ThrottleCooldownManager
from dynamic_risk_engine.throttle_cooldown_manager_protocol import ThrottleCooldownManagerProtocol

from unittest.mock import MagicMock

@pytest.fixture
def manager():
    mock_regime = MagicMock()
    mock_regime.get_behavioral_overlay.return_value = "NORMAL"
    mock_regime.get_current_regime.return_value = "NORMAL"
    mock_regime.update_regime.return_value = MarketRegime.UNKNOWN

    mock_confidence = MagicMock()
    mock_confidence.get_current_confidence.return_value = 0.8

    mock_cancel_window = MagicMock()
    mock_orderbook = MagicMock()

    m = ThrottleCooldownManager(
        regime_classifier=mock_regime,
        confidence=mock_confidence,
        cancel_window=mock_cancel_window,
        orderbook=mock_orderbook,
        max_losses=3,
        cooldown_seconds=5,
        max_trades_per_minute=3
    )
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

    
def test_conversion_rate_with_orders_and_cancels(manager):
    manager.reset()
    for _ in range(5):
        manager.record_order(volume=1.0)
    for _ in range(5):
        manager.record_cancel()
    for _ in range(2):
        manager.register_trade_result(-10)
    assert manager.get_conversion_rate() == pytest.approx(2 / 10, 0.01)

def test_fill_weight_calculation(manager):
    manager.reset()
    manager.record_order(volume=100.0)
    manager.record_fill(volume=25.0)
    assert manager.get_fill_weight() == pytest.approx(0.25, 0.01)

def test_weight_accumulation(manager):
    manager.reset()
    for _ in range(10):
        manager.record_order(volume=1.0, weight=100)
    assert manager.get_weight_per_minute() == 1000

def test_status_snapshot(manager):
    manager.reset()
    manager.register_trade_result(-50)
    manager.record_order(volume=10.0)
    manager.record_cancel()
    status = manager.get_status()
    assert status["loss_streak"] == 1
    assert status["conversion_rate"] >= 0.0
    assert status["fill_weight"] >= 0.0
    assert isinstance(status["can_trade"], bool)


def test_behavioral_throttle_triggered(manager):
    manager.reset()
    manager.regime_classifier.get_behavioral_overlay = lambda: "LIQUIDITY_VACUUM"
    assert manager.is_throttled() is True
