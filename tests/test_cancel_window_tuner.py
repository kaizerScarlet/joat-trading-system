from cancel_window.cancel_window_tuner import CancelWindowTuner

def test_window_tuner_score():
    #Create Synthethic test dataset with both spoofing and non-spoofing
    historical_events = [
        {'timestamp' : 1000, 'price': 100.1, 'side': 'ask', 'size':5},  #spoof
        {'timestamp' : 1020, 'price': 100.1, 'side': 'ask', 'size':5},  #spoof
        {'timestamp' : 1200, 'price': 100.2, 'side': 'ask', 'size':1},  #normal
        {'timestamp' : 1400, 'price': 100.3, 'side': 'bid', 'size':4},  #spoof
        {'timestamp' : 1500, 'price': 100.3, 'side': 'bid', 'size':4},  #spoof
        {'timestamp' : 2000, 'price': 100.5, 'side': 'ask', 'size':0.4},  #normal

    ]

    #True labels for spoof detection
    ground_truth = [True, True, False, True, True, False]


    #Run tuner
    tuner = CancelWindowTuner(historical_events, ground_truth)
    results = tuner.tune([50,100,200])

    #Assert expected structure
    for win in [50, 100, 200]:
        assert 'precision' in results[win]
        assert 'recall' in results[win]
        assert 'f1_score' in results[win]

    #Optional: check f1_scores improve with tuning
    assert results[50]['f1_score'] <= results[200]['f1_score'] #maybe better at higher window


def test_tuner_with_all_spoofing():
    events = [
        {'timestamp' : 1000, 'price': 100.0, 'side': 'ask', 'size':5},  #spoof
        {'timestamp' : 1020, 'price': 100.0, 'side': 'ask', 'size':5},  #spoof
        {'timestamp' : 1400, 'price': 100.0, 'side': 'ask', 'size':5},  #spoof
    ]

    labels = [True, True, True]

    tuner = CancelWindowTuner(events, labels)
    result = tuner.tune([200])
    metrics = result[200]


    assert metrics['precision'] >= 0.5
    assert metrics['recall'] >= 0.5