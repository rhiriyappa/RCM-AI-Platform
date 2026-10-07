"""tests/pipeline/conftest.py — shared context and helpers for the phased-pipeline tests."""
import json
from datetime import UTC, datetime

import pytest

from contracts.pipeline import PipelineRecord
from contracts.schemas import ClassificationResult, DocumentType, RawDocument, SourceType
from pipeline.context import DEFAULT_DATA_DIR, PipelineContext, build_context

if not (DEFAULT_DATA_DIR / "fax").exists():
    pytest.skip("sample_data/ missing — run scripts/generate_sample_data.py", allow_module_level=True)


@pytest.fixture(scope="session")
def ctx() -> PipelineContext:
    return build_context()


@pytest.fixture
def fresh_ctx(ctx) -> PipelineContext:
    """Same trained components, empty LLM-call ledger — for tests that count calls."""
    return PipelineContext(**{**ctx.__dict__, "llm_calls": []})


def make_doc(text: str, source_type: SourceType = SourceType.WEBHOOK, doc_type: DocumentType = DocumentType.UNKNOWN,
             **kw) -> RawDocument:
    return RawDocument(document_id="d1", source_id="s1", source_type=source_type, document_type=doc_type,
                       ingested_at=datetime.now(UTC), full_text=text, **kw)


def make_record(doc: RawDocument, doc_type: DocumentType | None = None) -> PipelineRecord:
    rec = PipelineRecord(record_id="t/1", source="webhook", file="t", document=doc)
    if doc_type:
        rec.document = doc.model_copy(update={"document_type": doc_type})
        rec.classification = ClassificationResult(document_id=doc.document_id, document_type=doc_type,
                                                  confidence=0.9, method="rules", routing_queue="q")
    return rec


def webhook_text(**over) -> str:
    body = {"event": "referral.created", "patient": {"name": "Jane Smith", "dob": "1978-04-12", "mrn": "MRN-1"},
            "payer": {"id": "BCBS-TX", "name": "BCBS"}, "diagnosis_codes": ["M54.5"], "procedure_codes": ["99213"],
            "provider_npi": "1234567890"}
    return json.dumps({**body, **over})
