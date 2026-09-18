"""ingestion/textract_ocr.py — async Textract OCR with confidence filtering."""
from __future__ import annotations
import logging, time
from dataclasses import dataclass, field
import boto3

logger = logging.getLogger(__name__)


@dataclass
class OCRResult:
    full_text: str
    page_texts: list[str]
    mean_confidence: float
    low_conf_blocks: list[dict] = field(default_factory=list)
    raw_blocks: list[dict]      = field(default_factory=list)
    job_id: str = ""


class TextractOCR:
    CONFIDENCE_THRESHOLD = 85.0
    POLL_INTERVAL_S      = 2
    MAX_POLLS            = 150

    def __init__(self, region: str = "us-east-1", endpoint_url: str | None = None):
        self._textract = boto3.client("textract", region_name=region, endpoint_url=endpoint_url)

    def extract_async(self, bucket: str, key: str) -> OCRResult:
        resp = self._textract.start_document_text_detection(
            DocumentLocation={"S3Object": {"Bucket": bucket, "Name": key}})
        job_id = resp["JobId"]
        logger.info("Textract job started: %s", job_id)
        blocks = self._poll(job_id)
        return self._build(blocks, job_id)

    def _poll(self, job_id: str) -> list[dict]:
        for _ in range(self.MAX_POLLS):
            resp = self._textract.get_document_text_detection(JobId=job_id)
            status = resp["JobStatus"]
            if status == "SUCCEEDED":
                blocks = resp["Blocks"]
                while token := resp.get("NextToken"):
                    resp = self._textract.get_document_text_detection(JobId=job_id, NextToken=token)
                    blocks.extend(resp["Blocks"])
                return blocks
            if status == "FAILED":
                raise RuntimeError(f"Textract job {job_id} failed")
            time.sleep(self.POLL_INTERVAL_S)
        raise TimeoutError(f"Textract job {job_id} timed out")

    def _build(self, blocks: list[dict], job_id: str) -> OCRResult:
        lines_by_page: dict[int, list[str]] = {}
        low_conf, confs = [], []
        for b in blocks:
            if b["BlockType"] != "LINE":
                continue
            conf = b.get("Confidence", 0.0)
            page = b.get("Page", 1)
            confs.append(conf)
            lines_by_page.setdefault(page, []).append(b["Text"])
            if conf < self.CONFIDENCE_THRESHOLD:
                low_conf.append({"text": b["Text"], "conf": conf, "page": page})
        page_texts = ["\n".join(lines_by_page.get(p, [])) for p in sorted(lines_by_page)]
        mean = round(sum(confs) / len(confs), 2) if confs else 0.0
        return OCRResult(full_text="\n\n".join(page_texts), page_texts=page_texts,
                         mean_confidence=mean, low_conf_blocks=low_conf,
                         raw_blocks=blocks, job_id=job_id)
