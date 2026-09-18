"""ingestion/format_parsers.py — HL7 v2, FHIR R4, EDI 837 parsers."""
from __future__ import annotations

import json
import re
from typing import Any


class HL7V2Parser:
    def parse(self, raw: bytes) -> dict[str, Any]:
        text = raw.decode("utf-8", errors="replace")
        segments: dict[str, list[str]] = {}
        for s in text.strip().splitlines():
            if len(s) > 3:
                segments[s[:3]] = s.split("|")
        pid = segments.get("PID", [])
        dg1 = segments.get("DG1", [])
        pr1 = segments.get("PR1", [])
        in1 = segments.get("IN1", [])
        return {
            "patient_name": self._g(pid, 5), "patient_dob": self._g(pid, 7),
            "patient_id": self._g(pid, 3),
            "diagnosis_codes": [self._g(dg1, 3)] if dg1 else [],
            "procedure_codes": [self._g(pr1, 3)] if pr1 else [],
            "payer_id": self._g(in1, 3), "raw_segments": segments,
        }
    def _g(self, seg: list[str], idx: int) -> str:
        try:
            return seg[idx].strip()
        except IndexError:
            return ""


class FHIRR4Parser:
    def parse(self, raw: bytes) -> dict[str, Any]:
        bundle = json.loads(raw)
        resources = {e["resource"]["resourceType"]: e["resource"]
                     for e in bundle.get("entry", []) if "resource" in e}
        patient  = resources.get("Patient", {})
        coverage = resources.get("Coverage", {})
        claim    = resources.get("Claim", {})
        return {
            "patient_name": self._name(patient), "patient_dob": patient.get("birthDate", ""),
            "patient_id": self._pid(patient), "diagnosis_codes": self._dx(claim),
            "procedure_codes": self._px(claim), "payer_id": self._payer(coverage),
            "raw_bundle": bundle,
        }
    def _name(self, p: dict) -> str:
        n = (p.get("name") or [{}])[0]
        return " ".join(n.get("given", []) + [n.get("family", "")])
    def _pid(self, p: dict) -> str:
        ids = p.get("identifier") or [{}]
        return ids[0].get("value", "")
    def _dx(self, c: dict) -> list[str]:
        return [d["diagnosisCodeableConcept"]["coding"][0]["code"]
                for d in c.get("diagnosis", []) if "diagnosisCodeableConcept" in d]
    def _px(self, c: dict) -> list[str]:
        return [cd["code"] for item in c.get("item", [])
                for cd in item.get("productOrService", {}).get("coding", [])]
    def _payer(self, cov: dict) -> str:
        payor = cov.get("payor") or [{}]
        return payor[0].get("identifier", {}).get("value", "")


class EDI837Parser:
    def parse(self, raw: bytes) -> dict[str, Any]:
        text = raw.decode("utf-8", errors="replace")
        segs = [s.split("*") for s in re.split(r"[~\n]", text) if s.strip()]
        seg_map: dict[str, list] = {}
        for s in segs:
            seg_map.setdefault(s[0], []).append(s)
        nm1: list = next((s for s in seg_map.get("NM1", []) if len(s) > 1 and s[1] == "QC"), [])
        hi  = [e.replace("ABK:", "").replace("ABF:", "") for s in seg_map.get("HI", []) for e in s[1:] if e]
        sv1 = [s[1].split(":")[1] if ":" in s[1] else s[1] for s in seg_map.get("SV1", []) if len(s) > 1]
        ref: list = next((s for s in seg_map.get("REF", []) if len(s) > 1 and s[1] == "2U"), [])
        return {
            "patient_name": " ".join(filter(None, [self._g(nm1, 4), self._g(nm1, 5)])),
            "patient_dob": "", "patient_id": self._g(nm1, 9),
            "diagnosis_codes": hi, "procedure_codes": sv1, "payer_id": self._g(ref, 2),
        }
    def _g(self, seg: list, idx: int) -> str:
        try:
            return seg[idx].strip()
        except IndexError:
            return ""
