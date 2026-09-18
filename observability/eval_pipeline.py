"""observability/eval_pipeline.py — extraction quality evaluation and F1 scoring."""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class FieldScore:
    field_name:    str
    precision:     float
    recall:        float
    f1:            float
    n_expected:    int
    n_actual:      int


@dataclass
class EvalReport:
    total_records:  int
    mean_f1:        float
    field_scores:   list[FieldScore] = field(default_factory=list)
    passed:         bool = True
    threshold:      float = 0.80


def _score_field(actual: any, expected: any) -> float:
    if isinstance(expected, list):
        exp_set = {str(v).upper() for v in expected}
        act_set = {str(v).upper() for v in (actual or [])}
        if not exp_set and not act_set:
            return 1.0
        if not exp_set or not act_set:
            return 0.0
        inter = exp_set & act_set
        p = len(inter) / len(act_set)
        r = len(inter) / len(exp_set)
        return 2 * p * r / (p + r) if (p + r) > 0 else 0.0
    return 1.0 if str(actual).strip() == str(expected).strip() else 0.0


def run_eval(gold_path: str | Path, extractor_fn, threshold: float = 0.80) -> EvalReport:
    gold_path = Path(gold_path)
    records   = [json.loads(line) for line in gold_path.read_text().splitlines() if line.strip()]
    all_f1: list[float] = []

    for rec in records:
        result = extractor_fn(rec)
        for field_name, expected_val in rec.get("expected", {}).items():
            actual_val = result.get(field_name)
            all_f1.append(_score_field(actual_val, expected_val))

    mean_f1 = sum(all_f1) / len(all_f1) if all_f1 else 0.0
    passed  = mean_f1 >= threshold
    logger.info("Eval complete: %d records, mean_f1=%.3f, passed=%s", len(records), mean_f1, passed)
    return EvalReport(total_records=len(records), mean_f1=round(mean_f1, 4),
                      passed=passed, threshold=threshold)
