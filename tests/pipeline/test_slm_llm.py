"""tests/pipeline/test_slm_llm.py — unit tests mock Ollama so the suite stays offline and fast;
one test at the bottom is marked integration and actually talks to a local Ollama server.
"""
import json

import httpx
import pytest

import pipeline.slm_llm as slm


def _chat_response(content: str) -> httpx.Response:
    return httpx.Response(200, json={"message": {"content": content}},
                          request=httpx.Request("POST", "http://x/api/chat"))


class TestSlmLlmMocked:
    def test_uses_the_model_response_when_it_is_valid_json(self, monkeypatch):
        good = json.dumps({"patient_name": {"value": "Jane Smith", "confidence": 0.9}})
        monkeypatch.setattr(httpx, "post", lambda *a, **kw: _chat_response(good))
        assert slm.slm_llm("sys", "user") == good

    def test_strips_markdown_fences_before_validating(self, monkeypatch):
        fenced = "```json\n" + json.dumps({"a": {"value": 1, "confidence": 0.5}}) + "\n```"
        monkeypatch.setattr(httpx, "post", lambda *a, **kw: _chat_response(fenced))
        assert slm.slm_llm("sys", "user") == fenced  # raw content is returned, parser handles fences

    def test_falls_back_on_connection_error(self, monkeypatch):
        def boom(*a, **kw): raise httpx.ConnectError("refused")
        monkeypatch.setattr(httpx, "post", boom)
        out = slm.slm_llm("Extract patient_name.", "DOCUMENT:\nPatient: Jane Smith. Payer: BCBS-TX.")
        assert json.loads(out)["patient_name"]["value"] == "Jane Smith"  # deterministic fallback ran

    def test_falls_back_on_timeout(self, monkeypatch):
        def boom(*a, **kw): raise httpx.TimeoutException("timed out")
        monkeypatch.setattr(httpx, "post", boom)
        out = slm.slm_llm("sys", "DOCUMENT:\nPatient: Jane Smith.")
        assert json.loads(out)["patient_name"]["value"] == "Jane Smith"

    def test_falls_back_on_unparseable_model_output(self, monkeypatch):
        monkeypatch.setattr(httpx, "post", lambda *a, **kw: _chat_response("not json at all"))
        out = slm.slm_llm("sys", "DOCUMENT:\nPatient: Jane Smith.")
        assert json.loads(out)["patient_name"]["value"] == "Jane Smith"

    def test_falls_back_on_http_error_status(self, monkeypatch):
        def kaboom(*a, **kw):
            req = httpx.Request("POST", "http://x/api/chat")
            return httpx.Response(500, request=req)
        monkeypatch.setattr(httpx, "post", kaboom)
        out = slm.slm_llm("sys", "DOCUMENT:\nPatient: Jane Smith.")
        assert json.loads(out)["patient_name"]["value"] == "Jane Smith"

    def test_sends_the_configured_model_and_a_bounded_num_predict(self, monkeypatch):
        seen = {}
        def capture(url, json, timeout):  # noqa: A002 - matches httpx.post's kwarg name
            seen["url"], seen["payload"] = url, json
            return _chat_response('{"a": {"value": 1, "confidence": 0.9}}')
        monkeypatch.setattr(httpx, "post", capture)
        slm.slm_llm("sys", "user")
        assert seen["url"] == f"{slm.OLLAMA_URL}/api/chat"
        assert seen["payload"]["model"] == slm.SLM_MODEL
        assert seen["payload"]["options"]["num_predict"] == slm.NUM_PREDICT
        assert seen["payload"]["options"]["temperature"] == 0.0

    def test_is_available_true_when_model_is_in_tags(self, monkeypatch):
        tags = httpx.Response(200, json={"models": [{"model": "llama3.2:latest"}]},
                              request=httpx.Request("GET", "http://x/api/tags"))
        monkeypatch.setattr(httpx, "get", lambda *a, **kw: tags)
        assert slm.is_available("llama3.2") is True

    def test_is_available_false_when_model_missing(self, monkeypatch):
        tags = httpx.Response(200, json={"models": [{"model": "mistral:latest"}]},
                              request=httpx.Request("GET", "http://x/api/tags"))
        monkeypatch.setattr(httpx, "get", lambda *a, **kw: tags)
        assert slm.is_available("llama3.2") is False

    def test_is_available_false_when_server_unreachable(self, monkeypatch):
        def boom(*a, **kw): raise httpx.ConnectError("refused")
        monkeypatch.setattr(httpx, "get", boom)
        assert slm.is_available() is False


@pytest.mark.integration
class TestSlmLlmLive:
    """Talks to a real Ollama server. Skips (not fails) if it isn't reachable with the model pulled —
    run `ollama pull llama3.2` (or set RCM_SLM_MODEL=mistral and `ollama pull mistral`) first."""

    @pytest.fixture(autouse=True)
    def require_ollama(self):
        if not slm.is_available():
            pytest.skip(f"Ollama with model {slm.SLM_MODEL!r} not reachable at {slm.OLLAMA_URL}")

    def test_live_extraction_returns_usable_json(self):
        raw = slm.slm_llm("Extract patient_name and payer_id.",
                          "DOCUMENT:\nPatient: Jane Smith. Payer: BCBS-TX.")
        data = json.loads(raw)
        assert data["patient_name"]["value"] == "Jane Smith"
