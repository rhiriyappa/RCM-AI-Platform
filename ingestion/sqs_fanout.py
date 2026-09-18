"""ingestion/sqs_fanout.py — SQS FIFO fan-out to downstream queues."""
from __future__ import annotations
import json, logging
import boto3
from contracts.schemas import ErrorEnvelope, RawDocument

logger = logging.getLogger(__name__)


class SQSFanout:
    def __init__(self, classifier_queue_url: str, extraction_queue_url: str,
                 dlq_url: str, region: str = "us-east-1", endpoint_url: str | None = None):
        self._sqs = boto3.client("sqs", region_name=region, endpoint_url=endpoint_url)
        self._cq, self._eq, self._dlq = classifier_queue_url, extraction_queue_url, dlq_url

    def publish(self, doc: RawDocument) -> None:
        body = self._serialize(doc)
        attrs = {"document_type": {"DataType": "String", "StringValue": doc.document_type},
                 "source_type":   {"DataType": "String", "StringValue": doc.source_type}}
        for url in (self._cq, self._eq):
            self._sqs.send_message(QueueUrl=url, MessageBody=body, MessageAttributes=attrs,
                                   MessageGroupId=str(doc.source_type),
                                   MessageDeduplicationId=doc.document_id)
            logger.info("Published %s → %s", doc.document_id, url.split("/")[-1])

    def send_to_dlq(self, envelope: ErrorEnvelope) -> None:
        self._sqs.send_message(QueueUrl=self._dlq, MessageBody=json.dumps(envelope.model_dump()))
        logger.warning("DLQ: %s | %s", envelope.document_id, envelope.errors)

    @staticmethod
    def _serialize(doc: RawDocument) -> str:
        d = doc.model_dump(mode="json")
        return json.dumps(d)
