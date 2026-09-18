"""extraction/engine.py — LLM extraction orchestrator."""
from __future__ import annotations
import logging, time
from datetime import datetime, timezone
from typing import Callable
from contracts.schemas import ClassificationResult, DocumentType, ExtractionResult, RawDocument
from extraction.prompts    import get_extraction_prompt, get_user_message
from extraction.parser     import parse_llm_output
from extraction.enrichment import ExtractionEnricher

logger = logging.getLogger(__name__)
HUMAN_REVIEW_THRESHOLD = 0.55


class ExtractionEngine:
    def __init__(self, call_llm: Callable[[str, str], str], enricher: ExtractionEnricher) -> None:
        self._call_llm = call_llm; self._enricher = enricher

    def extract(self, doc: RawDocument, classification: ClassificationResult) -> ExtractionResult:
        t0 = time.perf_counter()
        try:
            raw = self._call_llm(get_extraction_prompt(classification.document_type),
                                  get_user_message(doc.full_text))
        except Exception as exc:
            logger.error("[%s] LLM call failed: %s", doc.document_id, exc)
            return self._empty(doc.document_id, classification.document_type, str(exc))
        result = parse_llm_output(raw, doc.document_id, classification.document_type)
        result = self._enricher.enrich(result)
        logger.info("[%s] extracted in %.0fms — conf=%.2f low=%s",
                    doc.document_id, (time.perf_counter()-t0)*1000,
                    result.mean_confidence, result.low_conf_fields or "none")
        return result

    def needs_human_review(self, result: ExtractionResult) -> bool:
        return result.mean_confidence < HUMAN_REVIEW_THRESHOLD

    @staticmethod
    def _empty(document_id: str, document_type: DocumentType, error: str) -> ExtractionResult:
        return ExtractionResult(document_id=document_id, document_type=document_type,
                                extracted_at=datetime.now(timezone.utc),
                                mean_confidence=0.0, extraction_warnings=[f"extraction_error: {error}"])
