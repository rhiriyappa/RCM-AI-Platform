"""extraction/enrichment.py — NPI lookup, code validation, payer normalisation."""
from __future__ import annotations
import logging, re
from typing import Optional
from contracts.schemas import ExtractionResult

logger = logging.getLogger(__name__)
_NPI_RE = re.compile(r"^\d{10}$")


class NPILookup:
    def lookup(self, npi: str) -> Optional[dict]: raise NotImplementedError


class MockNPILookup(NPILookup):
    _KNOWN = {
        "1234567890": {"npi": "1234567890", "name": "Dr. Jane Smith",  "taxonomy": "207Q00000X", "state": "TX"},
        "9876543210": {"npi": "9876543210", "name": "Dr. Robert Jones","taxonomy": "208D00000X", "state": "CA"},
    }
    def lookup(self, npi: str) -> Optional[dict]: return self._KNOWN.get(npi)


class CodeValidator:
    _VALID_ICD10 = {"M54.5","M54.50","J45.901","J18.9","Z00.00","Z87.891",
                    "E11.9","E11.65","I10","J44.1","M51.16","N18.3"}
    _VALID_CPT   = {"99213","99214","99215","99233","73721","27447",
                    "22612","94640","94010","90837","99243"}
    def validate_icd10(self, code: str) -> bool: return code.upper() in self._VALID_ICD10
    def validate_cpt(self, code: str) -> bool:   return code in self._VALID_CPT


class ExtractionEnricher:
    def __init__(self, npi_lookup: NPILookup, code_validator: CodeValidator) -> None:
        self._npi = npi_lookup; self._codes = code_validator

    def enrich(self, result: ExtractionResult) -> ExtractionResult:
        kwargs = result.model_dump()
        warnings = list(result.extraction_warnings)
        npi_validated = False
        if result.provider_npi and _NPI_RE.match(str(result.provider_npi.value)):
            info = self._npi.lookup(str(result.provider_npi.value))
            npi_validated = bool(info)
            if not info:
                warnings.append(f"NPI not found in registry: {result.provider_npi.value}")
        kwargs["npi_validated"] = npi_validated
        codes_validated = True
        for f in result.diagnosis_codes:
            if not self._codes.validate_icd10(str(f.value)):
                warnings.append(f"ICD-10 not in reference table: {f.value}"); codes_validated = False
        for f in result.procedure_codes:
            if not self._codes.validate_cpt(str(f.value)):
                warnings.append(f"CPT not in reference table: {f.value}"); codes_validated = False
        kwargs["codes_validated"] = codes_validated
        kwargs["extraction_warnings"] = warnings
        return ExtractionResult(**kwargs)
