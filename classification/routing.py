"""classification/routing.py — DocumentType → SQS queue."""
from contracts.schemas import DocumentType

_ROUTING_MAP: dict[DocumentType, str] = {
    DocumentType.PRIOR_AUTH:    "onecall-prior-auth-agent.fifo",
    DocumentType.DENIAL_EOB:    "onecall-denial-agent.fifo",
    DocumentType.REFERRAL:      "onecall-triage-agent",
    DocumentType.CLAIM_837:     "onecall-claim-processor",
    DocumentType.CLINICAL_NOTE: "onecall-clinical-enrichment",
    DocumentType.ELIGIBILITY:   "onecall-eligibility-agent",
    DocumentType.UNKNOWN:       "onecall-human-review",
}


def resolve_routing_queue(document_type: DocumentType) -> str:
    return _ROUTING_MAP.get(document_type, "onecall-human-review")


def is_high_priority(document_type: DocumentType) -> bool:
    return document_type in {DocumentType.PRIOR_AUTH, DocumentType.DENIAL_EOB}
