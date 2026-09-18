"""classification/ensemble.py — three-tier ensemble classifier."""
from __future__ import annotations

import logging
import time

from classification.embeddings import EmbeddingClassifier
from classification.llm_classifier import LLMClassifier
from classification.routing import resolve_routing_queue
from classification.rules import apply_rules
from contracts.schemas import ClassificationResult, DocumentType, RawDocument

logger = logging.getLogger(__name__)
RULES_THRESHOLD     = 0.88
EMBEDDING_THRESHOLD = 0.72


class EnsembleClassifier:
    def __init__(self, embedding_classifier: EmbeddingClassifier,
                 llm_classifier: LLMClassifier | None = None) -> None:
        self._embedding = embedding_classifier
        self._llm       = llm_classifier

    def classify(self, doc: RawDocument) -> ClassificationResult:
        t0 = time.perf_counter()
        text = doc.full_text

        signals = apply_rules(text)
        if signals and signals[0].confidence >= RULES_THRESHOLD:
            top = signals[0]
            return self._result(doc.document_id, top.document_type, top.confidence,
                                runner_up=signals[1] if len(signals) > 1 else None,
                                method="rules", elapsed=time.perf_counter() - t0)

        if self._embedding.is_trained:
            emb_type, emb_conf, ru_type, ru_conf = self._embedding.predict_top2(text)
            rules_top = signals[0].document_type if signals else None
            agrees = (rules_top == emb_type) or (rules_top is None)
            if emb_conf >= EMBEDDING_THRESHOLD and emb_type != DocumentType.UNKNOWN and agrees:
                return self._result(doc.document_id, emb_type, emb_conf,
                                    runner_up_type=ru_type, runner_up_conf=ru_conf,
                                    method="embedding", elapsed=time.perf_counter() - t0)

        if self._llm is not None:
            llm_type, llm_conf, reasoning = self._llm.classify(text)
            logger.info("[%s] LLM tier: %s @ %.2f — %s", doc.document_id, llm_type, llm_conf, reasoning)
            return self._result(doc.document_id, llm_type, llm_conf,
                                method="llm", elapsed=time.perf_counter() - t0)

        if signals:
            top = signals[0]
            return self._result(doc.document_id, top.document_type, top.confidence,
                                method="rules_only", elapsed=time.perf_counter() - t0)

        return self._result(doc.document_id, DocumentType.UNKNOWN, 0.0,
                            method="no_signal", elapsed=time.perf_counter() - t0)

    def _result(self, document_id: str, document_type: DocumentType, confidence: float,
                runner_up=None, runner_up_type=None, runner_up_conf=None,
                method: str = "ensemble", elapsed: float = 0.0) -> ClassificationResult:
        logger.info("[%s] → %s (%.2f) via %s in %.0fms",
                    document_id, document_type, confidence, method, elapsed * 1000)
        ru_type = runner_up_type or (runner_up.document_type if runner_up else None)
        ru_conf = runner_up_conf or (runner_up.confidence if runner_up else None)
        return ClassificationResult(document_id=document_id, document_type=document_type,
                                    confidence=round(confidence, 4), runner_up_type=ru_type,
                                    runner_up_conf=ru_conf, method=method,
                                    routing_queue=resolve_routing_queue(document_type))
