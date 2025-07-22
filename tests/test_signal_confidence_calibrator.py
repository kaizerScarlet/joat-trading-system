import pytest 
from dynamic_risk_engine.signal_confidence_calibrator import SignalConfidenceCalibrator


def test_initial_confidence_returns_base():
    calibrator = SignalConfidenceCalibrator(base_confidence=0.7)
    assert calibrator.get_current_confidence() == 0.7

def test_single_correct_signal_boosts_confidence():
    calibrator = SignalConfidenceCalibrator(base_confidence=0.5)
    calibrator.update_signal_result('signal1', True)
    assert calibrator.get_current_confidence() == 1.0  # 1 correct out of 1

def test_mixed_signals_adjusts_confidence_correctly():
    calibrator = SignalConfidenceCalibrator(base_confidence=0.5)
    calibrator.update_signal_result('signal1', True)
    calibrator.update_signal_result('signal2', False)
    calibrator.update_signal_result('signal3', True)
    # Reset to clear history
    # 2 correct out of 3
    assert calibrator.get_current_confidence() == 0.6667


def test_reset_clears_history():
    calibrator = SignalConfidenceCalibrator(base_confidence=0.5)
    calibrator.update_signal_result('signal1', True)
    calibrator.update_signal_result('signal2', False)
    calibrator.update_signal_result('signal3', True)
    calibrator.reset()
    assert calibrator.get_current_confidence() == 0.5  # Should return to base confidence
    assert not calibrator.signal_history  # History should be cleared


def test_precision_rounding():
    calibrator  = SignalConfidenceCalibrator(base_confidence=0.5)
    #7 out of 10 correct 0.7
    for i in range(7):
        calibrator.update_signal_result(f'signal{i}', True)
    for i in range(3):
        calibrator.update_signal_result(f'signal{i+7}', False)

    assert calibrator.get_current_confidence() == 0.7  # Should round to 4 decimal places
    assert len(calibrator.signal_history) == 10  # History should contain all signals
    assert calibrator.compute_adjusted_confidence() == 0.7  # Should match computed confidence


def test_multiple_resets():
    calibrator = SignalConfidenceCalibrator(base_confidence=0.5)
    calibrator.update_signal_result('signal1', True)
    calibrator.update_signal_result('signal2', False)
    calibrator.reset()
    assert calibrator.get_current_confidence() == 0.5  # After reset, should return to base confidence
    calibrator.update_signal_result('signal3', True)
    assert calibrator.get_current_confidence() == 1.0  # Now should be 1 correct out of 1 after reset
    calibrator.reset()
    assert calibrator.get_current_confidence() == 0.5  # Reset again, back to base confidence