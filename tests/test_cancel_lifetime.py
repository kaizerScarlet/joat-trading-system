import time #will need to change this at production so that it is the server time taken not my machine time
import pytest 
from cancel_window.simple_cancel_window import SimpleCancelWindow

#test fast cancel on bid side
def test_fast_cancel_flag_bid():
    cw = SimpleCancelWindow()

    #add level at t0
    cw.process_l2_update({"E": 1000, "b": [["30000", "1.0"]], "a": []})
    # cancel same level 20ms later
    cw.process_l2_update({"E": 1020, "b": [["30000", "0"]], "a": []})

    flags = cw.flush_flags()
    print(flags)
    assert flags and flags[0]["type"] == "CANCEL_SPOOF"
    assert flags[0]["latency_ms"] == 20

#test fast cancel on ask side
def test_fast_cancel_flag_ask():
    cw = SimpleCancelWindow()

    #add level at t0
    cw.process_l2_update({"E": 1000, "b": [],   "a": [["30000", "1.0"]]})
    # cancel same level 20ms later
    cw.process_l2_update({"E": 1020, "b": [],   "a": [["30000", "0"]]})

    flags = cw.flush_flags()
    print(flags)
    assert flags and flags[0]["type"] == "CANCEL_SPOOF"
    assert flags[0]["latency_ms"] == 20



#Test True fill flag on ask side
def test_true_fill_flag_ask():
    cw = SimpleCancelWindow()
    #1. add order
    cw.process_l2_update({"E": 1000, "a": [["30050", "2.0"]], "b":[]})
    #2. Cancel order 20ms later
    cw.process_l2_update({"E": 1020, "a": [["30050", "0"]], "b": []})
    #3. Trade hits that price 40ms after cancel
    cw.process_trade({
        "T": 1060,
        "p": "30050",
        "q": "2.0",
        "m": False # buyer is taker
        })
    flags = cw.flush_flags()
    print(flags)
    assert any(f["type"] == "TRUE_FILL" for f in flags)

#Test True fill flag bid
def test_true_fill_flag_bid():
    cw = SimpleCancelWindow()
    #1. add order
    cw.process_l2_update({"E": 1000, "b": [["30050", "2.0"]], "a":[]})
    #2. Cancel order 20ms later
    cw.process_l2_update({"E": 1020, "b": [["30050", "0"]], "a": []})
    #3. Trade hits that price 40ms after cancel
    cw.process_trade({
        "T": 1060,
        "p": "30050",
        "q": "2.0",
        "m": True   #seller is taker
        })
    flags = cw.flush_flags()
    print(flags)
    assert any(f["type"] == "TRUE_FILL" for f in flags)

#Test partial fill flag bid side
#@pytest.mark.asyncio
def test_partial_fill_flag_bid():
    """
    Order is added -> partially removed via  trade smaller than original size
    in <window_ms. Expect PARTIAL_FILL, not TRUE_FILL.
    """
    cw = SimpleCancelWindow()
    #1. add 2 BTC ask @ 30 070
    cw.process_l2_update({"E": 1_000, "b": [["30070", "2.0"]], "a":[]})

    #2. cancel level 20ms later
    cw.process_l2_update({"E": 1_020, "b": [["30070", "0"]], "a": []})
    #3. only 0.5 BTC trades through -> partial
    cw.process_trade({
        "T": 1_040,
        "p": "30070",
        "q": "0.5",
        "m": True     #taker is seller-> hitting bid
    })

    flags = cw.flush_flags()
    print(flags)
    types = [f["type"] for f in flags]
    assert "PARTIAL_FILL" in types
    assert "TRUE_FILL" not in types 


#Test partial fill flag ask side
#@pytest.mark.asyncio
def test_partial_fill_flag_ask():
    """
    Order is added -> partially removed via  trade smaller than original size
    in <window_ms. Expect PARTIAL_FILL, not TRUE_FILL.
    """
    cw = SimpleCancelWindow()
    #1. add 2 BTC ask @ 30 070
    cw.process_l2_update({"E": 1_000, "a": [["30070", "2.0"]], "b":[]})

    #2. cancel level 20ms later
    cw.process_l2_update({"E": 1_020, "a": [["30070", "0"]], "b": []})
    #3. only 0.5 BTC trades through -> partial
    cw.process_trade({
        "T": 1_040,
        "p": "30070",
        "q": "0.5",
        "m": False  #taker is buyer -> hitting ask
    })

    flags = cw.flush_flags()
    print(flags)
    types = [f["type"] for f in flags]
    assert "PARTIAL_FILL" in types
    assert "TRUE_FILL" not in types 


