import pytest
import time
import pytest_asyncio
from dynamic_risk_engine.dynamic_risk_engine_protocol import DynamicRiskEngineProtocol
from dynamic_risk_engine.dynamic_risk_engine import DynamicRiskEngine
from dynamic_risk_engine.cognitive_market_regime_classifier import MarketRegime



# 🔧 Mock Adapter


# 🔧 Fixture for initialized engine
from unittest.mock import AsyncMock, MagicMock
import pytest_asyncio
from dynamic_risk_engine.dynamic_risk_engine import DynamicRiskEngine
from dynamic_risk_engine.cognitive_market_regime_classifier import MarketRegime

@pytest_asyncio.fixture
async def initialized_engine():
    # Mocks
    mock_adapter = MagicMock()
    mock_adapter.get_account_balance = AsyncMock(return_value=100_000.0)
    mock_adapter.get_account = AsyncMock(return_value=100_000.0)

    mock_confidence = MagicMock()
    mock_confidence.get_current_confidence = MagicMock(return_value=0.8)
    mock_confidence.get_confidence_breakdown = MagicMock(return_value={"confidence": 0.8, "streak": 5})
    mock_confidence.reset = MagicMock()
    mock_confidence.update_signal_result = MagicMock()

    mock_tracker = MagicMock()
    mock_tracker.win_rate = MagicMock(return_value=0.75)
    mock_tracker.average_rrr = MagicMock(return_value=2.0)
    mock_tracker.profit_factor = MagicMock(return_value=1.5)
    mock_tracker.get_equity_curve = MagicMock(return_value=[])
    mock_tracker.reset = MagicMock()
    mock_tracker.record_trade = MagicMock()


    mock_drawdown = MagicMock()
    mock_drawdown.initialize = AsyncMock()
    mock_drawdown.get_daily_drawdown_limit = MagicMock(return_value=-0.1)
    mock_drawdown.is_trading_halted = MagicMock(return_value=False)
    mock_drawdown.in_drawdown_limit = MagicMock(return_value=True)
    mock_drawdown.reset_daily_drawdown = MagicMock()
    mock_drawdown.record_pnl = MagicMock()

    mock_sizer = MagicMock()
    mock_sizer.initialize = AsyncMock()
    mock_sizer.calculate_position_size = AsyncMock(return_value=100.0)
    mock_sizer.reset = AsyncMock()
    mock_sizer.max_risk_per_trade = 0.03
    mock_sizer.account_balance = mock_adapter
    mock_sizer.drawdown = mock_drawdown
    mock_sizer.reset = AsyncMock(return_value=mock_sizer)


    mock_throttle = MagicMock()
    mock_throttle.can_trade = MagicMock(return_value=True)
    mock_throttle.is_in_cooldown = MagicMock(return_value=False)
    mock_throttle.register_trade_result = MagicMock()
    mock_throttle.reset = MagicMock(return_value=mock_throttle)

    mock_orderbook = MagicMock()
    mock_orderbook.get_volatility_estimate = MagicMock(return_value=0.02)
    mock_orderbook._update_midprice = MagicMock()
    mock_orderbook.price_history = []
    mock_orderbook.bids = {}
    mock_orderbook.asks = {}
    mock_orderbook.last_update_ts = None

    mock_cancel_window = MagicMock()
    mock_cancel_window._flags = []

    mock_regime = MagicMock()
    mock_regime.update_regime = MagicMock(side_effect=[
        MarketRegime.UNKNOWN, #First Call
        MarketRegime.VOLATILE
    ])
    mock_regime.get_regime_duration_seconds = MagicMock(return_value=0.5)
    mock_regime.get_regime_stability = MagicMock(return_value=1.0)
    mock_regime.regime_history = [MarketRegime.UNKNOWN]

    # Engine
    engine = DynamicRiskEngine(
        daily_drawdown_limit=mock_drawdown,
        performance_tracker=mock_tracker,
        signal_confidence=mock_confidence,
        dynamic_position_sizer=mock_sizer,
        throttle_cooldown_manager=mock_throttle,
        binance_adapter=mock_adapter,
        orderbook=mock_orderbook,
        cancel_window=mock_cancel_window,
        market_regime_classifier=mock_regime
    )

    await engine.initialize()
    return engine


# ✅ Test Cases

@pytest.mark.asyncio
async def test_initial_state(initialized_engine):
    diagnostic = await initialized_engine.get_diagnostic()
    assert diagnostic['can_trade'] is True
    assert diagnostic['drawdown_triggered'] is False
    assert diagnostic['cooldown_active'] is False
    assert diagnostic['position_size_for_1_sl'] > 0
    assert diagnostic['current_confidence'] == 0.8
    assert diagnostic['current_win_rate'] == 0.75
    assert diagnostic['average_rrr'] == 2.0
    assert diagnostic['equity_curve'] == []
    assert diagnostic['market_regime'] == MarketRegime.UNKNOWN.value

