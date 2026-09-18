"""ingestion/api.py — FastAPI ingestor service."""
from __future__ import annotations
import os, uuid
import structlog
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from ingestion.adapters import EDI837Adapter, FHIRBundleAdapter, WebhookAdapter
from ingestion.normalizer import Normalizer
from ingestion.sqs_fanout import SQSFanout
from ingestion.validator import DocumentValidator

log = structlog.get_logger()
app = FastAPI(title="One Call Ingestor", version="1.0.0")
_normalizer = Normalizer()
_validator  = DocumentValidator()


def _fanout() -> SQSFanout:
    return SQSFanout(classifier_queue_url=os.environ["SQS_CLASSIFIER_URL"],
                     extraction_queue_url=os.environ["SQS_EXTRACTION_URL"],
                     dlq_url=os.environ["SQS_DLQ_URL"],
                     endpoint_url=os.environ.get("AWS_ENDPOINT_URL"))


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "service": "ingestor", "version": "1.0.0"}


@app.post("/ingest/fhir")
async def ingest_fhir(request: Request) -> JSONResponse:
    body = await request.json()
    payload = FHIRBundleAdapter().from_json(body, source_id=str(uuid.uuid4()))
    doc = _normalizer.normalize(payload)
    result = _validator.validate(doc)
    fanout = _fanout()
    if result.is_valid:
        fanout.publish(doc)
        return JSONResponse({"document_id": doc.document_id, "status": "queued"})
    envelope = _validator.to_error_envelope(doc, result)
    fanout.send_to_dlq(envelope)
    return JSONResponse({"document_id": doc.document_id, "status": "dlq", "errors": result.errors}, status_code=422)


@app.post("/ingest/edi837")
async def ingest_edi(request: Request) -> JSONResponse:
    body = await request.body()
    payload = EDI837Adapter().from_bytes(body, source_id=str(uuid.uuid4()))
    doc = _normalizer.normalize(payload)
    result = _validator.validate(doc)
    fanout = _fanout()
    if result.is_valid:
        fanout.publish(doc)
        return JSONResponse({"document_id": doc.document_id, "status": "queued"})
    envelope = _validator.to_error_envelope(doc, result)
    fanout.send_to_dlq(envelope)
    return JSONResponse({"document_id": doc.document_id, "status": "dlq", "errors": result.errors}, status_code=422)


@app.post("/ingest/webhook")
async def ingest_webhook(request: Request) -> JSONResponse:
    body = await request.body()
    headers = dict(request.headers)
    source_id = headers.get("x-source-id", str(uuid.uuid4()))
    payload = WebhookAdapter().from_request(body, headers, source_id=source_id)
    doc = _normalizer.normalize(payload)
    result = _validator.validate(doc)
    fanout = _fanout()
    if result.is_valid:
        fanout.publish(doc)
        return JSONResponse({"document_id": doc.document_id, "status": "queued"})
    envelope = _validator.to_error_envelope(doc, result)
    fanout.send_to_dlq(envelope)
    return JSONResponse({"document_id": doc.document_id, "status": "dlq", "errors": result.errors}, status_code=422)
