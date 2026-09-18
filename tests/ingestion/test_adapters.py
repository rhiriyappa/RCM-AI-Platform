"""tests/ingestion/test_adapters.py"""
import pytest
from unittest.mock import MagicMock
from contracts.schemas import SourceType
from ingestion.adapters import EDI837Adapter, FHIRBundleAdapter, HL7V2Adapter, S3FaxAdapter, WebhookAdapter


@pytest.fixture
def fhir_bundle():
    return {"resourceType": "Bundle", "type": "collection",
            "entry": [{"resource": {"resourceType": "Patient",
                                    "name": [{"family": "Smith", "given": ["Jane"]}],
                                    "birthDate": "1978-04-12",
                                    "identifier": [{"value": "MRN-00042"}]}}]}


class TestFHIRBundleAdapter:
    def test_source_type(self, fhir_bundle):
        p = FHIRBundleAdapter().from_json(fhir_bundle, "t1")
        assert p.source_type == SourceType.FHIR_R4
    def test_content_type(self, fhir_bundle):
        p = FHIRBundleAdapter().from_json(fhir_bundle, "t1")
        assert p.content_type == "application/fhir+json"
    def test_raw_bytes_non_empty(self, fhir_bundle):
        p = FHIRBundleAdapter().from_json(fhir_bundle, "t1")
        assert len(p.raw_bytes) > 0
    def test_source_id_preserved(self, fhir_bundle):
        p = FHIRBundleAdapter().from_json(fhir_bundle, "my-id")
        assert p.source_id == "my-id"

class TestHL7V2Adapter:
    HL7 = b"MSH|^~\\&|A|B|C|D|20240101||ADT^A01|1|P|2.5\rPID|1||MRN-001|||DOE^JOHN\r"
    def test_source_type(self):
        assert HL7V2Adapter().from_bytes(self.HL7, "h1").source_type == SourceType.HL7_V2
    def test_content_type(self):
        assert HL7V2Adapter().from_bytes(self.HL7, "h1").content_type == "application/hl7-v2"

class TestEDI837Adapter:
    def test_source_type(self):
        assert EDI837Adapter().from_bytes(b"ISA*00*~", "e1").source_type == SourceType.EDI_837

class TestWebhookAdapter:
    def test_source_type(self):
        p = WebhookAdapter().from_request(b"{}", {"content-type": "application/json"}, "w1")
        assert p.source_type == SourceType.WEBHOOK
    def test_headers_in_metadata(self):
        p = WebhookAdapter().from_request(b"data", {"content-type": "text/plain", "x-custom": "val"}, "w2")
        assert p.metadata["headers"]["x-custom"] == "val"

class TestS3FaxAdapter:
    def test_fetch_returns_fax_payload(self):
        mock_s3 = MagicMock()
        mock_s3.get_object.return_value = {"ContentType": "application/pdf", "Body": MagicMock(read=lambda: b"%PDF")}
        adapter = S3FaxAdapter(bucket="test-bucket")
        adapter._s3 = mock_s3
        p = adapter.fetch("fax/001.pdf")
        assert p.source_type == SourceType.FAX_S3
        assert p.metadata["bucket"] == "test-bucket"
