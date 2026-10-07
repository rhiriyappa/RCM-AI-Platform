"""pipeline/stage_observability.py — Phase 5: LLM call metrics, cost, gold-set eval, run report."""
from __future__ import annotations

import time
from collections import Counter
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from contracts.pipeline import PipelineRecord, PipelineReport
from contracts.schemas import RawDocument, SourceType
from observability.eval_pipeline import EvalReport, run_eval
from observability.metrics import record_call
from pipeline.context import PipelineContext

GOLD_PATH = Path(__file__).parent.parent / "tests" / "fixtures" / "gold_extractions_p2.jsonl"


def instrument(call_fn: Callable[[str, str], str], ctx: PipelineContext, document_id: str, model: str,
               prompt_name: str, prompt_version: str) -> Callable[[str, str], str]:
    """Like observability.metrics.instrumented_llm, but keeps each ModelCallRecord for the report."""
    def wrapper(system: str, user: str) -> str:
        t0 = time.perf_counter()
        try:
            out = call_fn(system, user)
        except Exception as exc:
            ctx.llm_calls.append(record_call(document_id, model, prompt_name, prompt_version, 0, 0,
                                             (time.perf_counter() - t0) * 1000, success=False, error=str(exc)))
            raise
        # Word-count token estimate, same convention as instrumented_llm.
        ctx.llm_calls.append(record_call(document_id, model, prompt_name, prompt_version,
                                         len((system + user).split()) * 4 // 3, len(out.split()) * 4 // 3,
                                         (time.perf_counter() - t0) * 1000))
        return out
    return wrapper


def run_gold_eval(ctx: PipelineContext, gold_path: Path = GOLD_PATH) -> EvalReport:
    """Score the extraction path (classify → extract) against the labelled gold records."""
    from pipeline.stage_agents import flatten_extraction

    def extractor(rec: dict) -> dict:
        doc = RawDocument(document_id=rec["doc_id"], source_id=rec["doc_id"], source_type=SourceType.WEBHOOK,
                          ingested_at=datetime.now(UTC), full_text=rec["text"])
        clf = ctx.classifier.classify(doc)
        return flatten_extraction(ctx.engine.extract(doc, clf))

    return run_eval(gold_path, extractor)


def build_report(records: list[PipelineRecord], ctx: PipelineContext,
                 eval_report: EvalReport | None = None) -> PipelineReport:
    confs = [r.extraction.mean_confidence for r in records if r.extraction]
    stage_ms: dict[str, list[float]] = {}
    for r in records:
        for stage, ms in r.stage_ms.items():
            stage_ms.setdefault(stage, []).append(ms)
    calls = ctx.llm_calls
    return PipelineReport(
        total_records=len(records),
        by_source=dict(Counter(r.source for r in records)),
        by_disposition=dict(Counter(r.disposition.value if r.disposition else "in_flight" for r in records)),
        by_document_type=dict(Counter(r.document.document_type.value for r in records if r.document)),
        by_classifier_method=dict(Counter(r.classification.method for r in records if r.classification)),
        by_agent=dict(Counter(r.agent.audit_trail[0]["agent"] for r in records if r.agent and r.agent.audit_trail)),
        mean_extraction_confidence=round(sum(confs) / len(confs), 4) if confs else 0.0,
        llm_calls=len(calls), llm_cost_usd=round(sum(c.cost_usd for c in calls), 6),
        llm_mean_latency_ms=round(sum(c.latency_ms for c in calls) / len(calls), 3) if calls else 0.0,
        stage_mean_ms={s: round(sum(v) / len(v), 2) for s, v in stage_ms.items()},
        eval_mean_f1=eval_report.mean_f1 if eval_report else None,
        eval_passed=eval_report.passed if eval_report else None)


def run(records: list[PipelineRecord], ctx: PipelineContext, with_eval: bool = True) -> PipelineReport:
    return build_report(records, ctx, run_gold_eval(ctx) if with_eval else None)
