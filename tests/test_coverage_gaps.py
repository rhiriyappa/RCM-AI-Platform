"""
tests/test_coverage_gaps.py
Targeted coverage tests for modules that were not fully exercised:
  - observability/metrics.py
  - observability/eval_pipeline.py
  - ingestion/format_parsers.py
  - ingestion/sqs_fanout.py
  - ingestion/textract_ocr.py
  - orchestration/prompt_registry.py (load_from_dir)
"""
import json, pytest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch, call


# ── observability/metrics.py ────────────────────────────────────────────────

class TestMetrics:
    def test_estimate_cost_known_model(self):
        from observability.metrics import estimate_cost
        cost = estimate_cost("claude-sonnet-4-20250514", 1000, 500)
        assert cost > 0

    def test_estimate_cost_unknown_model_uses_default(self):
        from observability.metrics import estimate_cost
        cost = estimate_cost("unknown-model", 1000, 500)
        assert cost > 0

    def test_record_call_returns_record(self):
        from observability.metrics import record_call
        rec = record_call(
            document_id="d1", model="claude-sonnet-4-20250514",
            prompt_name="test", prompt_version="v1",
            input_tokens=500, output_tokens=200,
            latency_ms=320.5, success=True,
        )
        assert rec.call_id
        assert rec.cost_usd > 0
        assert rec.latency_ms == 320.5
        assert rec.success is True

    def test_record_call_failure(self):
        from observability.metrics import record_call
        rec = record_call(
            document_id="d1", model="gpt-4o",
            prompt_name="test", prompt_version="v1",
            input_tokens=0, output_tokens=0,
            latency_ms=50.0, success=False, error="timeout",
        )
        assert rec.success is False
        assert rec.error == "timeout"

    def test_instrumented_llm_records_on_success(self):
        from observability.metrics import instrumented_llm
        mock_fn = MagicMock(return_value="result text")
        wrapped = instrumented_llm(mock_fn, "d1", "claude-sonnet-4-20250514", "test", "v1")
        out = wrapped(system="sys", user="usr")
        assert out == "result text"
        mock_fn.assert_called_once()

    def test_instrumented_llm_raises_on_failure(self):
        from observability.metrics import instrumented_llm
        def bad(system, user): raise ConnectionError("timeout")
        wrapped = instrumented_llm(bad, "d1", "claude-haiku-4-5-20251001", "test", "v1")
        with pytest.raises(ConnectionError):
            wrapped(system="sys", user="usr")


# ── observability/eval_pipeline.py ──────────────────────────────────────────

class TestEvalPipeline:
    def test_run_eval_perfect_score(self, tmp_path):
        from observability.eval_pipeline import run_eval
        gold = tmp_path / "gold.jsonl"
        gold.write_text(json.dumps({
            "source_type": "fhir_r4",
            "expected": {"patient_name": "Jane Smith", "payer_id": "BCBS"}
        }) + "\n")

        def extractor(rec):
            return {"patient_name": "Jane Smith", "payer_id": "BCBS"}

        report = run_eval(gold, extractor, threshold=0.80)
        assert report.mean_f1 == 1.0
        assert report.passed is True

    def test_run_eval_zero_score(self, tmp_path):
        from observability.eval_pipeline import run_eval
        gold = tmp_path / "gold.jsonl"
        gold.write_text(json.dumps({
            "expected": {"patient_name": "Jane Smith"}
        }) + "\n")

        def extractor(rec):
            return {"patient_name": "Wrong Name"}

        report = run_eval(gold, extractor, threshold=0.80)
        assert report.mean_f1 == 0.0
        assert report.passed is False

    def test_run_eval_list_field_f1(self, tmp_path):
        from observability.eval_pipeline import run_eval
        gold = tmp_path / "gold.jsonl"
        gold.write_text(json.dumps({
            "expected": {"diagnosis_codes": ["M54.5", "J45.901"]}
        }) + "\n")

        def extractor(rec):
            return {"diagnosis_codes": ["M54.5"]}   # half correct

        report = run_eval(gold, extractor, threshold=0.0)
        assert 0.0 < report.mean_f1 < 1.0


# ── ingestion/format_parsers.py ─────────────────────────────────────────────

