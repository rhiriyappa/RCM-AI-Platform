"""tests/pipeline/test_offline_llm.py — the LLM stand-in must emit the shape the parser expects."""
import json

from contracts.schemas import DocumentType
from extraction.parser import parse_llm_output
from pipeline.offline_llm import offline_llm
from tests.pipeline.conftest import webhook_text


def ask(text: str):
    raw = offline_llm("sys", f"DOCUMENT:\n{text}")
    return json.loads(raw), parse_llm_output(raw, "d", DocumentType.UNKNOWN)


def test_webhook_json():
    _, r = ask(webhook_text())
    assert r.patient_name.value == "Jane Smith" and r.payer_id.value == "BCBS-TX"
    assert [f.value for f in r.diagnosis_codes] == ["M54.5"]


def test_webhook_denial_codes():
    _, r = ask(webhook_text(denial={"reason_code": "CO-50", "appeal_by": "2024-12-31"}))
    assert [f.value for f in r.denial_reason_codes] == ["CO-50"] and r.appeal_deadline.value == "2024-12-31"


def test_fhir_bundle(sample_fhir_bundle):
    _, r = ask(json.dumps(sample_fhir_bundle))
    assert r.patient_name.value == "Robert Johnson" and r.patient_dob.value == "1965-08-22"
    assert [f.value for f in r.procedure_codes] == ["99214"]


def test_hl7_message():
    _, r = ask("MSH|^~\\&|A|B|C|D|20240101||ADT^A08|1|P|2.5\nPID|1||MRN-9||DOE^JOHN||19800102|M\n"
               "IN1|1|P|AETNA-001|Aetna\nDG1|1|I10|E11.9^x^I10\nPR1|1|CPT4|99213^y^C4")
    assert r.patient_name.value == "John Doe" and r.patient_dob.value == "1980-01-02"
    assert r.payer_id.value == "AETNA-001" and r.diagnosis_codes[0].value == "E11.9"


def test_edi_reads_last_name_and_dob():
    _, r = ask("ISA*00~\nNM1*QC*1*DOE*JOHN*A***MI*MRN-9~\nDMG*D8*19800102*M~\nREF*2U*UHC-002~\n"
               "HI*ABK:M545~\nSV1*HC:99213*100*UN*1~")
    assert r.patient_name.value == "John Doe" and r.patient_dob.value == "1980-01-02"
    assert r.diagnosis_codes[0].value == "M54.5" and r.payer_id.value == "UHC-002"


def test_fax_free_text():
    _, r = ask("Patient: Jane Smith\nDOB: 1978-04-12\nPayer: Aetna (AETNA-001)\nICD-10: M54.5, J45.901\n"
               "CPT: 99213\nClaim CLM123456 denied CO-4: reason")
    assert r.payer_id.value == "AETNA-001" and len(r.diagnosis_codes) == 2
    assert r.claim_number.value == "CLM123456" and r.denial_reason_codes[0].value == "CO-4"


def test_unparseable_text_yields_empty_object():
    raw, r = ask("nothing useful in here")
    assert r.mean_confidence == 0.0 and isinstance(raw, dict)


def test_truncated_marker_is_ignored():
    _, r = ask(webhook_text() + "\n\n[truncated to 6000 chars]")
    assert r.patient_name.value == "Jane Smith"
