"""tests/ingestion/test_sqs_fanout.py — SQS fan-out integration test (requires LocalStack)."""
from __future__ import annotations

import json
import os
from datetime import UTC, datetime

import boto3
import pytest

from contracts.schemas import DocumentType, ErrorEnvelope, RawDocument, SourceType
from ingestion.sqs_fanout import SQSFanout

ENDPOINT = os.environ.get("AWS_ENDPOINT_URL", "http://localhost:4566")
REGION = os.environ.get("AWS_DEFAULT_REGION", "us-east-1")


def _queue_url(sqs, name: str) -> str:
    return sqs.get_queue_url(QueueName=name)["QueueUrl"]


@pytest.fixture(scope="module")
def sqs_client():
    return boto3.client("sqs", region_name=REGION, endpoint_url=ENDPOINT)


@pytest.fixture(scope="module")
def fanout(sqs_client):
    return SQSFanout(
        classifier_queue_url=_queue_url(sqs_client, "onecall-classify.fifo"),
        extraction_queue_url=_queue_url(sqs_client, "onecall-extract.fifo"),
        dlq_url=_queue_url(sqs_client, "onecall-dlq"),
        region=REGION, endpoint_url=ENDPOINT,
    )


@pytest.mark.integration
class TestSQSFanout:
    def test_publish_fans_out_to_classifier_and_extraction_queues(self, sqs_client, fanout):
        doc = RawDocument(
            document_id="itest-doc-1", source_id="itest-src-1",
            source_type=SourceType.WEBHOOK, document_type=DocumentType.REFERRAL,
            ingested_at=datetime.now(UTC), full_text="integration test document",
        )
        fanout.publish(doc)

        for queue_name in ("onecall-classify.fifo", "onecall-extract.fifo"):
            url = _queue_url(sqs_client, queue_name)
            resp = sqs_client.receive_message(QueueUrl=url, MaxNumberOfMessages=1, WaitTimeSeconds=5)
            messages = resp.get("Messages", [])
            assert messages, f"expected a message on {queue_name}"
            body = json.loads(messages[0]["Body"])
            assert body["document_id"] == "itest-doc-1"
            sqs_client.delete_message(QueueUrl=url, ReceiptHandle=messages[0]["ReceiptHandle"])

    def test_send_to_dlq(self, sqs_client, fanout):
        envelope = ErrorEnvelope(
            document_id="itest-doc-2", source_id="itest-src-2",
            errors=["missing patient_id"], warnings=[], raw_snapshot={},
        )
        fanout.send_to_dlq(envelope)

        url = _queue_url(sqs_client, "onecall-dlq")
        resp = sqs_client.receive_message(QueueUrl=url, MaxNumberOfMessages=1, WaitTimeSeconds=5)
        messages = resp.get("Messages", [])
        assert messages, "expected a message on the DLQ"
        body = json.loads(messages[0]["Body"])
        assert body["document_id"] == "itest-doc-2"
        sqs_client.delete_message(QueueUrl=url, ReceiptHandle=messages[0]["ReceiptHandle"])