class TestHL7V2Parser:
    HL7 = (
        b"MSH|^~\\&|SEND|FAC|RECV|DEST|20240101||ADT^A01|123|P|2.5\r"
        b"PID|1||MRN-001^^^HospA||DOE^JOHN||19800515|M\r"
        b"DG1|1||M54.5^Low back pain^ICD10\r"
        b"PR1|1||99213^Office visit^CPT\r"
        b"IN1|1||BCBS-TX\r"
    )

    def test_patient_id(self):
        from ingestion.format_parsers import HL7V2Parser
        r = HL7V2Parser().parse(self.HL7)
        assert r["patient_id"] == "MRN-001^^^HospA"

    def test_raw_segments_present(self):
        from ingestion.format_parsers import HL7V2Parser
        r = HL7V2Parser().parse(self.HL7)
        assert "MSH" in r["raw_segments"] and "PID" in r["raw_segments"]

    def test_payer_id(self):
        from ingestion.format_parsers import HL7V2Parser
        r = HL7V2Parser().parse(self.HL7)
        assert r["payer_id"] == "BCBS-TX"

    def test_empty_bytes(self):
        from ingestion.format_parsers import HL7V2Parser
        r = HL7V2Parser().parse(b"")
        assert r["patient_name"] == "" and r["diagnosis_codes"] == []


class TestFHIRR4Parser:
    def test_multi_dx_codes(self):
        from ingestion.format_parsers import FHIRR4Parser
        bundle = {"resourceType": "Bundle", "entry": [
            {"resource": {"resourceType": "Claim",
                "diagnosis": [
                    {"diagnosisCodeableConcept": {"coding": [{"code": "M54.5"}]}},
                    {"diagnosisCodeableConcept": {"coding": [{"code": "J45.901"}]}},
                ],
                "item": [{"productOrService": {"coding": [{"code": "99213"}]}}]}}
        ]}
        r = FHIRR4Parser().parse(json.dumps(bundle).encode())
        assert "M54.5" in r["diagnosis_codes"] and "J45.901" in r["diagnosis_codes"]

    def test_empty_bundle(self):
        from ingestion.format_parsers import FHIRR4Parser
        r = FHIRR4Parser().parse(json.dumps({"resourceType": "Bundle", "entry": []}).encode())
        assert r["patient_name"] == "" and r["diagnosis_codes"] == []

    def test_multi_procedure_codes(self):
        from ingestion.format_parsers import FHIRR4Parser
        bundle = {"resourceType": "Bundle", "entry": [
            {"resource": {"resourceType": "Claim", "diagnosis": [],
                "item": [
                    {"productOrService": {"coding": [{"code": "99213"}]}},
                    {"productOrService": {"coding": [{"code": "73721"}]}},
                ]}}
        ]}
        r = FHIRR4Parser().parse(json.dumps(bundle).encode())
        assert "99213" in r["procedure_codes"] and "73721" in r["procedure_codes"]


class TestEDI837Parser:
    EDI = (
        b"ISA*00*~\nGS*HC*SENDER*RECV*20240101*1200*1*X*005010X222A1~\n"
        b"ST*837*0001~\nNM1*QC*1*DOE*JOHN****MI*MBR-001~\n"
        b"HI*ABK:M54.5*ABF:J45.901~\nSV1*HC:99213*150.00~\nREF*2U*BCBS-001~\n"
    )

    def test_diagnosis_codes(self):
        from ingestion.format_parsers import EDI837Parser
        r = EDI837Parser().parse(self.EDI)
        assert any("M54.5" in c for c in r["diagnosis_codes"])

    def test_procedure_codes(self):
        from ingestion.format_parsers import EDI837Parser
        r = EDI837Parser().parse(self.EDI)
        assert any("99213" in c for c in r["procedure_codes"])

    def test_payer_id(self):
        from ingestion.format_parsers import EDI837Parser
        r = EDI837Parser().parse(self.EDI)
        assert r["payer_id"] == "BCBS-001"

    def test_empty_bytes(self):
        from ingestion.format_parsers import EDI837Parser
        r = EDI837Parser().parse(b"")
        assert r["diagnosis_codes"] == [] and r["procedure_codes"] == []


# ── ingestion/sqs_fanout.py ─────────────────────────────────────────────────

class TestSQSFanout:
    def _make_fanout(self, mock_sqs):
        from ingestion.sqs_fanout import SQSFanout
        fanout = SQSFanout(
            classifier_queue_url="http://localhost:4566/000/onecall-classify.fifo",
            extraction_queue_url="http://localhost:4566/000/onecall-extract.fifo",
            dlq_url="http://localhost:4566/000/onecall-dlq",
        )
        fanout._sqs = mock_sqs
        return fanout

    def _make_doc(self):
        from contracts.schemas import DocumentType, RawDocument, SourceType
        return RawDocument(
            document_id="doc-001", source_id="s1",
            source_type=SourceType.FHIR_R4, document_type=DocumentType.DENIAL_EOB,
            ingested_at=datetime.now(timezone.utc),
            full_text="Claim denied CO-4. Patient Jane Smith.",
        )

    def test_publish_sends_to_both_queues(self):
        mock_sqs = MagicMock()
        fanout = self._make_fanout(mock_sqs)
        fanout.publish(self._make_doc())
        assert mock_sqs.send_message.call_count == 2

    def test_publish_message_body_is_json(self):
        mock_sqs = MagicMock()
        fanout = self._make_fanout(mock_sqs)
        fanout.publish(self._make_doc())
        body = mock_sqs.send_message.call_args_list[0][1]["MessageBody"]
        parsed = json.loads(body)
        assert parsed["document_id"] == "doc-001"

    def test_dlq_send(self):
        from contracts.schemas import ErrorEnvelope
        mock_sqs = MagicMock()
        fanout = self._make_fanout(mock_sqs)
        env = ErrorEnvelope(document_id="d1", source_id="s1",
                             errors=["bad ocr"], warnings=[], raw_snapshot={})
        fanout.send_to_dlq(env)
        mock_sqs.send_message.assert_called_once()
        body = json.loads(mock_sqs.send_message.call_args[1]["MessageBody"])
        assert body["document_id"] == "d1"


