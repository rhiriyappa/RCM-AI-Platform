"""pipeline/offline_llm.py — deterministic stand-in for the extraction LLM.

Lets the whole pipeline run with no network or API key. It reads the DOCUMENT text
the engine sends and answers in the same JSON shape a real model is prompted for
({"field": {"value", "confidence"}}). Swap it for a real client by passing any
callable with the signature call_llm(system, user) -> str.
"""
from __future__ import annotations

import json
import re

_ICD  = re.compile(r"\b[A-Z]\d{2}\.?[0-9A-Z]{0,4}\b")
_CPT  = re.compile(r"\b\d{5}\b")
_CARC = re.compile(r"\b(?:CO|PR|OA|PI)-\d+\b")
_DATE = r"\d{4}-\d{2}-\d{2}"


def _f(value, conf: float) -> dict:
    return {"value": value, "confidence": conf}


def _wrap(d: dict, conf: float) -> dict:
    out: dict = {}
    for k, v in d.items():
        if v in (None, "", []):
            continue
        out[k] = [_f(x, conf) for x in v] if isinstance(v, list) else _f(v, conf)
    return out


def _from_json(obj: dict) -> dict | None:
    if obj.get("resourceType") == "Bundle":
        res = {e["resource"]["resourceType"]: e["resource"] for e in obj.get("entry", []) if "resource" in e}
        pat, cov, clm = res.get("Patient", {}), res.get("Coverage", {}), res.get("Claim", {})
        name = (pat.get("name") or [{}])[0]
        return {
            "patient_name": " ".join(name.get("given", []) + [name.get("family", "")]).strip(),
            "patient_dob": pat.get("birthDate"),
            "patient_id": (pat.get("identifier") or [{}])[0].get("value"),
            "payer_id": ((cov.get("payor") or [{}])[0].get("identifier") or {}).get("value"),
            "diagnosis_codes": [d["diagnosisCodeableConcept"]["coding"][0]["code"]
                                for d in clm.get("diagnosis", []) if "diagnosisCodeableConcept" in d],
            "procedure_codes": [c["code"] for i in clm.get("item", [])
                                for c in i.get("productOrService", {}).get("coding", [])],
            "total_charge": (clm.get("total") or {}).get("value"),
        }
    if "event" in obj:
        pat, payer = obj.get("patient", {}), obj.get("payer", {})
        den = obj.get("denial", {})
        return {
            "patient_name": pat.get("name"), "patient_dob": pat.get("dob"), "patient_id": pat.get("mrn"),
            "payer_id": payer.get("id"), "payer_name": payer.get("name"),
            "diagnosis_codes": obj.get("diagnosis_codes"), "procedure_codes": obj.get("procedure_codes"),
            "provider_npi": obj.get("provider_npi"), "claim_number": obj.get("claim_number"),
            "auth_number": obj.get("auth_number"),
            "denial_reason_codes": [den["reason_code"]] if den.get("reason_code") else None,
            "appeal_deadline": den.get("appeal_by"),
        }
    return None


def _from_hl7(text: str) -> dict:
    seg = {ln[:3]: ln.split("|") for ln in text.splitlines() if len(ln) > 3}
    g = lambda s, i: (seg.get(s, []) + [""] * 20)[i].split("^")  # noqa: E731
    last, first = (g("PID", 5) + [""])[:2]
    dob = g("PID", 7)[0]
    return {
        "patient_name": f"{first.title()} {last.title()}".strip(),
        "patient_dob": f"{dob[:4]}-{dob[4:6]}-{dob[6:8]}" if len(dob) == 8 else "",
        "patient_id": g("PID", 3)[0], "payer_id": g("IN1", 3)[0],
        "diagnosis_codes": [g("DG1", 3)[0]] if "DG1" in seg else [],
        "procedure_codes": [g("PR1", 3)[0]] if "PR1" in seg else [],
        "provider_npi": g("PV1", 7)[0], "service_date": None,
    }


