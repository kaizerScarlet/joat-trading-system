from cancel_window.cancel_window_tuner import CancelWindowTuner
import pytest 

def test_window_tuner_score():
    # Synthetic add + cancel sequences
    synthetic_events = [
        {"E": 1000, "a": [["100.1", "5"]]},   # Add spoof
        {"E": 1020, "a": [["100.1", "0"]]},   # Cancel spoof
        {"E": 1200, "a": [["100.2", "1"]]},   # Add normal
        {"E": 1220, "a": [["100.2", "0"]]},   # Cancel normal
        {"E": 1400, "b": [["100.3", "4"]]},   # Add spoof
        {"E": 1425, "b": [["100.3", "0"]]},   # Cancel spoof
        {"E": 2000, "a": [["100.5", "0.4"]]}, # No add first → no spoof

    ]

    # Labels only for cancels we want to evaluate (True=spoof)
    labels = [True, False]

    # Tune and assert
    tuner = CancelWindowTuner(synthetic_events, labels)
    results = tuner.tune([50, 100, 200])

    for win in [50, 100, 200]:
        assert 'precision' in results[win]
        assert 'recall' in results[win]
        assert 'f1_score' in results[win]

    assert results[50]['f1_score'] <= results[200]['f1_score']


def test_tuner_with_all_spoofing():
    synthetic_events = [
        {"E": 1000, "a": [["100.0", "5"]]},
        {"E": 1020, "a": [["100.0", "0"]]},
        {"E": 1400, "a": [["100.0", "5"]]},
        {"E": 1430, "a": [["100.0", "0"]]},
        {"E": 1800, "a": [["100.0", "5"]]},
        {"E": 1830, "a": [["100.0", "0"]]},
    ]

    labels = [True, True, True]

    tuner = CancelWindowTuner(synthetic_events, labels)
    result = tuner.tune([200])
    metrics = result[200]

    assert metrics['precision'] >= 0.8
    assert metrics['recall'] >= 0.8
