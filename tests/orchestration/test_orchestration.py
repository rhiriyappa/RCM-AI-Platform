"""tests/orchestration/test_orchestration.py"""
import pytest

from orchestration.fallback import with_fallback
from orchestration.guardrails import check_json_schema, redact_pii, validate_output
from orchestration.model_router import ModelTier, route
from orchestration.prompt_registry import PromptRegistry


class TestPromptRegistry:
    def test_register_and_get(self):
        from contracts.schemas import PromptTemplate
        reg = PromptRegistry()
        t = PromptTemplate(name="test", version="v1", system="sys", user_template="usr")
        reg.register(t)
        assert reg.get("test", "v1") is not None

    def test_get_latest(self):
        from contracts.schemas import PromptTemplate
        reg = PromptRegistry()
        reg.register(PromptTemplate(name="t", version="v1", system="s1", user_template="u"))
        reg.register(PromptTemplate(name="t", version="v2", system="s2", user_template="u"))
        got = reg.get("t", "latest")
        assert got is not None

    def test_missing_returns_none(self):
        assert PromptRegistry().get("nonexistent") is None

    def test_list_versions(self):
        from contracts.schemas import PromptTemplate
        reg = PromptRegistry()
        reg.register(PromptTemplate(name="t", version="v1", system="s", user_template="u"))
        reg.register(PromptTemplate(name="t", version="v2", system="s", user_template="u"))
        assert set(reg.list_versions("t")) == {"v1", "v2"}


class TestModelRouter:
    def test_short_task_fast(self):      assert route("classify", 100).tier == ModelTier.FAST
    def test_long_text_premium(self):    assert route("extract", 6000).tier == ModelTier.PREMIUM
    def test_reasoning_premium(self):    assert route("generate", 200, require_reasoning=True).tier == ModelTier.PREMIUM
    def test_medium_standard(self):      assert route("extraction", 2000).tier == ModelTier.STANDARD


class TestGuardrails:
    def test_valid_output_passes(self):  assert validate_output("Valid output text").passed
    def test_too_short_fails(self):      assert not validate_output("Hi").passed
    def test_pii_redacted(self):
        r = redact_pii("SSN is 123-45-6789")
        assert "123-45-6789" not in r and "SSN-REDACTED" in r
    def test_valid_json_schema(self):
        r = check_json_schema('{"type":"denial","confidence":0.9}', ["type","confidence"])
        assert r.passed
    def test_missing_key_fails(self):
        r = check_json_schema('{"type":"denial"}', ["type","confidence"])
        assert not r.passed
    def test_invalid_json_fails(self):   assert not check_json_schema("not json", ["type"]).passed


class TestFallback:
    def test_llm_success(self):
        result = with_fallback(llm_fn=lambda: type("R", (), {"mean_confidence": 0.9})())
        assert result.source == "llm"

    def test_falls_to_rules(self):
        def bad_llm():  raise ConnectionError("timeout")
        result = with_fallback(llm_fn=bad_llm, rules_fn=lambda: "rules_result")
        assert result.source == "rules" and result.used_fallback

    def test_all_tiers_exhaust_raises(self):
        with pytest.raises(RuntimeError):
            with_fallback(llm_fn=lambda: (_ for _ in ()).throw(Exception("fail")))
