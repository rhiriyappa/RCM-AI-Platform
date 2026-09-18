"""classification/llm_classifier.py — LLM fallback classifier (Tier 3)."""
from __future__ import annotations

import json
import logging
import re
from typing import Any

from contracts.schemas import DocumentType

logger = logging.getLogger(__name__)

_SYSTEM = """\
You are a healthcare RCM document classifier.
Classify into exactly one of:
  referral, prior_auth, denial_eob, claim_837, clinical_note, eligibility, unknown

Respond ONLY with valid JSON (no preamble):
{"type": "<type>", "confidence": <0.0-1.0>, "reasoning": "<one sentence>"}
"""


class LLMClassifier:
    EXCERPT_LENGTH = 800

    def __init__(self, call_llm: Any) -> None:
        self._call = call_llm

    def classify(self, text: str) -> tuple[DocumentType, float, str]:
        excerpt = text[:self.EXCERPT_LENGTH].strip()
        try:
            raw = self._call(system=_SYSTEM, user=f"DOCUMENT:\n{excerpt}")
            return self._parse(raw)
        except Exception as exc:
            logger.warning("LLMClassifier failed: %s", exc)
            return DocumentType.UNKNOWN, 0.0, f"error: {exc}"

    def _parse(self, raw: str) -> tuple[DocumentType, float, str]:
        cleaned = re.sub(r"```(?:json)?|```", "", raw).strip()
        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError:
            m = re.search(r"\{.*\}", cleaned, re.DOTALL)
            if not m:
                return DocumentType.UNKNOWN, 0.0, "parse_error"
            data = json.loads(m.group())
        raw_type   = data.get("type", "unknown").lower()
        confidence = min(1.0, max(0.0, float(data.get("confidence", 0.5))))
        reasoning  = str(data.get("reasoning", ""))
        try:
            doc_type = DocumentType(raw_type)
        except ValueError:
            doc_type = DocumentType.UNKNOWN
        return doc_type, confidence, reasoning
