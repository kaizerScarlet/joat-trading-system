import json, gzip, pytest, pathlib
from replay.replay_runner import run


GT_PATH = pathlib.Path("data/fixtures/ground_truth_flags.jsonl.gz")

def load_gt():
    with gzip.open(GT_PATH, 'rt') as f:
        return [json.loads(x) for x in f]
    
def calc_scores(pred, gt):
    gt_set = {(f['ts'], f['event']) for f in gt }
    pred_set = {(f['ts'], f['event']) for  f in pred }
    tp = len(pred_set & gt_set)
    fp = len(pred_set - gt_set)
    fn = len(gt_set - pred_set)
    precision = tp / (tp+fp) if tp+fp else 1
    recall = tp / (tp+fn) if tp + fn else 1

    return precision, recall


def test_replay_precision_recall():
    pred = run()
    gt = load_gt()
    precision, recall = calc_scores(pred, gt)
    assert precision >= 0.99
    assert recall >= 0.98