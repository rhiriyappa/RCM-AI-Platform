"""tests/classification/test_rules.py"""
import pytest
from contracts.schemas import DocumentType
from classification.rules import apply_rules


class TestDenialRules:
    def test_co_code(self):
        assert apply_rules("Claim denied. CO-4.")[0].document_type == DocumentType.DENIAL_EOB
    def test_eob_keyword(self):
        assert apply_rules("Explanation of Benefits.")[0].document_type == DocumentType.DENIAL_EOB
    def test_rarc_code(self):
        assert apply_rules("RARC N56 applied.")[0].document_type == DocumentType.DENIAL_EOB
    def test_dense_confidence(self):
        assert apply_rules("Claim denied CO-11. EOB. RARC N95. Denied.")[0].confidence >= 0.80


class TestPriorAuthRules:
    def test_prior_auth_keyword(self):
        assert apply_rules("Prior authorization request.")[0].document_type == DocumentType.PRIOR_AUTH
    def test_medically_necessary(self):
        signals = apply_rules("Medically necessary. Utilization review.")
        types = [s.document_type for s in signals]
        assert DocumentType.PRIOR_AUTH in types


class TestReferralRules:
    def test_referral(self):
        assert apply_rules("I am referring this patient.")[0].document_type == DocumentType.REFERRAL
    def test_referred_to(self):
        assert apply_rules("Patient referred to Dr. Smith.")[0].document_type == DocumentType.REFERRAL


class TestEdgeCases:
    def test_empty(self):
        assert apply_rules("") == []
    def test_unrelated(self):
        assert apply_rules("The weather is sunny today.") == []
    def test_sorted_by_conf(self):
        s = apply_rules("Claim denied CO-4. Prior auth required.")
        for i in range(len(s) - 1):
            assert s[i].confidence >= s[i + 1].confidence
    def test_multiple_signals(self):
        assert len(apply_rules("Prior auth denied. CO-11 denial. Referral also attached.")) >= 2
