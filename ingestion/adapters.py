"""ingestion/adapters.py — unified source adapters."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

import boto3

from contracts.schemas import SourceType


@dataclass
class RawPayload:
    source_type:  SourceType
    raw_bytes:    bytes
    content_type: str
    source_id:    str
    metadata:     dict[str, Any] = field(default_factory=dict)


class S3FaxAdapter:
    def __init__(self, bucket: str, region: str = "us-east-1", endpoint_url: str | None = None):
        self._s3 = boto3.client("s3", region_name=region, endpoint_url=endpoint_url)
        self._bucket = bucket

    def fetch(self, s3_key: str) -> RawPayload:
        obj = self._s3.get_object(Bucket=self._bucket, Key=s3_key)
        raw = obj["Body"].read()
        return RawPayload(source_type=SourceType.FAX_S3, raw_bytes=raw,
                          content_type=obj["ContentType"], source_id=s3_key,
                          metadata={"bucket": self._bucket, "key": s3_key, "size_bytes": len(raw)})


class HL7V2Adapter:
    def from_bytes(self, raw: bytes, source_id: str) -> RawPayload:
        return RawPayload(source_type=SourceType.HL7_V2, raw_bytes=raw,
                          content_type="application/hl7-v2", source_id=source_id)


class FHIRBundleAdapter:
    def from_json(self, body: dict[str, Any], source_id: str) -> RawPayload:
        raw = json.dumps(body).encode()
        return RawPayload(source_type=SourceType.FHIR_R4, raw_bytes=raw,
                          content_type="application/fhir+json", source_id=source_id,
                          metadata={"resource_type": body.get("resourceType")})


class EDI837Adapter:
    def from_bytes(self, raw: bytes, source_id: str) -> RawPayload:
        return RawPayload(source_type=SourceType.EDI_837, raw_bytes=raw,
                          content_type="application/x12", source_id=source_id)


class WebhookAdapter:
    def from_request(self, body: bytes, headers: dict[str, str], source_id: str) -> RawPayload:
        ct = headers.get("content-type", "application/octet-stream")
        return RawPayload(source_type=SourceType.WEBHOOK, raw_bytes=body,
                          content_type=ct, source_id=source_id,
                          metadata={"headers": dict(headers)})
