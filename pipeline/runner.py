#!/usr/bin/env python3
"""pipeline/runner.py — run sample_data through the platform phase by phase.

    python -m pipeline.runner                          # all phases, all sources, deterministic LLM
    python -m pipeline.runner --llm slm                 # route simple extractions to a local Ollama SLM
    python -m pipeline.runner --until classification   # stop after a phase
    python -m pipeline.runner --source fax --source edi837
    python -m pipeline.runner --out-dir out/           # one JSONL per phase + report.json

Phases run as batches: every record finishes a phase before the next phase starts, and a
record that reaches a terminal disposition (DLQ, human review, ...) skips the later phases.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable
from pathlib import Path

from contracts.pipeline import PipelineRecord, PipelineReport
from pipeline import (
    stage_agents,
    stage_classification,
    stage_extraction,
    stage_ingestion,
    stage_observability,
    stage_orchestration,
)
from pipeline.context import BACKENDS, DEFAULT_DATA_DIR, SOURCES, PipelineContext, build_context

# (name, function). Ingestion builds the records; the rest transform them.
PHASES: list[tuple[str, Callable]] = [
    ("classification", stage_classification.run),
    ("extraction",     stage_extraction.run),
    ("orchestration",  stage_orchestration.run),
    ("agents",         stage_agents.run),
]
PHASE_NAMES = ["ingestion", *(n for n, _ in PHASES), "observability"]


def run_pipeline(ctx: PipelineContext, until: str = "observability",
                 on_phase: Callable[[str, list[PipelineRecord]], None] | None = None,
                 with_eval: bool = True) -> tuple[list[PipelineRecord], PipelineReport | None]:
    """Run phases in order up to and including `until`. The report exists only when observability ran."""
    stop = PHASE_NAMES.index(until)
    records = stage_ingestion.run(ctx)
    if on_phase:
        on_phase("ingestion", records)
    for name, fn in PHASES:
        if PHASE_NAMES.index(name) > stop:
            return records, None
        records = fn(records, ctx)
        if on_phase:
            on_phase(name, records)
    if stop < PHASE_NAMES.index("observability"):
        return records, None
    return records, stage_observability.run(records, ctx, with_eval=with_eval)


def _print_summary(records: list[PipelineRecord], report: PipelineReport | None) -> None:
    print(f"{'record':<28}{'type':<15}{'via':<12}{'conf':>6}  {'agent':<18}disposition")
    print("-" * 94)
    for r in records:
        typ = r.document.document_type.value if r.document else "-"
        via = r.classification.method if r.classification else "-"
        conf = f"{r.extraction.mean_confidence:.2f}" if r.extraction else "-"
        agent = r.agent.audit_trail[0]["agent"] if r.agent and r.agent.audit_trail else "-"
        print(f"{r.record_id:<28}{typ:<15}{via:<12}{conf:>6}  {agent:<18}"
              f"{r.disposition.value if r.disposition else 'in_flight'}")
    if report:
        print("\nReport")
        for k, v in report.model_dump().items():
            print(f"  {k:<28}{v}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    ap.add_argument("--source", action="append", choices=SOURCES, help="limit to a source (repeatable)")
    ap.add_argument("--until", choices=PHASE_NAMES, default="observability", help="last phase to run")
    ap.add_argument("--out-dir", type=Path, help="write one JSONL per phase, plus report.json")
    ap.add_argument("--no-eval", action="store_true", help="skip the gold-set extraction eval")
    ap.add_argument("--llm", choices=sorted(BACKENDS), default="deterministic",
                    help="call_llm backend: deterministic (default, no network) or slm (local Ollama, "
                         "RCM_SLM_MODEL env var picks the model, default llama3.2)")
    ap.add_argument("-q", "--quiet", action="store_true", help="print only the report")
    args = ap.parse_args(argv)

    ctx = build_context(args.data_dir, args.source, backend=args.llm)

    def dump(name: str, recs: list[PipelineRecord]) -> None:
        if args.out_dir:
            args.out_dir.mkdir(parents=True, exist_ok=True)
            n = PHASE_NAMES.index(name) + 1
            (args.out_dir / f"phase{n}_{name}.jsonl").write_text(
                "\n".join(r.model_dump_json() for r in recs) + "\n")

    records, report = run_pipeline(ctx, args.until, dump, with_eval=not args.no_eval)
    if not args.quiet:
        _print_summary(records, report)
    elif report:
        print(json.dumps(report.model_dump(), indent=2))
    if args.out_dir and report:
        (args.out_dir / "report.json").write_text(report.model_dump_json(indent=2) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
