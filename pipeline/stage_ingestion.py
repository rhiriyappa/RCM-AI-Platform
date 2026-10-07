"""pipeline/stage_ingestion.py — Phase 1: sample files → RawDocument, validated, DLQ on failure."""
from __future__ import annotations

import json
import time
from collections.abc import Callable
from pathlib import Path

from contracts.pipeline import Disposition, PipelineRecord
from contracts.schemas import SourceType
from ingestion.adapters import (
    EDI837Adapter,
    FHIRBundleAdapter,
    HL7V2Adapter,
    RawPayload,
    WebhookAdapter,
)
from ingestion.textract_ocr import OCRResult, TextractOCR
from pipeline.context import PipelineContext

STAGE = "ingestion"
Loaded = tuple[RawPayload, OCRResult | None]


def _fax(path: Path) -> Loaded:
    """Fax samples hold pre-OCR line blocks; build the OCRResult with the real Textract block builder."""
    s = json.loads(path.read_text())
    blocks = [{"BlockType": "LINE", "Text": b["text"], "Confidence": b["confidence"], "Page": b["page"]}
              for b in s["blocks"]]
    ocr = TextractOCR()._build(blocks, job_id=f"sim-{path.stem}")
    return RawPayload(source_type=SourceType.FAX_S3, raw_bytes=b"%PDF-1.4 simulated",
                      content_type=s["content_type"], source_id=s["s3_key"],
                      metadata={"bucket": "sim-bucket", "key": s["s3_key"]}), ocr


def _webhook(path: Path) -> Loaded:
    s = json.loads(path.read_text())
    return WebhookAdapter().from_request(s["body"].encode(), s["headers"], path.name), None


LOADERS: dict[str, Callable[[Path], Loaded]] = {
    "fax":     _fax,
    "hl7v2":   lambda p: (HL7V2Adapter().from_bytes(p.read_bytes(), p.name), None),
    "fhir_r4": lambda p: (FHIRBundleAdapter().from_json(json.loads(p.read_text()), p.name), None),
    "edi837":  lambda p: (EDI837Adapter().from_bytes(p.read_bytes(), p.name), None),
    "webhook": _webhook,
}


def run(ctx: PipelineContext) -> list[PipelineRecord]:
    """Create one PipelineRecord per sample file. Invalid documents are closed out as DLQ here."""
    records: list[PipelineRecord] = []
    for source in ctx.sources:
        for path in sorted(p for p in (ctx.data_dir / source).glob("*") if p.is_file()):
            rec = PipelineRecord(record_id=f"{source}/{path.name}", source=source, file=str(path))
            t0 = time.perf_counter()
            try:
                payload, ocr = LOADERS[source](path)
                doc = ctx.normalizer.normalize(payload, ocr)
                result = ctx.validator.validate(doc)
                rec.document = doc
                rec.validation_errors, rec.validation_warnings = result.errors, result.warnings
                if not result.is_valid:
                    rec.disposition = Disposition.DLQ
            except Exception as exc:  # a bad sample must not stop the batch
                rec.errors.append(f"ingestion: {type(exc).__name__}: {exc}")
                rec.disposition = Disposition.FAILED
            rec.stage_ms[STAGE] = round((time.perf_counter() - t0) * 1000, 2)
            rec.stages_completed.append(STAGE)
            records.append(rec)
    return records