@pytest.mark.asyncio
async def test_register_trade_win_updates_all_modules(initialized_engine):
    initialized_engine.register_trade(
        pnl=100.0,
        risk=50.0,
        reward=150,
        signal_id="signal_1",
        was_correct=True,
        metadata={"strategy": "test_strategy"}
    )
    diagnostic = await initialized_engine.get_diagnostic()
    assert diagnostic['equity_curve'] == []
    assert diagnostic['drawdown_triggered'] is False
    assert diagnostic['cooldown_active'] is False

@pytest.mark.asyncio
async def test_register_trade_loss_and_cooldown_triggered(initialized_engine):
    losses = []

    def register_trade_result(pnl):
        losses.append(pnl)
        if sum(losses) < -100:
            initialized_engine.throttle_cooldown_manager.is_in_cooldown = MagicMock(return_value=True)
            initialized_engine.throttle_cooldown_manager.can_trade = MagicMock(return_value=False)

    initialized_engine.throttle_cooldown_manager.register_trade_result = MagicMock(side_effect=register_trade_result)

    initialized_engine.register_trade(pnl=-50.0, risk=50.0, reward=100, signal_id="signal_2", was_correct=False)
    initialized_engine.register_trade(pnl=-30.0, risk=50.0, reward=100, signal_id="signal_3", was_correct=False)
    initialized_engine.register_trade(pnl=-70.0, risk=50.0, reward=100, signal_id="signal_4", was_correct=False)

    diagnostic = await initialized_engine.get_diagnostic()
    assert diagnostic['cooldown_active'] is True
    assert initialized_engine.can_trade() is False


@pytest.mark.asyncio
async def test_position_size_scaling(initialized_engine):
    position_size = await initialized_engine.get_position_size(stop_loss_distance=5)
    assert position_size > 0.01

@pytest.mark.asyncio
async def test_engine_reset(initialized_engine):
    await initialized_engine.reset()
    diagnostic = await initialized_engine.get_diagnostic()
    assert diagnostic['equity_curve'] == []
    assert diagnostic['drawdown_triggered'] is False
    assert diagnostic['cooldown_active'] is False
    assert diagnostic['position_size_for_1_sl'] > 0

@pytest.mark.asyncio
async def test_confidence_decay_behavior(initialized_engine):
    confidence = initialized_engine.signal_confidence_calibrator.get_current_confidence()
    assert confidence == 0.8
    assert (await initialized_engine.get_diagnostic())['confidence_breakdown']['confidence'] == confidence

@pytest.mark.asyncio
async def test_risk_curve_value_alignment(initialized_engine):
    risk_value = initialized_engine.get_risk_curve_value()
    assert 0.005 <= risk_value <= 0.05

@pytest.mark.asyncio
async def test_regime_transition_tracking(initialized_engine):
    initialized_engine.update_market_regime()
    initial_regime = initialized_engine.current_regime
    initialized_engine.cancel_window._flags.append({
        "type": "CANCEL_DENSITY_SPIKE",
        "price": 100,
        "side": "bid",
        "timestamp": time.time(),
        "cancel_count": 500,
        "orderid": "spoof_test"
    })
    initialized_engine.orderbook.price_history.extend([100, 150, 80, 160, 70])
    initialized_engine.orderbook.bids = {100: 0.1}
    initialized_engine.orderbook.asks = {101: 200}
    initialized_engine.orderbook.last_update_ts = time.time() - 0.1
    initialized_engine.orderbook._update_midprice()
    initialized_engine.update_market_regime()
    new_regime = initialized_engine.current_regime
    assert new_regime != initial_regime
    assert new_regime == MarketRegime.VOLATILE
    assert initialized_engine.market_regime_classifier.get_regime_duration_seconds() < 2.0

@pytest.mark.asyncio
async def test_regime_stability_metric(initialized_engine):
    for _ in range(10):
        initialized_engine.market_regime_classifier.regime_history.append(MarketRegime.TRENDING)
    stability = initialized_engine.market_regime_classifier.get_regime_stability()
    assert stability == 1.0

@pytest.mark.asyncio
async def test_diagnostic_integrity(initialized_engine):
    diagnostic = await initialized_engine.get_diagnostic()
    expected_keys = [
        'can_trade', 'position_size_for_1_sl', 'current_confidence',
        'current_win_rate', 'average_rrr', 'profit_factor',
        'drawdown_triggered', 'cooldown_active', 'equity_curve',
        'market_regime', 'regime_duration_seconds', 'regime_stability',
        'regime_history_tail', 'confidence_breakdown', 'risk_curve_value'
    ]
    for key in expected_keys:
        assert key in diagnostic
