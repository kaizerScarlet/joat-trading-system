import gzip
import json
from datetime import datetime, timedelta

base_ts = int(datetime.utcnow().timestamp()*1000)

#1. Order Books updates (L2)
l2_updates = [
    {"e": "depthUpdate", "E": base_ts, "b": [["30000.0","1.5"]], "a":[["30010.0","2.0"]]},
    {"e": "depthUpdate", "E": base_ts + 1000, "b": [["30000.0","0"]]}, #Cancel bid

]

#2. Trade (Time & Sales)
trades = [
    {"e": "trade", "E": base_ts + 2000, "p": "30010.0", "q": "1.0", "T": base_ts + 2000, "m":False},
]


#3 Ground truth expected output (cancel & fill flags)
ground_truth = [
    {"timestamp": base_ts + 1000, "type":"cancel", "price":"30000.0","side":"bid"},
    {"timestamp": base_ts + 2000, "type":"fill", "price":"30010.0","side":"ask"},
    {"timestamp": base_ts + 3000, "type":"fill", "price":"30020.0","side":"ask"},
    {"timestamp": base_ts + 4000, "type":"partial_fill", "price":"30030.0", "side":"ask"},
]


def save_jsonl_gz(filename, data):
    with gzip.open(filename, "wt", encoding="utf-8") as f:
        for item in data:
            json.dump(item, f)
            f.write("\n")


#save files
save_jsonl_gz("data/fixtures/btcusdt_10min_l2.jsonl.gz", l2_updates)
save_jsonl_gz("data/fixtures/btcusdt_10min_trades.jsonl.gz", trades)
save_jsonl_gz("data/fixtures/ground_truth_flags.jsonl.gz", ground_truth)