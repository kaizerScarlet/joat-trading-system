import gzip, json, time
from pathlib import Path
from cancel_window.simple_cancel_window import SimpleCancelWindow

def stream(path):
    with gzip.open(path, 'rt') as f:
        for line in f: yield json.loads(line)

def run():
    cw = SimpleCancelWindow(window_ms =75)
    for l2 in stream("data/fixtures/btcusdt_10min.jsonl.gz"):
        cw.process_l2_update(l2)
    
    for t in stream("data/fixtures/btcusdt_10min_trades.jsonl.gz"):
        cw.process_trade(t)

    return cw.flush_flags()

if __name__ == "__main__":
    flags = run()
    Path("replay_output.json").write_text(json.dumps(flags, ident=2))
