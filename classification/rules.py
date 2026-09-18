"""classification/rules.py — deterministic rule-based pre-classifier (Tier 1)."""
from __future__ import annotations
import re
from dataclasses import dataclass
from contracts.schemas import DocumentType


@dataclass
class RuleSignal:
    document_type: DocumentType
    confidence:    float
    matched_rule:  str


_CATALOG: list[tuple[DocumentType, list[str], float]] = [
    (DocumentType.DENIAL_EOB, [
        r"\bdenial\b", r"\bdenied\b", r"\bCO-\d+\b", r"\bPR-\d+\b",
        r"\bRARC\b", r"\bCARC\b", r"\bexplanation of benefits\b", r"\bEOB\b",
        r"\badjustment reason\b", r"\bremark code\b",
    ], 0.92),
    (DocumentType.PRIOR_AUTH, [
        r"\bprior auth", r"\bpre-auth", r"\bpre-certification\b",
        r"\bauthorization number\b", r"\bauth.*request\b",
        r"\bmedically necessary\b", r"\butilization review\b",
    ], 0.90),
    (DocumentType.REFERRAL, [
        r"\breferral\b", r"\breferred to\b", r"\brefer.*patient\b",
        r"\boutpatient.*referral\b", r"\bPCP.*refer", r"\bprimary care.*refer",
    ], 0.88),
    (DocumentType.CLAIM_837, [
        r"\b837\b", r"\bclaim.*form\b", r"\bCMS-1500\b", r"\bUB-04\b",
        r"\bplace of service\b", r"\bbilling.*provider\b",
    ], 0.88),
    (DocumentType.CLINICAL_NOTE, [
        r"\bSOAP note\b", r"\bdischarge summary\b", r"\bprogress note\b",
        r"\bassessment and plan\b", r"\bHPI\b", r"\bhistory of present illness\b",
    ], 0.85),
    (DocumentType.ELIGIBILITY, [
        r"\beligibility\b", r"\b271\b.*\bresponse\b", r"\b270\b.*\binquiry\b",
        r"\bbenefits\b.*\bverification\b", r"\bcoverage.*verification\b",
    ], 0.87),
]

_COMPILED = [(dt, [re.compile(p, re.IGNORECASE) for p in pats], conf)
             for dt, pats, conf in _CATALOG]


def apply_rules(text: str) -> list[RuleSignal]:
    signals: list[RuleSignal] = []
    text_lower = text.lower()
    for doc_type, compiled, base_conf in _COMPILED:
        hits = sum(1 for p in compiled if p.search(text_lower))
        if hits == 0:
            continue
        scale    = 0.7 + 0.3 * min(1.0, (hits / len(compiled)) * 4)
        adjusted = min(0.99, base_conf * scale)
        matched  = next(p.pattern for p in compiled if p.search(text_lower))
        signals.append(RuleSignal(document_type=doc_type,
                                   confidence=round(adjusted, 4),
                                   matched_rule=matched))
    return sorted(signals, key=lambda s: s.confidence, reverse=True)
