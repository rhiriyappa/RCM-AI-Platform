"""tests/classification/test_ensemble.py"""
import pytest
from datetime import datetime, timezone
from contracts.schemas import DocumentType, RawDocument, SourceType
from classification.embeddings import EmbeddingClassifier
from classification.ensemble import EnsembleClassifier
from classification.llm_classifier import LLMClassifier
from classification.training_data import get_training_texts_and_labels


def make_doc(text: str) -> RawDocument:
    return RawDocument(document_id="t1", source_id="s1", source_type=SourceType.FHIR_R4,
                       ingested_at=datetime.now(timezone.utc), full_text=text)


@pytest.fixture(scope="module")
def emb():
    c = EmbeddingClassifier()
    texts, labels = get_training_texts_and_labels()
    c.train(texts, labels)
    return c


@pytest.fixture
def ensemble(emb): return EnsembleClassifier(embedding_classifier=emb)


class TestRulesTier:
    def test_denial_classified(self, ensemble):
        r = ensemble.classify(make_doc("Claim denied CO-4. EOB. RARC N56. Not covered. Denied."))
        assert r.document_type == DocumentType.DENIAL_EOB

    def test_has_routing_queue(self, ensemble):
        r = ensemble.classify(make_doc("Claim denied CO-4. EOB."))
        assert r.routing_queue != ""

    def test_denial_routes_correctly(self, ensemble):
        r = ensemble.classify(make_doc("Claim denied CO-4. EOB."))
        assert "denial" in r.routing_queue


class TestLLMFallback:
    def test_bad_llm_does_not_raise(self, emb):
        llm = LLMClassifier(call_llm=lambda system, user: "not json")
        clf = EnsembleClassifier(embedding_classifier=emb, llm_classifier=llm)
        r   = clf.classify(make_doc("something ambiguous here"))
        assert r.document_type in DocumentType


class TestResultContract:
    def test_required_fields(self, ensemble):
        r = ensemble.classify(make_doc("Claim denied CO-4 EOB."))
        assert r.document_id and 0.0 <= r.confidence <= 1.0 and r.method and r.routing_queue