# Test iceberg cancel flag emitted ask side
def test_iceberg_cancel_flag_emitted_ask():
    cw = SimpleCancelWindow()

    base_ts = 100000
    #simulate  3 quick size reductions at same price, no  trades
    #1. Add new ask level at 30090 with size 4.0
    cw.process_l2_update({"E": base_ts, "a": [["30090", "4.0"]], "b": []})
    #2. reduce to 3.0
    cw.process_l2_update({"E": base_ts + 10, "a": [["30090", " 3.0"]], "b": []})
    #3. reduce again to 2.0
    cw.process_l2_update({"E": base_ts + 20, "a": [["30090", "2.0"]], "b": []})
    #4. Cancel (set at 0)
    cw.process_l2_update({"E": base_ts + 30, "a": [["30090", "0"]], "b": []})

    flags = cw.flush_flags()
    print(flags)
    assert len(flags) == 1
    assert flags[0]["type"] == "ICEBERG_CANCEL"
    assert flags[0]["price"] == 30090.0
    assert flags[0]["side"] == "ask"
    assert "reductions" in flags[0]
    assert len(flags[0]["reductions"]) == 2

#Test iceberg cancel flag emitted bid side
def test_iceberg_cancel_flag_emitted_bid():
    cw = SimpleCancelWindow()

    base_ts = 100000
    #simulate  3 quick size reductions at same price, no  trades
    #1. Add new ask level at 30090 with size 4.0
    cw.process_l2_update({"E": base_ts, "b": [["30090", "4.0"]], "a": []})
    #2. reduce to 3.0
    cw.process_l2_update({"E": base_ts + 10, "b": [["30090", " 3.0"]], "a": []})
    #3. reduce again to 2.0
    cw.process_l2_update({"E": base_ts + 20, "b": [["30090", "2.0"]], "a": []})
    #4. Cancel (set at 0)
    cw.process_l2_update({"E": base_ts + 30, "b": [["30090", "0"]], "a": []})

    flags = cw.flush_flags()
    print(flags)
    assert len(flags) == 1
    assert flags[0]["type"] == "ICEBERG_CANCEL"
    assert flags[0]["price"] == 30090.0
    assert flags[0]["side"] == "bid"
    assert "reductions" in flags[0]
    assert len(flags[0]["reductions"]) == 2


#Test no iceberg if only one reduction ask
def test_no_iceberg_if_only_one_reduction_ask():
    cw = SimpleCancelWindow()

    base_ts = 100000
    #simulate  3 quick size reductions at same price, no  trades
    #1. Add new ask level at 30090 with size 5.0
    cw.process_l2_update({"E": base_ts, "a": [["30090", "5.0"]], "b": []})
    #3. reduce to 2.0
    cw.process_l2_update({"E": base_ts + 20, "a": [["30090", "2.0"]], "b": []})
    #4. Cancel (set at 0)
    cw.process_l2_update({"E": base_ts + 30, "a": [["30090", "0"]], "b": []})
    
    flags = cw.flush_flags()
    assert len(flags) == 1
    assert flags[0]["type"] == "CANCEL_SPOOF"


#Test no iceberg if only one reduction bid
def test_no_iceberg_if_only_one_reduction_bid():
    cw = SimpleCancelWindow()

    base_ts = 100000
    #simulate  3 quick size reductions at same price, no  trades
    #1. Add new ask level at 30090 with size 5.0
    cw.process_l2_update({"E": base_ts, "b": [["30090", "5.0"]], "a": []})
    #3. reduce to 2.0
    cw.process_l2_update({"E": base_ts + 20, "b": [["30090", "2.0"]], "a": []})
    #4. Cancel (set at 0)
    cw.process_l2_update({"E": base_ts + 30, "b": [["30090", "0"]], "a": []})
    
    flags = cw.flush_flags()
    assert len(flags) == 1
    assert flags[0]["type"] == "CANCEL_SPOOF"



#Test no iceberg if cancel outside window on the ask side
def test_no_iceberg_if_cancel_outside_window_ask():
    cw = SimpleCancelWindow()

    base_ts = 100000
    #simulate  3 quick size reductions at same price, no  trades
    #1. Add new ask level at 30090 with size 5.0
    cw.process_l2_update({"E": base_ts, "a": [["30090", "5.0"]], "b": []})
    #3. reduce to 2.0
    cw.process_l2_update({"E": base_ts + 20, "a": [["30090", "2.0"]], "b": []})
    #4. Cancel (set at 0)
    cw.process_l2_update({"E": base_ts + 30, "a": [["30090", "0"]], "b": []})
    
    flags = cw.flush_flags()
    #No iceberg or spoof because outside window
    assert len(flags) == 0


