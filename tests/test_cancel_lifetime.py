import pytest 
from cancel_window.simple_cancel_window import SimpleCancelWindow

def test_fast_cancel_flag():
    cw = SimpleCancelWindow(window_ms=100)

    #add level at t0
    cw.process_l2_update({"E": 1000, "b": [["30000", "1.0"]], "a": []})
    # cancel same level 20ms later
    cw.process_l2_update({"E": 1020, "b": [["30000", "0"]], "a": []})

    flags = cw.flush_flags()
    assert flags and flags[0]["type"] == "CANCEL_SPOOF"
    assert flags[0]["latency_ms"] == 20