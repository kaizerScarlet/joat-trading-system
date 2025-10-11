import pytest 
from dynamic_risk_engine.signal_confidence_calibrator import SignalConfidenceCalibrator
from dynamic_risk_engine.signal_confidence_calibrator_protocol import SignalConfidenceCalibratorProtocol

def test_initial_confidence_returns_base():
    calibrator : SignalConfidenceCalibratorProtocol = SignalConfidenceCalibrator(base_confidence=0.7)
    assert calibrator.get_current_confidence() == 0.7

def test_single_correct_signal_boosts_confidence():
    calibrator : SignalConfidenceCalibratorProtocol = SignalConfidenceCalibrator(base_confidence=0.5)
    calibrator.update_signal_result('signal1', True)
    assert calibrator.get_current_confidence() == 1.0  # 1 correct out of 1

def test_mixed_signals_adjusts_confidence_correctly():
    calibrator : SignalConfidenceCalibratorProtocol = SignalConfidenceCalibrator(base_confidence=0.5)
    calibrator.update_signal_result('signal1', True)
    calibrator.update_signal_result('signal2', False)
    calibrator.update_signal_result('signal3', True)
    # Reset to clear history
    # 2 correct out of 3
    assert round(calibrator.get_current_confidence(), 4) == 0.667
    assert abs(calibrator.get_current_confidence() - 0.667) < 0.001


def test_reset_clears_history():
    calibrator : SignalConfidenceCalibratorProtocol = SignalConfidenceCalibrator(base_confidence=0.5)
    calibrator.update_signal_result('signal1', True)
    calibrator.update_signal_result('signal2', False)
    calibrator.update_signal_result('signal3', True)
    calibrator.reset()
    assert calibrator.get_current_confidence() == 0.5  # Should return to base confidence
    assert not calibrator.signal_history  # History should be cleared


def test_precision_rounding():
    calibrator  : SignalConfidenceCalibratorProtocol = SignalConfidenceCalibrator(base_confidence=0.5)
    #7 out of 10 correct 0.7
    for i in range(7):
        calibrator.update_signal_result(f'signal{i}', True)
    for i in range(3):
        calibrator.update_signal_result(f'signal{i+7}', False)

    assert calibrator.get_current_confidence() == 0.6446  # Should round to 4 decimal places
    assert len(calibrator.signal_history) == 10  # History should contain all signals
    assert calibrator.compute_adjusted_confidence() == 0.6446 # Should match computed confidence


def test_multiple_resets():
    calibrator : SignalConfidenceCalibratorProtocol = SignalConfidenceCalibrator(base_confidence=0.5)
    calibrator.update_signal_result('signal1', True)
    calibrator.update_signal_result('signal2', False)
    calibrator.reset()
    assert calibrator.get_current_confidence() == 0.5  # After reset, should return to base confidence
    calibrator.update_signal_result('signal3', True)
    assert calibrator.get_current_confidence() == 1.0  # Now should be 1 correct out of 1 after reset
    calibrator.reset()
    assert calibrator.get_current_confidence() == 0.5  # Reset again, back to base confidence


def test_confidence_breakdown_structure():
    calibrator : SignalConfidenceCalibratorProtocol = SignalConfidenceCalibrator(base_confidence=0.5)
    for i in range(12):
        calibrator.update_signal_result(f'signal{i}', was_correct=(i % 2 == 0))
    breakdown = calibrator.get_confidence_breakdown()
    assert "confidence" in breakdown
    assert "recent_streak" in breakdown
    assert isinstance(breakdown["recent_streak"], list)
    assert len(breakdown["recent_streak"]) == 10


def test_summary_snapshot():
    calibrator : SignalConfidenceCalibratorProtocol = SignalConfidenceCalibrator(base_confidence=0.5)
    for i in range(10):
        calibrator.update_signal_result(f'signal{i}', was_correct=(i < 7))  # 7 wins
    summary = calibrator.get_summary()
    assert summary["total_signals"] == 10
    assert summary["current_confidence"] == calibrator.get_current_confidence()
    assert summary["recent_accuracy"] == pytest.approx(0.7, 0.01)


def test_last_signal_trace():
    calibrator : SignalConfidenceCalibratorProtocol = SignalConfidenceCalibrator()
    calibrator.update_signal_result("signalX", True)
    last = calibrator.get_last_signal()
    assert last["signal_id"] == "signalX"
    assert last["was_correct"] is True
