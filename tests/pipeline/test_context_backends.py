"""tests/pipeline/test_context_backends.py — call_llm backend selection (deterministic vs slm)."""

from pipeline.context import build_context
from pipeline.offline_llm import offline_llm
from pipeline.slm_llm import slm_llm


def test_default_backend_is_deterministic():
    ctx = build_context()
    assert ctx.call_llm is offline_llm and ctx.use_slm is False


def test_backend_slm_selects_the_slm_call_llm():
    ctx = build_context(backend="slm")
    assert ctx.call_llm is slm_llm and ctx.use_slm is True


def test_env_var_selects_the_backend(monkeypatch):
    monkeypatch.setenv("RCM_CALL_LLM", "slm")
    ctx = build_context()
    assert ctx.call_llm is slm_llm and ctx.use_slm is True


def test_explicit_backend_argument_overrides_the_env_var(monkeypatch):
    monkeypatch.setenv("RCM_CALL_LLM", "slm")
    ctx = build_context(backend="deterministic")
    assert ctx.call_llm is offline_llm and ctx.use_slm is False


def test_explicit_call_llm_overrides_backend_selection():
    sentinel = lambda system, user: "{}"  # noqa: E731
    ctx = build_context(backend="slm", call_llm=sentinel)
    assert ctx.call_llm is sentinel
    # use_slm still reflects the requested backend, since it drives model_router.route(prefer_local=...)
    assert ctx.use_slm is True


def test_unknown_backend_falls_back_to_deterministic():
    ctx = build_context(backend="nonsense")
    assert ctx.call_llm is offline_llm
