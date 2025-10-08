import pytest
import time
import pytest_asyncio
from dynamic_risk_engine.dynamic_risk_engine_protocol import DynamicRiskEngineProtocol
from dynamic_risk_engine.dynamic_risk_engine import DynamicRiskEngine
from dynamic_risk_engine.cognitive_market_regime_classifier import MarketRegime
from Execution_layer.binance_adapter_protocol import BinanceExecutionAdapterProtocol
from dynamic_risk_engine.performance_tracker_protocol import PerformanceTrcakerProtocol
from dynamic_risk_engine.signal_confidence_calibrator_protocol import SignalConfidenceCalibratorProtocol


# 🔧 Mock Adapter
class MockBinanceAdapter(BinanceExecutionAdapterProtocol):
    async def get_account_balance(self):
        return 100_000.0

    async def get_account(self):
        return 100_000.0

    def _sign(self, data):
        return "mock_signature"

    async def _signed_request(self, method, endpoint, params):
        return {"status": "mocked"}

# 🔧 Mock Confidence Calibrator
class MockConfidenceCalibrator(SignalConfidenceCalibratorProtocol):
    def get_current_confidence(self):
        return 0.8

    def get_confidence_breakdown(self):
        return {"confidence": 0.8, "streak": 5}

    def reset(self):
        pass

    def update_signal_result(self, signal_id, was_correct):
        pass

# 🔧 Mock Performance Tracker
class MockPerformanceTracker(PerformanceTrcakerProtocol):
    def win_rate(self):
        return 0.75

    def average_rrr(self):
        return 2.0

    def profit_factor(self):
        return 1.5

    def get_equity_curve(self):
        return []

    def reset(self):
        pass

    def record_trade(self, pnl, risk, reward, metadata=None):
        pass

# 🔧 Fixture for initialized engine
@pytest_asyncio.fixture
async def initialized_engine():
    engine : DynamicRiskEngineProtocol = DynamicRiskEngine(daily_drawdown_limit=0.25)

    mock_adapter = MockBinanceAdapter()
    mock_confidence = MockConfidenceCalibrator()
    mock_tracker = MockPerformanceTracker()

    engine.binance_adapter = mock_adapter
    engine.dynamic_position_sizer.account_balance = mock_adapter
    engine.dynamic_position_sizer.drawdown.account_balance = mock_adapter
    engine.daily_drawdown_manager.account_balance = mock_adapter

    engine.signal_confidence_calibrator = mock_confidence
    engine.performance_tracker = mock_tracker

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