#Test no iceberg if cancel outside window on the bid side
def test_no_iceberg_if_cancel_outside_window_bid():
    cw = SimpleCancelWindow()

    base_ts = 100000
    #simulate  3 quick size reductions at same price, no  trades
    #1. Add new ask level at 30090 with size 5.0
    cw.process_l2_update({"E": base_ts, "b": [["30090", "5.0"]], "a": []})
    #3. reduce to 2.0
    cw.process_l2_update({"E": base_ts + 20, "b": [["30090", "2.0"]], "a": []})
    #4. Cancel (set at 0)
    cw.process_l2_update({"E": base_ts + 30, "b": [["30090", "0"]], "a": []})
    
    flags = cw.flush_flags()
    #No iceberg or spoof because outside window
    assert len(flags) == 0


#Test Cancel Density flag ask side
def test_high_cancel_density_flag_ask():
    cw = SimpleCancelWindow()
    cw.set_cancel_density_params(initial_threshold=3, initial_window_ms=100)

    base_ts = 100000
    #simulate  3 quick size reductions at same price, no  trades
    #1. Add new ask level at 30090 with size 5.0
    cw.process_l2_update({"E": base_ts, "a": [["30090", "5.0"]], "b": []})
    #2. Cancel to 0
    cw.process_l2_update({"E": base_ts + 20, "a": [["30090", "0"]], "b": []})
    #3. add
    cw.process_l2_update({"E": base_ts + 30, "a": [["30090", "2.0"]], "b": []})
    #4  Cancel
    cw.process_l2_update({"E": base_ts + 40, "a": [["30090", "0"]], "b": []})
    #5. Add
    cw.process_l2_update({"E": base_ts + 50, "a": [["30090", "2.0"]], "b": []})
    #6. Cancel
    cw.process_l2_update({"E": base_ts + 30, "a": [["30090", "0"]], "b": []})
    
    flags = cw.flush_flags()
    
    #Should contain HIGH_CANCEL_DENSITY
    density_flags = [f for f in flags if f["type"] ==  "HIGH_CANCEL_DENSITY"]
    assert len(density_flags) > 0
    print("Test Passed. High_CANCEL_DENSITY triggered", density_flags)



#Test Cancel Density flag bid side
def test_high_cancel_density_flag_bid():
    cw = SimpleCancelWindow()
    cw.set_cancel_density_params(initial_threshold=3, initial_window_ms=100)

    base_ts = 100000
    #simulate  3 quick size reductions at same price, no  trades
    #1. Add new ask level at 30090 with size 5.0
    cw.process_l2_update({"E": base_ts, "b": [["30090", "5.0"]], "a": []})
    #2. Cancel to 0
    cw.process_l2_update({"E": base_ts + 20, "b": [["30090", "0"]], "a": []})
    #3. add
    cw.process_l2_update({"E": base_ts + 30, "b": [["30090", "2.0"]], "a": []})
    #4  Cancel
    cw.process_l2_update({"E": base_ts + 40, "b": [["30090", "0"]], "a": []})
    #5. Add
    cw.process_l2_update({"E": base_ts + 50, "b": [["30090", "2.0"]], "a": []})
    #6. Cancel
    cw.process_l2_update({"E": base_ts + 30, "b": [["30090", "0"]], "a": []})
    
    flags = cw.flush_flags()
    
    #Should contain HIGH_CANCEL_DENSITY
    density_flags = [f for f in flags if f["type"] ==  "HIGH_CANCEL_DENSITY"]
    assert len(density_flags) > 0
    print("Test Passed. High_CANCEL_DENSITY triggered", density_flags)


#@pytest.mark.skip(reason="REGISTER_CANCEL missing positional arguments, correct it first")
#Test Compute cancel density correctly
def test_cancel_density_computation():
    cw = SimpleCancelWindow()
    # Simple 10 cancels at level 100, 5 at  101, 1 at 102
    for _ in range(10):
        cw.register_cancel(price=100.0, side='ask', timestamp=123456789, size=1.0)
    for _ in range(5):
        cw.register_cancel(price=102.0, side='ask', timestamp=123456789, size=1.0)
    cw.register_cancel(price=103.0, side='ask', timestamp=123456789, size=1.0)


    density = cw.get_cancel_density('ask')
    assert density[100.0] == 10
    assert density[102.0] == 5
    assert density[103.0] == 1

#@pytest.mark.skip(reason="REGISTER_CANCEL missing positional arguments, correct it first")
#Test Normalize Cancel Density
def test_normalized_cancel_density():
    cw = SimpleCancelWindow()
    for price, count in [(100.0, 10), (101.0, 5), (102.0, 1)]:
        for _ in range(count):
           cw.register_cancel(price=price, side='ask', timestamp=0, size=1.0)
    
    norm = cw.get_normalized_cancel_density()
    assert norm['num_cancels'] == 16
    assert norm['time_window_ms'] == 0 #since all timestamps were 0
    assert norm['cancel_density_per_sec'] > 0
    assert norm['cancel_density_per_price'] > 0
    assert norm['normalized_score'] > 0


