#!/usr/bin/env python3
"""scripts/run_eval.py — run extraction eval against gold JSONL."""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from ingestion.adapters import FHIRBundleAdapter
from ingestion.normalizer import Normalizer

N = Normalizer()


def eval_record(rec: dict) -> dict:
    if rec["source_type"] == "fhir_r4":
        payload = FHIRBundleAdapter().from_json(rec["input"], source_id="eval")
        doc = N.normalize(payload)
        actual = {"patient_name": doc.patient_name, "patient_dob": doc.patient_dob,
                  "diagnosis_codes": sorted(doc.diagnosis_codes),
                  "procedure_codes": sorted(doc.procedure_codes), "payer_id": doc.payer_id}
    else:
        return {"error": f"unsupported source_type: {rec['source_type']}"}
    expected = rec["expected"]
    correct = sum(1 for k, v in expected.items()
                  if (sorted(actual.get(k, [])) == sorted(v) if isinstance(v, list) else actual.get(k) == v))
    return {"score": correct / len(expected) if expected else 0.0,
            "correct": correct, "total": len(expected),
            "actual": actual, "expected": expected}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--gold-set", required=True)
    args = ap.parse_args()
    records = [json.loads(line) for line in Path(args.gold_set).read_text().splitlines() if line.strip()]
    results = [eval_record(r) for r in records]
    scores  = [r["score"] for r in results if "score" in r]
    mean    = sum(scores) / len(scores) if scores else 0.0
    report  = {"total": len(records), "mean_score": round(mean, 4), "results": results}
    Path("eval_report.json").write_text(json.dumps(report, indent=2))
    print(f"Eval: {len(records)} records, mean score {mean:.2%}")
    sys.exit(0 if mean >= 0.90 else 1)


if __name__ == "__main__":
    main()
