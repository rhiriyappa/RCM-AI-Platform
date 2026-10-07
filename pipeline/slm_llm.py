"""pipeline/slm_llm.py — SLM-backed extraction via a local Ollama server.

Point of this module: route the "less complex reasoning" calls (short documents, simple field
extraction) to a small model running on-box — Mistral 7B or Llama 3.2 through Ollama — instead of
paying for a hosted frontier model on every document. See orchestration/model_router.py for where
that split happens; this module is just the call_llm implementation the SLM-routed calls use.

Falls back to the deterministic parser in pipeline.offline_llm whenever Ollama is unreachable, the
model isn't pulled, the call times out, or the response isn't usable JSON — so the pipeline (and the
test suite) still runs correctly with no local model installed. That fallback is what keeps this
"offline" in the same sense as pipeline.offline_llm: no step here requires a live service to succeed.
"""
from __future__ import annotations

import json
import logging
import os
import re

import httpx

from pipeline.offline_llm import offline_llm

logger = logging.getLogger(__name__)

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
SLM_MODEL  = os.environ.get("RCM_SLM_MODEL", "llama3.2")
# A 3B–7B model on CPU can take several seconds for a full extraction prompt — timed against
# llama3.2 locally, ~7-10s. NUM_PREDICT caps the response so it can't run past that budget.
TIMEOUT_S    = float(os.environ.get("RCM_SLM_TIMEOUT", "20"))
NUM_PREDICT  = int(os.environ.get("RCM_SLM_NUM_PREDICT", "500"))

# Mirrors the shape extraction/parser.py expects: {"field": {"value": ..., "confidence": 0.0-1.0}}.
_SCHEMA_HINT = (
    "\n\nRespond with ONLY a JSON object, no prose and no markdown fences. "
    'Each field you can find must be {"value": <value>, "confidence": <0.0-1.0>}. '
    "Omit any field you cannot find in the document — do not invent values."
)
_FENCE_RE = re.compile(r"```(?:json)?|```")


def slm_llm(system: str, user: str) -> str:
    """call_llm-shaped function (system, user) -> raw response text.

    Tries the local Ollama server first; on any connectivity, timeout, or malformed-response
    error it logs a warning and hands the same (system, user) pair to the deterministic fallback.
    """
    try:
        content = _call_ollama(system, user)
        json.loads(_FENCE_RE.sub("", content).strip())  # fail fast if it isn't parseable JSON
        return content
    except (httpx.HTTPError, KeyError, ValueError) as exc:
        logger.warning("SLM call to %s@%s failed (%s) — falling back to deterministic extraction",
                       SLM_MODEL, OLLAMA_URL, exc)
        return offline_llm(system, user)


def _call_ollama(system: str, user: str) -> str:
    resp = httpx.post(
        f"{OLLAMA_URL}/api/chat",
        json={
            "model": SLM_MODEL,
            "messages": [{"role": "system", "content": system + _SCHEMA_HINT},
                        {"role": "user", "content": user}],
            "stream": False,
            "options": {"temperature": 0.0, "num_predict": NUM_PREDICT},
        },
        timeout=TIMEOUT_S,
    )
    resp.raise_for_status()
    return resp.json()["message"]["content"]


def is_available(model: str = SLM_MODEL, url: str = OLLAMA_URL) -> bool:
    """Best-effort reachability check: is Ollama up, and is `model` pulled?

    Used by the CLI and by live/integration tests to skip gracefully rather than hang.
    """
    try:
        tags = httpx.get(f"{url}/api/tags", timeout=2.0).json().get("models", [])
    except httpx.HTTPError:
        return False
    wanted = model.split(":")[0]
    return any(m.get("model", "").split(":")[0] == wanted for m in tags)
