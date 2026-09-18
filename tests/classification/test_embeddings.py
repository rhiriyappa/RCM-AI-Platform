"""tests/classification/test_embeddings.py"""
import pytest
from contracts.schemas import DocumentType
from classification.embeddings import EmbeddingClassifier
from classification.training_data import get_training_texts_and_labels


@pytest.fixture(scope="module")
def clf():
    c = EmbeddingClassifier()
    texts, labels = get_training_texts_and_labels()
    c.train(texts, labels)
    return c


class TestTraining:
    def test_trained_after_fit(self):
        c = EmbeddingClassifier()
        assert not c.is_trained
        texts, labels = get_training_texts_and_labels()
        c.train(texts, labels)
        assert c.is_trained

    def test_raises_before_training(self):
        with pytest.raises(RuntimeError): EmbeddingClassifier().predict("text")


class TestPrediction:
    def test_denial_classified(self, clf):
        t, c = clf.predict("Claim denied CO-4. EOB. Remark N56.")
        assert t == DocumentType.DENIAL_EOB and c > 0.30

    def test_prior_auth_classified(self, clf):
        t, c = clf.predict("Prior authorization request for lumbar fusion. Medically necessary.")
        assert t == DocumentType.PRIOR_AUTH

    def test_predict_top2(self, clf):
        t, tc, rt, rc = clf.predict_top2("Claim denied. Prior auth needed.")
        assert t is not None and rt is not None and tc >= rc

    def test_confidence_range(self, clf):
        _, c = clf.predict("patient text here")
        assert 0.0 <= c <= 1.0

    def test_unknown_or_low_conf(self, clf):
        t, c = clf.predict("The quick brown fox. Hello world.")
        assert t == DocumentType.UNKNOWN or c < 0.70


class TestPersistence:
    def test_save_load(self, clf, tmp_path):
        p = tmp_path / "model.pkl"
        clf.save(p)
        l = EmbeddingClassifier()
        l.load(p)
        orig, _ = clf.predict("Claim denied CO-4.")
        loaded, _ = l.predict("Claim denied CO-4.")
        assert orig == loaded

    def test_load_missing_raises(self):
        with pytest.raises(FileNotFoundError): EmbeddingClassifier().load("/nope/model.pkl")
