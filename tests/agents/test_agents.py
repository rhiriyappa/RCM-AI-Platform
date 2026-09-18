"""tests/agents/test_agents.py"""
from agents.denial import DenialAppealAgent
from agents.prior_auth import PriorAuthAgent
from agents.triage import ReferralTriageAgent
from contracts.schemas import AgentState, AgentStatus, DocumentType


def make_state(doc_type=DocumentType.DENIAL_EOB, extraction=None, doc_id="ag-001"):
    return AgentState(document_id=doc_id, document_type=doc_type,
                      extraction=extraction or {})


class TestPriorAuthAgent:
    agent = PriorAuthAgent()

    def test_missing_fields_fails(self):
        state = make_state(DocumentType.PRIOR_AUTH, {})
        result = self.agent.run(state)
        assert result.status == AgentStatus.FAILED

    def test_low_conf_needs_hitl(self):
        state = make_state(DocumentType.PRIOR_AUTH, {
            "patient_name": "Jane Smith", "member_id": "MBR-001",
            "provider_npi": "1234567890", "diagnosis_codes": ["M54.5"],
            "procedure_codes": ["22612"], "payer_id": "BCBS-TX",
            "mean_confidence": 0.50,
        })
        result = self.agent.run(state)
        assert result.hitl_required is True

    def test_high_conf_completes(self):
        state = make_state(DocumentType.PRIOR_AUTH, {
            "patient_name": "Jane Smith", "member_id": "MBR-001",
            "provider_npi": "1234567890", "diagnosis_codes": ["M54.5"],
            "procedure_codes": ["22612"], "payer_id": "BCBS-TX",
            "mean_confidence": 0.92,
        })
        result = self.agent.run(state)
        assert result.status == AgentStatus.COMPLETED

    def test_audit_trail_populated(self):
        state = make_state(DocumentType.PRIOR_AUTH, {
            "patient_name": "X", "member_id": "M", "provider_npi": "1234567890",
            "diagnosis_codes": ["M54.5"], "procedure_codes": ["22612"],
            "payer_id": "P", "mean_confidence": 0.90,
        })
        result = self.agent.run(state)
        assert len(result.audit_trail) > 0

    def test_output_has_action(self):
        state = make_state(DocumentType.PRIOR_AUTH, {
            "patient_name": "X", "member_id": "M", "provider_npi": "1234567890",
            "diagnosis_codes": ["M54.5"], "procedure_codes": ["22612"],
            "payer_id": "P", "mean_confidence": 0.90,
        })
        result = self.agent.run(state)
        assert result.output.get("action") == "submit_prior_auth"


class TestDenialAppealAgent:
    agent = DenialAppealAgent()

    def test_no_codes_completes(self):
        state = make_state(DocumentType.DENIAL_EOB, {"denial_reason_codes": [], "mean_confidence": 0.80})
        result = self.agent.run(state)
        assert result.status == AgentStatus.COMPLETED

    def test_overturnable_code_generates_letter(self):
        state = make_state(DocumentType.DENIAL_EOB, {
            "denial_reason_codes": ["CO-4"], "claim_number": "CLM-001",
            "patient_name": "Jane", "appeal_deadline": "2024-04-15",
            "mean_confidence": 0.90,
        })
        result = self.agent.run(state)
        assert result.status == AgentStatus.COMPLETED
        assert result.output.get("letter_status") == "draft_generated"

    def test_low_conf_needs_hitl(self):
        state = make_state(DocumentType.DENIAL_EOB, {
            "denial_reason_codes": ["CO-11"], "mean_confidence": 0.50,
        })
        result = self.agent.run(state)
        assert result.hitl_required is True

    def test_strategy_selected(self):
        state = make_state(DocumentType.DENIAL_EOB, {
            "denial_reason_codes": ["CO-50"], "mean_confidence": 0.90,
            "patient_name": "X", "claim_number": "C1",
        })
        result = self.agent.run(state)
        assert result.output.get("strategy") == "medical_necessity"


class TestReferralTriageAgent:
    agent = ReferralTriageAgent()

    def test_low_conf_needs_hitl(self):
        state = make_state(DocumentType.REFERRAL, {"diagnosis_codes": ["M54.5"], "mean_confidence": 0.45})
        result = self.agent.run(state)
        assert result.hitl_required is True

    def test_routine_referral_completes(self):
        state = make_state(DocumentType.REFERRAL, {"diagnosis_codes": ["M54.5"], "mean_confidence": 0.85})
        result = self.agent.run(state)
        assert result.status == AgentStatus.COMPLETED
        assert result.output.get("urgency") == "routine"

    def test_urgent_dx_routes_urgently(self):
        state = make_state(DocumentType.REFERRAL, {"diagnosis_codes": ["I21.9"], "mean_confidence": 0.85})
        result = self.agent.run(state)
        assert result.output.get("urgency") == "urgent"
        assert "urgent" in result.output.get("queue", "")

    def test_provider_matched(self):
        state = make_state(DocumentType.REFERRAL, {"diagnosis_codes": ["M54.5"], "mean_confidence": 0.88})
        result = self.agent.run(state)
        assert result.output.get("matched_provider") is not None
