"""classification/embeddings.py — TF-IDF + Logistic Regression classifier (Tier 2)."""
from __future__ import annotations
import logging, pickle
from pathlib import Path
from typing import Optional
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import LabelEncoder
from contracts.schemas import DocumentType

logger = logging.getLogger(__name__)


class EmbeddingClassifier:
    CONFIDENCE_FLOOR = 0.40

    def __init__(self) -> None:
        self._pipeline: Optional[Pipeline] = None
        self._le: Optional[LabelEncoder]   = None
        self._trained: bool = False

    def train(self, texts: list[str], labels: list[str]) -> None:
        self._le = LabelEncoder()
        y = self._le.fit_transform(labels)
        self._pipeline = Pipeline([
            ("tfidf", TfidfVectorizer(ngram_range=(1, 3), max_features=20_000,
                                      sublinear_tf=True, min_df=2)),
            ("clf",   LogisticRegression(C=2.0, max_iter=1000,
                                         class_weight="balanced", solver="lbfgs")),
        ])
        self._pipeline.fit(texts, y)
        self._trained = True
        logger.info("EmbeddingClassifier trained on %d samples", len(texts))

    def predict(self, text: str) -> tuple[DocumentType, float]:
        if not self._trained or self._pipeline is None or self._le is None:
            raise RuntimeError("EmbeddingClassifier not trained — call train() first")
        proba    = self._pipeline.predict_proba([text])[0]
        top_idx  = int(np.argmax(proba))
        top_conf = float(proba[top_idx])
        top_lbl  = self._le.inverse_transform([top_idx])[0]
        if top_conf < self.CONFIDENCE_FLOOR:
            return DocumentType.UNKNOWN, top_conf
        return DocumentType(top_lbl), round(top_conf, 4)

    def predict_top2(self, text: str) -> tuple[DocumentType, float, Optional[DocumentType], Optional[float]]:
        if not self._trained or self._pipeline is None or self._le is None:
            raise RuntimeError("Not trained")
        proba      = self._pipeline.predict_proba([text])[0]
        sorted_idx = np.argsort(proba)[::-1]
        top_lbl    = DocumentType(self._le.inverse_transform([int(sorted_idx[0])])[0])
        top_conf   = round(float(proba[sorted_idx[0]]), 4)
        ru_lbl: Optional[DocumentType] = None
        ru_conf: Optional[float] = None
        if len(sorted_idx) > 1:
            ru_lbl  = DocumentType(self._le.inverse_transform([int(sorted_idx[1])])[0])
            ru_conf = round(float(proba[sorted_idx[1]]), 4)
        if top_conf < self.CONFIDENCE_FLOOR:
            return DocumentType.UNKNOWN, top_conf, ru_lbl, ru_conf
        return top_lbl, top_conf, ru_lbl, ru_conf

    def save(self, path: str | Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "wb") as f:
            pickle.dump({"pipeline": self._pipeline, "le": self._le}, f)

    def load(self, path: str | Path) -> None:
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"Model not found: {path}")
        with open(path, "rb") as f:
            state = pickle.load(f)
        self._pipeline, self._le = state["pipeline"], state["le"]
        self._trained = True

    @property
    def is_trained(self) -> bool:
        return self._trained
