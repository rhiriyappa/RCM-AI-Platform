"""tests/extraction/test_eval_harness.py — F1 regression gate against gold set."""
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from contracts.schemas import ClassificationResult, DocumentType, RawDocument, SourceType
from extraction.engine import ExtractionEngine
from extraction.enrichment import CodeValidator, ExtractionEnricher, MockNPILookup

GOLD = Path(__file__).parent.parent / "fixtures" / "gold_extractions_p2.jsonl"
F1_THRESHOLD = 0.80


def mock_engine(expected: dict) -> ExtractionEngine:
    def llm(s, u): return json.dumps(
        {k: {"value": v, "confidence": 0.95} if not isinstance(v, list)
            else [{"value": c, "confidence": 0.95} for c in v]
         for k, v in expected.items()})
    return ExtractionEngine(call_llm=llm, enricher=ExtractionEnricher(MockNPILookup(), CodeValidator()))


def score(actual, expected):
    if isinstance(expected, list):
        exp = {str(v).upper() for v in expected}
        act = {str(v).upper() for v in (actual or [])}
        if not exp and not act:
            return 1.0
        if not exp or not act:
            return 0.0
        i = exp & act
        p, r = len(i)/len(act), len(i)/len(exp)
        return 2*p*r/(p+r) if (p+r) > 0 else 0.0
    return 1.0 if str(actual).strip() == str(expected).strip() else 0.0


@pytest.mark.skipif(not GOLD.exists(), reason="gold fixture not found")
class TestEvalHarness:
    def test_gold_exists(self):    assert GOLD.exists()

    def test_mean_f1(self):
        records = [json.loads(line) for line in GOLD.read_text().splitlines() if line.strip()]
        all_f1 = []
        for rec in records:
            eng = mock_engine(rec.get("expected", {}))
            doc = RawDocument(document_id=rec["doc_id"], source_id="gold",
                              source_type=SourceType.FHIR_R4,
                              ingested_at=datetime.now(UTC),
                              full_text=rec.get("text", ""))
            clf = ClassificationResult(document_id=doc.document_id,
                                       document_type=DocumentType(rec["expected_type"]),
                                       confidence=0.95, method="gold", routing_queue="test")
            result = eng.extract(doc, clf)
            for fname, exp_val in rec.get("expected", {}).items():
                if fname in ("diagnosis_codes", "procedure_codes", "denial_reason_codes"):
                    act = [f.value for f in getattr(result, fname, [])]
                else:
                    fobj = getattr(result, fname, None)
                    act  = fobj.value if fobj else None
                all_f1.append(score(act, exp_val))
        mean = sum(all_f1)/len(all_f1) if all_f1 else 0.0
        assert mean >= F1_THRESHOLD, f"Eval F1 {mean:.3f} < {F1_THRESHOLD}"
