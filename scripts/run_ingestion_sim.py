#!/usr/bin/env python3
"""scripts/run_ingestion_sim.py — feed sample_data/ through ingestion, normalization and validation.

Runs fully offline: no S3, Textract or SQS. Fax samples carry pre-OCR line blocks,
which are turned into an OCRResult by the real TextractOCR block builder.

    python scripts/run_ingestion_sim.py                  # all sources
    python scripts/run_ingestion_sim.py --source hl7v2   # one source
    python scripts/run_ingestion_sim.py -v --out out.jsonl
"""
import argparse
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from contracts.schemas import SourceType  # noqa: E402
from ingestion.adapters import (  # noqa: E402
    EDI837Adapter,
    FHIRBundleAdapter,
    HL7V2Adapter,
    RawPayload,
    WebhookAdapter,
)
from ingestion.normalizer import Normalizer  # noqa: E402
from ingestion.textract_ocr import OCRResult, TextractOCR  # noqa: E402
from ingestion.validator import DocumentValidator  # noqa: E402

SAMPLE_DIR = Path(__file__).parent.parent / "sample_data"
SOURCES = ["fax", "hl7v2", "fhir_r4", "edi837", "webhook"]


def load_fax(path: Path) -> tuple[RawPayload, OCRResult]:
    s = json.loads(path.read_text())
    blocks = [{"BlockType": "LINE", "Text": b["text"], "Confidence": b["confidence"],
               "Page": b["page"]} for b in s["blocks"]]
    ocr = TextractOCR()._build(blocks, job_id=f"sim-{path.stem}")
    payload = RawPayload(source_type=SourceType.FAX_S3, raw_bytes=b"%PDF-1.4 simulated",
                         content_type=s["content_type"], source_id=s["s3_key"],
                         metadata={"bucket": "sim-bucket", "key": s["s3_key"]})
    return payload, ocr


def load_hl7(path: Path) -> tuple[RawPayload, None]:
    return HL7V2Adapter().from_bytes(path.read_bytes(), path.name), None


def load_fhir(path: Path) -> tuple[RawPayload, None]:
    return FHIRBundleAdapter().from_json(json.loads(path.read_text()), path.name), None


def load_edi(path: Path) -> tuple[RawPayload, None]:
    return EDI837Adapter().from_bytes(path.read_bytes(), path.name), None


def load_webhook(path: Path) -> tuple[RawPayload, None]:
    s = json.loads(path.read_text())
    return WebhookAdapter().from_request(s["body"].encode(), s["headers"], path.name), None


LOADERS = {"fax": load_fax, "hl7v2": load_hl7, "fhir_r4": load_fhir,
           "edi837": load_edi, "webhook": load_webhook}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--source", choices=SOURCES, action="append", help="limit to a source (repeatable)")
    ap.add_argument("--data-dir", type=Path, default=SAMPLE_DIR)
    ap.add_argument("--out", type=Path, help="write normalized documents + validation to JSONL")
    ap.add_argument("-v", "--verbose", action="store_true", help="print every error and warning")
    args = ap.parse_args()

    normalizer, validator = Normalizer(), DocumentValidator()
    totals: Counter = Counter()
    records = []

    print(f"{'file':<18}{'patient':<22}{'dob':<12}{'payer':<12}{'dx':>3}{'px':>3}  status")
    print("-" * 82)
    for source in args.source or SOURCES:
        files = sorted(p for p in (args.data_dir / source).glob("*") if p.is_file())
        if not files:
            print(f"[{source}] no samples in {args.data_dir / source} "
                  f"— run scripts/generate_sample_data.py")
            continue
        for path in files:
            try:
                payload, ocr = LOADERS[source](path)
                doc = normalizer.normalize(payload, ocr)
                res = validator.validate(doc)
            except Exception as exc:  # a parser crash is a finding, not a reason to stop
                totals[(source, "crashed")] += 1
                print(f"{path.name:<18}{'':<22}{'':<12}{'':<12}{'':>3}{'':>3}  CRASH {type(exc).__name__}: {exc}")
                records.append({"file": str(path), "source": source, "crash": repr(exc)})
                continue
            status = "ok" if res.is_valid else "DLQ"
            if res.warnings:
                status += f" ({len(res.warnings)} warn)"
            totals[(source, "valid" if res.is_valid else "dlq")] += 1
            totals[(source, "warn")] += bool(res.warnings)
            print(f"{path.name:<18}{doc.patient_name[:20]:<22}{doc.patient_dob[:10]:<12}"
                  f"{doc.payer_id[:10]:<12}{len(doc.diagnosis_codes):>3}{len(doc.procedure_codes):>3}  {status}")
            if args.verbose:
                for m in res.errors + res.warnings:
                    print(f"    - {m}")
            rec = {"file": str(path), "source": source, "valid": res.is_valid,
                   "errors": res.errors, "warnings": res.warnings,
                   "document": doc.model_dump(mode="json", exclude={"raw_metadata"})}
            if not res.is_valid:
                rec["error_envelope"] = validator.to_error_envelope(doc, res).model_dump(mode="json")
            records.append(rec)

    print("\nSummary")
    print(f"{'source':<10}{'valid':>7}{'dlq':>6}{'crash':>7}{'w/ warnings':>13}")
    for source in args.source or SOURCES:
        print(f"{source:<10}{totals[(source, 'valid')]:>7}{totals[(source, 'dlq')]:>6}"
              f"{totals[(source, 'crashed')]:>7}{totals[(source, 'warn')]:>13}")

    if args.out:
        args.out.write_text("\n".join(json.dumps(r, default=str) for r in records) + "\n")
        print(f"\nWrote {len(records)} records to {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