def _from_edi(text: str) -> dict:
    segs = [s.split("*") for s in re.split(r"[~\n]", text) if s.strip()]
    pick = lambda tag, cond=lambda s: True: next((s for s in segs if s[0] == tag and cond(s)), [])  # noqa: E731
    at = lambda s, i: s[i] if len(s) > i else ""  # noqa: E731
    qc, dmg, clm = pick("NM1", lambda s: at(s, 1) == "QC"), pick("DMG"), pick("CLM")
    dob = at(dmg, 2)
    return {
        "patient_name": f"{at(qc, 4).title()} {at(qc, 3).title()}".strip(),
        "patient_dob": f"{dob[:4]}-{dob[4:6]}-{dob[6:8]}" if len(dob) == 8 else "",
        "patient_id": at(qc, 9), "member_id": at(qc, 9),
        "payer_id": at(pick("REF", lambda s: at(s, 1) == "2U"), 2),
        "provider_npi": at(pick("NM1", lambda s: at(s, 1) == "85"), 9),
        "claim_number": at(clm, 1), "total_charge": at(clm, 2),
        "diagnosis_codes": [_icd_dot(e.split(":")[1]) for s in segs if s[0] == "HI" for e in s[1:] if ":" in e],
        "procedure_codes": [s[1].split(":")[1] for s in segs if s[0] == "SV1" and ":" in s[1]],
    }


def _icd_dot(code: str) -> str:
    return code if "." in code or len(code) <= 3 else f"{code[:3]}.{code[3:]}"


def _from_text(text: str) -> dict:
    def grab(*patterns: str) -> str:
        for p in patterns:
            m = re.search(p, text, re.IGNORECASE)
            if m:
                return m.group(1).strip()
        return ""

    payer_line = grab(r"Payer:?\s*([^\n]+)")
    payer_id = (re.search(r"\(([A-Z0-9-]+)\)", payer_line) or re.search(r"^([A-Z]+-[A-Z0-9]+)", payer_line)
                or re.search(r"\bPayer\s+([A-Z]+-[A-Z0-9]+)", text))
    icd_zone = grab(r"(?:ICD-?10|Diagnosis|ICD)[:\s]+([^\n]*)")
    cpt_zone = grab(r"CPT[:\s]+([^\n]*)")
    return {
        "patient_name": grab(r"Patient:?\s+([A-Z][a-z]+ [A-Z][a-z]+)"),
        "patient_dob": grab(rf"DOB:?\s*({_DATE})"),
        "patient_id": grab(r"\b(MRN-\d+)"),
        "member_id": grab(r"Member ID:?\s*([A-Z0-9-]+)"),
        "payer_id": payer_id.group(1) if payer_id else "",
        "payer_name": re.sub(r"\s*\(.*", "", payer_line) if "(" in payer_line else "",
        "provider_npi": grab(r"Provider NPI:?\s*(\d{10})"),
        "claim_number": grab(r"Claim\s+(CLM\d+)"),
        "service_date": grab(rf"Date of service:?\s*({_DATE})"),
        "total_charge": grab(r"Billed amount:?\s*\$?([\d.]+)"),
        "auth_number": grab(r"Auth(?:orization)?(?: number)?:?\s*((?:PA|AUTH-)[A-Z0-9-]+)"),
        "auth_status": grab(r"Status:?\s*([A-Za-z ]+?)(?:\.|\n|$)"),
        "appeal_deadline": grab(rf"Appeal by\s*({_DATE})"),
        "diagnosis_codes": _ICD.findall(icd_zone),
        "procedure_codes": _CPT.findall(cpt_zone),
        "denial_reason_codes": _CARC.findall(text),
    }


def offline_llm(system: str, user: str) -> str:
    text = user.split("DOCUMENT:\n", 1)[-1].split("\n\n[truncated", 1)[0].strip()
    fields: dict | None = None
    conf = 0.86                                   # free text: least certain
    try:
        obj = json.loads(text)
        fields, conf = (_from_json(obj) if isinstance(obj, dict) else None), 0.97
    except json.JSONDecodeError:
        pass
    if fields is None and text.startswith("MSH|"):
        fields, conf = _from_hl7(text), 0.93
    elif fields is None and text.startswith("ISA*"):
        fields, conf = _from_edi(text), 0.95
    elif fields is None:
        fields = _from_text(text)
    return json.dumps(_wrap(fields, conf))