#@pytest.mark.skip(reason="REGISTER_CAMCEL missing positional arguments, correct it")
#Test Clear Density after Flush
def test_cancel_density_flush():
    window = SimpleCancelWindow()
    window.register_cancel(price=100.0,side='ask', timestamp=0, size=5.0)

    window.flush()
    density = window.get_cancel_density('ask')
    assert density == {}



# Test for Icerberg Cancels
def test_iceberg_cancel_detection():
    cw = SimpleCancelWindow()
    ts = 100
    for _ in range(5):
        cw.register_cancel(price= 101.0, side='ask', timestamp=ts, size=2.5)
        ts += 10
    flags = cw.get_flags()
    assert any(f['type'] == 'ICEBERG_CANCEL' for f in flags)


#Test for Orderflow impact scoring
# #Test case 1: High Density + Near mid High Score = high score

#Test-only Mock
class MockOrderBook:
    def get_level_size(self, price, side):
        if price == 100.1:
            return 1.0 #Fixed Book depth
        return 1000.0
#@pytest.mark.skip(reason="UPDATE_BOOK, COMPUTE_IMPACT_SCORE not implemented yet, also has incorrect parameters for REGISTER_CANCEL")
def test_high_impact_cancel():
    cw = SimpleCancelWindow()
    cw.update_book(mid_price=100.0)
    cw.orderbook = MockOrderBook() #Inject Mock dependency
    cw.fill_events = [{'price': 101.0, 'side':'ask'}] * 3
    cw.register_cancel(price=100.1, side='ask',timestamp=0 ,size=5)
    cw.register_cancel(price=100.1, side='ask',timestamp=0 ,size=5)
    cw.register_cancel(price=100.1, side='ask',timestamp=0, size=5)

    score = cw.compute_cancel_impact_score(price=100.1, side='ask')
    assert score >= 0.8


#Test case 2: Far from mid + low = low score
#@pytest.mark.skip(reason="UPDATE_BOOK, COMPUTE_CANCEL_IMPACT_SCORE npt implemented yet, aslo has incorrect parameters for REGISTER_CANCEL")
def test_low_impact_cancel():
    cw = SimpleCancelWindow()
    cw.update_book(mid_price=100.0)
    
    cw.orderbook = MockOrderBook() #Inject Mock dependency
    cw.fill_events = [{'price': 101.0, 'side':'ask'}] * 3
    cw.register_cancel(price=101.0, side='ask',timestamp=123456789 ,size=1)

    score = cw.compute_cancel_impact_score(price=102.0, side='ask')
    assert score <= 0.2



#Test Case 3: Score adjusts After Book Update
#@pytest.mark.skip(reason="UPDATE_BOOK, COMPUTE_CANCEL_IMPACT_SCORE not implemented yet, also has incorrect parameters for REGISTER_CANCEL")
def test_score_changes_with_book():
    cw = SimpleCancelWindow()
    cw.update_book(mid_price=100.0)
    cw.orderbook = MockOrderBook() #Inject Mock dependency
    cw.fill_events = [{'price': 101.0, 'side':'ask'}] * 3
    cw.register_cancel(price=101.0, side='ask',timestamp=123456789, size=1)
    score1 = cw.compute_cancel_impact_score(101.0, 'ask')

    cw.update_book(mid_price=100.5) #Price Moves away from cancel
    score2 = cw.compute_cancel_impact_score(100.2, 'ask')

    assert score2 < score1 # Cancel less relevant now






#Window Tunning Tool Test Cases
#Test Case 1: Load Config and Apply
@pytest.mark.skip(reason="CancelConfig() function not implemented yet")
def test_config_load():
    config = CancelConfig(window_size = 2.0, density_thresh=0.2)
    cw = SimpleCancelWindow(config=config)
    assert cw.config.density_thresh == 0.2



#Test Case 2 Replay maintains order
@pytest.mark.skip(reason="CancelWindowReplayer() function not implemented")
def test_replay_preserves_order():
    replayer = CancelWindowReplayer(data_path='test_orderflow.csv')
    events = replayer.get_events()
    assert events[0].timestamp <= events[1].timestamp   #sorted


#Test Case 3: Tuning increases F1 score
@pytest.mark.skip(reason="SimpleCancelWindowTuner() not implemented")
def test_optimizer_improves_performance():
    tuner = SimpleCancelWindowTuner(...)
    f1_before = tuner.evaluate_baseline()
    f1_after = tuner.optimize()
    assert f1_after > f1_before

