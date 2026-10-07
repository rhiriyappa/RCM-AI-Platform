"""tests/pipeline/test_contracts.py"""
from contracts.pipeline import Disposition, PipelineRecord


def test_new_record_is_in_flight():
    assert PipelineRecord(record_id="a", source="fax", file="f").in_flight


def test_record_with_disposition_is_not_in_flight():
    assert not PipelineRecord(record_id="a", source="fax", file="f", disposition=Disposition.DLQ).in_flight


def test_record_round_trips_through_json():
    rec = PipelineRecord(record_id="a", source="fax", file="f", disposition=Disposition.HITL,
                         stage_ms={"ingestion": 1.5})
    assert PipelineRecord.model_validate_json(rec.model_dump_json()) == rec
