import json, gzip, pytest, pathlib
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))

from replay.replay_runner import run


GT_PATH = pathlib.Path("data/fixtures/ground_truth_flags.jsonl.gz")

def load_gt():
    with gzip.open(GT_PATH, 'rt') as f:
        return [json.loads(x) for x in f]
    
def calc_scores(pred, gt):
    gt_set = {(f['timestamp'], f['type']) for f in gt }
    pred_set = {(f['timestamp'], f['type']) for  f in pred }
    tp = len(pred_set & gt_set)
    fp = len(pred_set - gt_set)
    fn = len(gt_set - pred_set)
    precision = tp / (tp+fp) if tp+fp else 1
    recall = tp / (tp+fn) if tp + fn else 1

    return precision, recall

def validate_flags(flags: list[dict], name: str):
    required = {"timestamp", "type"}
    for i, f in enumerate(flags):
        missing = required - f.keys()
        if missing:
            raise ValueError(f"Missing keys {missing} in {name}[{i}]: {f}")


def test_replay_precision_recall():
    pred = run()
    gt = load_gt()
    precision, recall = calc_scores(pred, gt)

    validate_flags(gt, "ground_truth")
    validate_flags(pred, "predictions")
    assert precision >= 0.9
    assert recall >= 0.9