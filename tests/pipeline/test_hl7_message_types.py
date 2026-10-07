"""tests/pipeline/test_hl7_message_types.py — ADT/ORM/DFT coverage on the real generated samples.

scripts/generate_sample_data.py writes 50 HL7 v2 samples cycling three message types: ADT^A08
(registration — no RCM document type covers it), ORM^O01 (order → mapped to REFERRAL) and
DFT^P03 (charge post → mapped to CLAIM_837). These tests run the real files in sample_data/hl7v2
through ingestion and classification and check each message type lands where it should — so a
change to the generator or to classification._HL7_MESSAGES that breaks either mapping fails here,
not just on the hand-written single-message tests in test_stage_classification.py.
"""
from collections import Counter

import pytest

from contracts.pipeline import Disposition
from contracts.schemas import DocumentType
from pipeline import stage_classification, stage_ingestion
from pipeline.context import build_context


def message_type(path) -> str:
    first_line = path.read_text().splitlines()[0]
    return first_line.split("|")[8].split("^")[0]


@pytest.fixture(scope="module")
def by_message_type(ctx):
    """Group the 50 generated .hl7 files by their MSH-9 message type, independent of the pipeline,
    so the "generator actually produced all three types" check doesn't depend on classification."""
    files = sorted((ctx.data_dir / "hl7v2").glob("*.hl7"))
    return files, Counter(message_type(p) for p in files)


class TestGeneratedSampleCoverage:
    def test_fifty_hl7_samples_exist(self, by_message_type):
        files, _ = by_message_type
        assert len(files) == 50

    def test_all_three_message_types_are_present(self, by_message_type):
        _, counts = by_message_type
        assert set(counts) == {"ADT", "ORM", "DFT"}

    def test_message_types_are_roughly_evenly_split(self, by_message_type):
        _, counts = by_message_type
        assert all(15 <= n <= 17 for n in counts.values())


@pytest.fixture(scope="module")
def classified_by_type(ctx):
    """Run every real HL7 sample through ingestion + classification, grouped by message type."""
    records = stage_ingestion.run(build_context(ctx.data_dir, ["hl7v2"]))
    stage_classification.run(records, ctx)
    grouped: dict[str, list] = {}
    for rec, path in zip(records, sorted((ctx.data_dir / "hl7v2").glob("*.hl7")), strict=True):
        grouped.setdefault(message_type(path), []).append(rec)
    return grouped


class TestEndToEndMapping:
    """Checks the disposition each real sample ends up with, grouped by message type."""

    def test_every_sample_classified_or_closed_out(self, classified_by_type):
        all_recs = [r for recs in classified_by_type.values() for r in recs]
        assert len(all_recs) == 50
        assert all(r.classification is not None for r in all_recs)

    def test_orm_samples_are_referrals(self, classified_by_type):
        recs = classified_by_type["ORM"]
        assert recs and all(r.document.document_type == DocumentType.REFERRAL for r in recs)
        assert all(r.classification.method == "source_hint" for r in recs)
        assert all(r.in_flight for r in recs)

    def test_dft_samples_are_claims(self, classified_by_type):
        recs = classified_by_type["DFT"]
        assert recs and all(r.document.document_type == DocumentType.CLAIM_837 for r in recs)
        assert all(r.classification.method == "source_hint" for r in recs)
        assert all(r.in_flight for r in recs)

    def test_adt_samples_have_no_mapping_and_go_to_human_review(self, classified_by_type):
        recs = classified_by_type["ADT"]
        assert recs and all(r.document.document_type == DocumentType.UNKNOWN for r in recs)
        assert all(r.classification.method == "no_signal" for r in recs)
        assert all(r.disposition == Disposition.HUMAN_REVIEW for r in recs)

    def test_orm_and_dft_outnumber_the_old_all_adt_fixture(self, classified_by_type):
        """Guards against regenerating the fixture back down to one message type: before this
        change, all 25 HL7 samples were ADT and 0 exercised the ORM/DFT mappings end to end."""
        mapped = len(classified_by_type["ORM"]) + len(classified_by_type["DFT"])
        assert mapped >= 30
