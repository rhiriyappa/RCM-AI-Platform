"""tests/pipeline/test_stage_ingestion.py"""
from collections import Counter

import pytest

from contracts.pipeline import Disposition
from contracts.schemas import SourceType
from pipeline import stage_ingestion
from pipeline.context import SOURCES, build_context


@pytest.fixture(scope="module")
def records(ctx):
    return stage_ingestion.run(ctx)


def test_one_record_per_sample_file(records):
    # hl7v2 ships 50 samples (ADT/ORM/DFT, see test_hl7_message_types.py); every other source has 25.
    assert Counter(r.source for r in records) == {
        "fax": 25, "hl7v2": 50, "fhir_r4": 25, "edi837": 25, "webhook": 25}
    assert set(Counter(r.source for r in records)) == set(SOURCES)


def test_source_types_match_directory(records):
    expected = {"fax": SourceType.FAX_S3, "hl7v2": SourceType.HL7_V2, "fhir_r4": SourceType.FHIR_R4,
                "edi837": SourceType.EDI_837, "webhook": SourceType.WEBHOOK}
    assert all(r.document.source_type == expected[r.source] for r in records)


def test_known_bad_samples_go_to_dlq(records):
    dlq = {r.record_id for r in records if r.disposition == Disposition.DLQ}
    assert dlq == {"fax/fax_007.json", "fax/fax_021.json", "webhook/webhook_008.json"}


def test_dlq_records_carry_reasons(records):
    assert all(r.validation_errors for r in records if r.disposition == Disposition.DLQ)


def test_fax_ocr_confidence_is_recorded(records):
    fax = [r for r in records if r.source == "fax" and r.disposition is None]
    assert all(r.document.ocr_mean_confidence and r.document.page_count == 2 for r in fax)


def test_structured_fields_are_parsed(records):
    fhir = next(r for r in records if r.record_id == "fhir_r4/fhir_001.json")
    assert fhir.document.patient_name and fhir.document.diagnosis_codes


def test_stage_timing_recorded(records):
    assert all("ingestion" in r.stage_ms and r.stages_completed == ["ingestion"] for r in records)


def test_empty_data_dir_yields_no_records(tmp_path):
    assert stage_ingestion.run(build_context(tmp_path, ["fax"])) == []


def test_unreadable_sample_is_failed_not_fatal(tmp_path):
    (tmp_path / "fhir_r4").mkdir()
    (tmp_path / "fhir_r4" / "bad.json").write_text("{not json")
    recs = stage_ingestion.run(build_context(tmp_path, ["fhir_r4"]))
    assert recs[0].disposition == Disposition.FAILED and recs[0].errors
