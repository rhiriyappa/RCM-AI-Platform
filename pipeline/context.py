"""pipeline/context.py — shared services every stage draws on, built once per run."""
from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from classification.embeddings import EmbeddingClassifier
from classification.ensemble import EnsembleClassifier
from classification.training_data import get_training_texts_and_labels
from contracts.schemas import DocumentType, ModelCallRecord, PromptTemplate
from extraction.engine import ExtractionEngine
from extraction.enrichment import CodeValidator, ExtractionEnricher, MockNPILookup
from extraction.prompts import VERSION, get_extraction_prompt
from ingestion.normalizer import Normalizer
from ingestion.validator import DocumentValidator
from orchestration.prompt_registry import PromptRegistry
from pipeline.offline_llm import offline_llm
from pipeline.slm_llm import slm_llm

DEFAULT_DATA_DIR = Path(__file__).parent.parent / "sample_data"
SOURCES = ["fax", "hl7v2", "fhir_r4", "edi837", "webhook"]

# "deterministic" (default) is the regex/rule extractor from pipeline.offline_llm — no external
# service, fully reproducible, what CI runs. "slm" calls a local Ollama model (Mistral 7B, Llama)
# for the simpler extractions and falls back to "deterministic" automatically if that's unreachable.
# Select with build_context(backend=...) or the RCM_CALL_LLM env var; the CLI exposes it as --llm.
BACKENDS: dict[str, Callable[[str, str], str]] = {"deterministic": offline_llm, "slm": slm_llm}


@dataclass
class PipelineContext:
    data_dir:   Path
    sources:    list[str]
    call_llm:   Callable[[str, str], str]
    normalizer: Normalizer
    validator:  DocumentValidator
    classifier: EnsembleClassifier
    engine:     ExtractionEngine
    registry:   PromptRegistry
    use_slm:    bool = False   # tells stage_extraction to route short/simple calls to the local SLM tier
    llm_calls:  list[ModelCallRecord] = field(default_factory=list)


def build_context(data_dir: Path = DEFAULT_DATA_DIR, sources: list[str] | None = None,
                  call_llm: Callable[[str, str], str] | None = None,
                  backend: str | None = None) -> PipelineContext:
    """Train the tier-2 classifier on the seed corpus and wire up every phase's components.

    backend picks the call_llm implementation ("deterministic" or "slm", see BACKENDS above),
    read from RCM_CALL_LLM if not passed explicitly. Pass call_llm directly to use something else
    entirely (a real Claude/GPT client, a test double) — it then takes precedence over backend.
    """
    backend = (backend or os.environ.get("RCM_CALL_LLM", "deterministic")).lower()
    if call_llm is None:
        call_llm = BACKENDS.get(backend, offline_llm)

    embedding = EmbeddingClassifier()
    texts, labels = get_training_texts_and_labels()
    embedding.train(texts, labels)

    registry = PromptRegistry()
    for dt in DocumentType:
        registry.register(PromptTemplate(
            name=f"extraction-{dt.value}", version=VERSION, document_type=dt,
            system=get_extraction_prompt(dt), user_template="DOCUMENT:\n{text}"))

    return PipelineContext(
        data_dir=Path(data_dir), sources=sources or SOURCES, call_llm=call_llm,
        normalizer=Normalizer(), validator=DocumentValidator(),
        classifier=EnsembleClassifier(embedding, llm_classifier=None),
        engine=ExtractionEngine(call_llm, ExtractionEnricher(MockNPILookup(), CodeValidator())),
        registry=registry, use_slm=(backend == "slm"))
