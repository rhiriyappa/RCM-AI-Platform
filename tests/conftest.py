"""tests/conftest.py — shared fixtures and AWS environment setup."""
import os

import pytest

os.environ.setdefault("AWS_ACCESS_KEY_ID", "test")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "test")
os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")
os.environ.setdefault("AWS_ENDPOINT_URL", "http://localhost:4566")


@pytest.fixture(scope="session")
def sample_fhir_bundle():
    return {
        "resourceType": "Bundle", "type": "collection",
        "entry": [
            {"resource": {"resourceType": "Patient",
                          "name": [{"family": "Johnson", "given": ["Robert"]}],
                          "birthDate": "1965-08-22",
                          "identifier": [{"value": "MRN-12345"}]}},
            {"resource": {"resourceType": "Coverage",
                          "payor": [{"identifier": {"value": "AETNA-001"}}]}},
            {"resource": {"resourceType": "Claim",
                          "diagnosis": [{"diagnosisCodeableConcept": {"coding": [{"code": "M54.5"}]}}],
                          "item": [{"productOrService": {"coding": [{"code": "99214"}]}}]}},
        ],
    }
