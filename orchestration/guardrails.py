"""orchestration/guardrails.py — output validation, PII redaction, hallucination checks."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

_PII_PATTERNS = [
    (re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),          "SSN"),
    (re.compile(r"\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b"), "CARD"),
    (re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"), "EMAIL"),
]


@dataclass
class GuardrailResult:
    passed:   bool
    failures: list[str] = field(default_factory=list)
    redacted: str = ""


def redact_pii(text: str) -> str:
    for pattern, label in _PII_PATTERNS:
        text = pattern.sub(f"[{label}-REDACTED]", text)
    return text


def validate_output(text: str, min_length: int = 5, max_length: int = 50_000) -> GuardrailResult:
    failures: list[str] = []
    if not text or len(text.strip()) < min_length:
        failures.append(f"Output too short (< {min_length} chars)")
    if len(text) > max_length:
        failures.append(f"Output too long (> {max_length} chars)")
    for _, label in _PII_PATTERNS:
        if f"[{label}-REDACTED]" in text:
            failures.append(f"PII detected and redacted: {label}")
    return GuardrailResult(passed=len(failures) == 0, failures=failures, redacted=redact_pii(text))


def check_json_schema(text: str, required_keys: list[str]) -> GuardrailResult:
    import json
    failures: list[str] = []
    cleaned = re.sub(r"```(?:json)?|```", "", text).strip()
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        return GuardrailResult(passed=False, failures=[f"Invalid JSON: {exc}"])
    for key in required_keys:
        if key not in data:
            failures.append(f"Missing required key: {key}")
    return GuardrailResult(passed=len(failures) == 0, failures=failures)