# ── ingestion/textract_ocr.py ───────────────────────────────────────────────

class TestTextractOCR:
    def _mock_textract(self, blocks, job_status="SUCCEEDED"):
        mock = MagicMock()
        mock.start_document_text_detection.return_value = {"JobId": "job-001"}
        mock.get_document_text_detection.return_value = {
            "JobStatus": job_status, "Blocks": blocks
        }
        return mock

    def _line_block(self, text, conf, page=1):
        return {"BlockType": "LINE", "Text": text, "Confidence": conf, "Page": page}

    def test_builds_full_text(self):
        from ingestion.textract_ocr import TextractOCR
        ocr = TextractOCR()
        ocr._textract = self._mock_textract([
            self._line_block("Patient: Jane Smith", 92.0),
            self._line_block("Diagnosis: M54.5", 88.0),
        ])
        result = ocr.extract_async("bucket", "key.pdf")
        assert "Patient: Jane Smith" in result.full_text
        assert "Diagnosis: M54.5" in result.full_text

    def test_mean_confidence_calculated(self):
        from ingestion.textract_ocr import TextractOCR
        ocr = TextractOCR()
        ocr._textract = self._mock_textract([
            self._line_block("Line 1", 80.0),
            self._line_block("Line 2", 90.0),
        ])
        result = ocr.extract_async("bucket", "key.pdf")
        assert result.mean_confidence == 85.0

    def test_low_conf_blocks_flagged(self):
        from ingestion.textract_ocr import TextractOCR
        ocr = TextractOCR()
        ocr._textract = self._mock_textract([
            self._line_block("Clear text", 95.0),
            self._line_block("Blurry text", 60.0),
        ])
        result = ocr.extract_async("bucket", "key.pdf")
        assert len(result.low_conf_blocks) == 1
        assert result.low_conf_blocks[0]["text"] == "Blurry text"

    def test_failed_job_raises(self):
        from ingestion.textract_ocr import TextractOCR
        ocr = TextractOCR()
        ocr._textract = self._mock_textract([], job_status="FAILED")
        with pytest.raises(RuntimeError, match="failed"):
            ocr.extract_async("bucket", "key.pdf")

    def test_multi_page_text_joined(self):
        from ingestion.textract_ocr import TextractOCR
        ocr = TextractOCR()
        ocr._textract = self._mock_textract([
            self._line_block("Page 1 text", 90.0, page=1),
            self._line_block("Page 2 text", 92.0, page=2),
        ])
        result = ocr.extract_async("bucket", "key.pdf")
        assert len(result.page_texts) == 2
        assert "Page 1 text" in result.page_texts[0]
        assert "Page 2 text" in result.page_texts[1]

    def test_empty_blocks_zero_confidence(self):
        from ingestion.textract_ocr import TextractOCR
        ocr = TextractOCR()
        ocr._textract = self._mock_textract([])
        result = ocr.extract_async("bucket", "key.pdf")
        assert result.mean_confidence == 0.0
        assert result.full_text == ""


# ── orchestration/prompt_registry.py ───────────────────────────────────────

class TestPromptRegistryLoadFromDir:
    def test_load_from_dir(self, tmp_path):
        from orchestration.prompt_registry import PromptRegistry
        prompt_file = tmp_path / "extraction_v1.json"
        prompt_file.write_text(json.dumps({
            "name": "extraction", "version": "v1",
            "system": "You are an extractor.", "user_template": "Extract: {text}",
            "model": "claude-sonnet-4-20250514",
        }))
        reg = PromptRegistry()
        count = reg.load_from_dir(tmp_path)
        assert count == 1
        assert reg.get("extraction", "v1") is not None

    def test_load_from_dir_ignores_bad_files(self, tmp_path):
        from orchestration.prompt_registry import PromptRegistry
        (tmp_path / "bad.json").write_text("not valid json{{{{")
        (tmp_path / "also_bad.json").write_text(json.dumps({"invalid": "schema"}))
        reg = PromptRegistry()
        count = reg.load_from_dir(tmp_path)
        assert count == 0   # all failed gracefully
