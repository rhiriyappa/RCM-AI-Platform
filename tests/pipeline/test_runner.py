"""tests/pipeline/test_runner.py — end-to-end over sample_data/."""
import json
from collections import Counter

import pytest

from contracts.pipeline import Disposition
from pipeline.context import build_context
from pipeline.runner import PHASE_NAMES, main, run_pipeline


@pytest.fixture(scope="module")
def full_run():
    return run_pipeline(build_context(), with_eval=True)


def test_every_record_reaches_a_terminal_disposition(full_run):
    records, _ = full_run
    assert len(records) == 150 and all(not r.in_flight for r in records)


def test_report_counts_reconcile(full_run):
    records, report = full_run
    assert report.total_records == sum(report.by_disposition.values()) == 150
    assert report.llm_calls == sum(1 for r in records if r.extraction)


def test_known_dispositions_on_the_shipped_samples(full_run):
    records, report = full_run
    assert report.by_disposition["dlq"] == 3
    assert report.by_disposition["completed"] > 0 and report.by_disposition["routed_no_agent"] > 0


def test_records_that_fell_out_skipped_later_phases(full_run):
    records, _ = full_run
    for r in records:
        if r.disposition == Disposition.DLQ:
            assert r.stages_completed == ["ingestion"]
        if r.disposition == Disposition.HUMAN_REVIEW and r.extraction is None:
            assert "extraction" not in r.stages_completed


def test_completed_records_ran_every_phase(full_run):
    records, _ = full_run
    done = next(r for r in records if r.disposition == Disposition.COMPLETED)
    assert done.stages_completed == ["ingestion", "classification", "extraction", "orchestration", "agents"]


def test_gold_eval_is_in_the_report(full_run):
    assert full_run[1].eval_passed is True


@pytest.mark.parametrize("until", ["ingestion", "classification", "extraction", "orchestration"])
def test_until_stops_after_the_phase(until):
    records, report = run_pipeline(build_context(sources=["webhook"]), until=until)
    assert report is None
    assert all(until in r.stages_completed for r in records if r.disposition is None or until == "ingestion")
    later = PHASE_NAMES[PHASE_NAMES.index(until) + 1:]
    assert not any(s in r.stages_completed for r in records for s in later)


def test_source_filter():
    records, _ = run_pipeline(build_context(sources=["edi837"]), until="classification")
    assert Counter(r.source for r in records) == {"edi837": 25}


def test_cli_writes_a_jsonl_per_phase_and_a_report(tmp_path, capsys):
    assert main(["--source", "webhook", "--out-dir", str(tmp_path), "-q"]) == 0
    files = sorted(p.name for p in tmp_path.iterdir())
    assert files == ["phase1_ingestion.jsonl", "phase2_classification.jsonl", "phase3_extraction.jsonl",
                     "phase4_orchestration.jsonl", "phase5_agents.jsonl", "report.json"]
    assert json.loads((tmp_path / "report.json").read_text())["total_records"] == 25
    assert len((tmp_path / "phase1_ingestion.jsonl").read_text().splitlines()) == 25


def test_cli_prints_a_table_by_default(capsys):
    main(["--source", "edi837", "--until", "classification"])
    out = capsys.readouterr().out
    assert "edi837_001.edi" in out and "claim_837" in out and "Report" not in out
