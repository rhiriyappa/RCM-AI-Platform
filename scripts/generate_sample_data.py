#!/usr/bin/env python3
"""scripts/generate_sample_data.py — regenerate the synthetic samples in sample_data/.

All data is fictitious. Output is deterministic (fixed seed), so re-running
produces identical files. Each source gets COUNT samples; a few per source are
deliberately defective so the validator / DLQ path is exercised.
"""
import argparse
import json
import random
import shutil
from pathlib import Path

COUNT = 25
HL7_COUNT = 50  # HL7 gets extra volume to cover all three message types it's classified on
ROOT = Path(__file__).parent.parent / "sample_data"

FIRST = ["Jane", "Robert", "Maria", "David", "Aisha", "Wei", "Carlos", "Priya", "Tom", "Linda",
         "James", "Fatima", "Kevin", "Olga", "Samuel"]
LAST = ["Smith", "Johnson", "Garcia", "Lee", "Patel", "Nguyen", "Brown", "Khan", "Miller",
        "Davis", "Wilson", "Lopez", "Clark", "Young", "Hall"]
PAYERS = [("BCBS-TX", "Blue Cross Blue Shield of Texas"), ("AETNA-001", "Aetna"),
          ("UHC-002", "UnitedHealthcare"), ("CIGNA-03", "Cigna"), ("HUMANA-04", "Humana"),
          ("MEDICARE-A", "Medicare"), ("ANTHEM-05", "Anthem")]
ICD10 = ["M54.5", "J45.901", "E11.9", "I10", "K21.9", "F41.1", "N39.0", "G43.909", "M17.11",
         "J06.9", "R07.9", "Z00.00"]
CPT = ["99213", "99214", "99203", "93000", "94640", "71046", "80053", "97110", "45378",
       "73721", "99285", "36415"]
DENIAL = [("CO-4", "procedure code inconsistent with modifier"), ("CO-16", "claim lacks information"),
          ("CO-50", "not medically necessary"), ("CO-97", "benefit included in another service"),
          ("PR-1", "deductible amount")]


class Patient:
    def __init__(self, rng: random.Random, i: int):
        self.first = rng.choice(FIRST)
        self.last = rng.choice(LAST)
        self.dob = f"{rng.randint(1935, 2005)}-{rng.randint(1, 12):02d}-{rng.randint(1, 28):02d}"
        self.mrn = f"MRN-{10000 + i * 37 + rng.randint(0, 30)}"
        self.payer_id, self.payer_name = rng.choice(PAYERS)
        self.dx = rng.sample(ICD10, rng.randint(1, 3))
        self.cpt = rng.sample(CPT, rng.randint(1, 3))
        self.npi = f"{rng.randint(1000000000, 1999999999)}"
        self.charge = f"{rng.randint(80, 4200)}.{rng.randint(0, 99):02d}"
        self.date = f"2024-{rng.randint(1, 12):02d}-{rng.randint(1, 28):02d}"
        self.claim = f"CLM{rng.randint(100000, 999999)}"

    @property
    def name(self) -> str:
        return f"{self.first} {self.last}"


def patients(seed: int, count: int = COUNT) -> list[Patient]:
    rng = random.Random(seed)
    return [Patient(rng, i) for i in range(count)]


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


# ── fax: pre-OCR line blocks (what Textract would return) ────────────────────

def fax_lines(p: Patient, kind: str) -> list[str]:
    head = {"referral": "REFERRAL REQUEST", "prior_auth": "PRIOR AUTHORIZATION REQUEST",
            "denial_eob": "EXPLANATION OF BENEFITS - CLAIM DENIED",
            "clinical_note": "PROGRESS NOTE", "eligibility": "ELIGIBILITY VERIFICATION"}[kind]
    lines = [head, f"Patient: {p.name}", f"DOB: {p.dob}", f"MRN: {p.mrn}",
             f"Payer: {p.payer_name} ({p.payer_id})", f"Provider NPI: {p.npi}",
             f"ICD-10: {', '.join(p.dx)}", f"CPT: {', '.join(p.cpt)}", f"Date of service: {p.date}"]
    if kind == "denial_eob":
        code, why = DENIAL[int(p.npi) % len(DENIAL)]
        lines += [f"Claim {p.claim} denied {code}: {why}", f"Billed amount: ${p.charge}",
                  "Appeal must be filed within 60 days of this notice."]
    elif kind == "prior_auth":
        lines += [f"Auth number: PA{p.npi[:7]}", "Status: PENDING REVIEW",
                  "Clinical justification attached on page 2."]
    elif kind == "referral":
        lines += ["Reason for referral: persistent symptoms, specialist evaluation requested."]
    elif kind == "clinical_note":
        lines += ["Assessment and plan: continue current therapy, follow up in 4 weeks."]
    else:
        lines += ["Coverage active. Copay $30. Deductible remaining $450."]
    return lines


def gen_fax(out: Path) -> None:
    kinds = ["referral", "prior_auth", "denial_eob", "clinical_note", "eligibility"]
    rng = random.Random(11)
    for i, p in enumerate(patients(1), 1):
        kind = kinds[i % len(kinds)]
        lines = fax_lines(p, kind)
        conf = round(rng.uniform(90, 99), 1)
        pages = [lines[: len(lines) // 2 + 1], lines[len(lines) // 2 + 1:]]
        defect = ""
        if i == 7:   # blurry scan -> below MIN_OCR_CONFIDENCE
            conf, defect = 41.5, "low_ocr_confidence"
        if i == 15:  # slightly degraded but still acceptable
            conf, defect = 72.0, "degraded_scan"
        if i == 21:  # near-empty page
            pages, defect = [["p.1"]], "too_short"
        blocks = [{"page": pn, "text": t, "confidence": round(conf + rng.uniform(-3, 1), 1)
                   if defect != "low_ocr_confidence" else conf}
                  for pn, pg in enumerate(pages, 1) for t in pg]
        doc = {"s3_key": f"fax/inbox/2024/fax-{i:03d}.pdf", "content_type": "application/pdf",
               "intended_type": kind, "defect": defect, "blocks": blocks}
        write(out / f"fax_{i:03d}.json", json.dumps(doc, indent=2) + "\n")


# ── HL7 v2 ────────────────────────────────────────────────────────────────────
# Three message types, cycled evenly across the 50 samples:
#   ADT^A08  registration/demographics update — no RCM document type covers this; it's meant
#            to fall through classification to human review (see classification._HL7_MESSAGES).
#   ORM^O01  order message — mapped to DocumentType.REFERRAL (an outbound specialist order).
#   DFT^P03  post detail financial transaction — mapped to DocumentType.CLAIM_837 (a charge post).
HL7_TRIGGERS = {"ADT": "A08", "ORM": "O01", "DFT": "P03"}
HL7_MESSAGE_TYPES = ["ADT", "ORM", "DFT"]


def gen_hl7(out: Path) -> None:
    for i, p in enumerate(patients(2, HL7_COUNT), 1):
        msg_type = HL7_MESSAGE_TYPES[(i - 1) % len(HL7_MESSAGE_TYPES)]
        ts = p.date.replace("-", "") + "1000"
        segs = [
            f"MSH|^~\\&|EPIC|MERCY|RCM|PLATFORM|20240{(i % 9) + 1}15100000||{msg_type}^{HL7_TRIGGERS[msg_type]}|"
            f"MSG{i:05d}|P|2.5",
            f"PID|1||{p.mrn}||{p.last.upper()}^{p.first.upper()}||{p.dob.replace('-', '')}|"
            f"{'F' if i % 2 else 'M'}|||{100 + i} MAIN ST^^AUSTIN^TX^78701",
        ]
        if msg_type == "ADT":
            segs.append(f"PV1|1|O|CLINIC^^^MERCY||||{p.npi}^PROVIDER^TEST")
        elif msg_type == "ORM":
            segs += [
                f"ORC|NW|ORD{i:05d}|PLC{i:05d}||SC||||{ts}|||{p.npi}^PROVIDER^TEST",
                f"OBR|1|ORD{i:05d}|PLC{i:05d}|REF^Specialist Referral^L|||{ts}",
                f"NTE|1|L|Referral to specialist for persistent symptoms, patient {p.name}.",
            ]
        else:  # DFT
            segs += [
                f"EVN|P03|{ts}",
                f"PV1|1|O|BILLING^^^MERCY||||{p.npi}^PROVIDER^TEST",
                f"FT1|1||{p.claim}|{p.date.replace('-', '')}|CG|{p.cpt[0]}^Procedure {p.cpt[0]}^C4|"
                f"{p.charge}|||||{p.npi}",
            ]
        segs += [
            f"IN1|1|PLAN{i:02d}|{p.payer_id}|{p.payer_name}",
            f"DG1|1|I10|{p.dx[0]}^Diagnosis {p.dx[0]}^I10",
            f"PR1|1|CPT4|{p.cpt[0]}^Procedure {p.cpt[0]}^C4|||{p.date.replace('-', '')}",
        ]
        if i == 9:   # no insurance segment
            segs = [s for s in segs if not s.startswith("IN1")]
        if i == 17:  # malformed diagnosis code
            segs = ["DG1|1|I10|BADCODE^Unknown^I10" if s.startswith("DG1") else s for s in segs]
        if i == 23:  # no procedure segment
            segs = [s for s in segs if not s.startswith("PR1")]
        write(out / f"hl7_{i:03d}.hl7", "\n".join(segs) + "\n")


# ── FHIR R4 ───────────────────────────────────────────────────────────────────

def gen_fhir(out: Path) -> None:
    for i, p in enumerate(patients(3), 1):
        bundle = {
            "resourceType": "Bundle", "type": "collection", "id": f"bundle-{i:03d}",
            "entry": [
                {"resource": {"resourceType": "Patient", "id": f"pat-{i}",
                              "name": [{"family": p.last, "given": [p.first]}],
                              "birthDate": p.dob, "identifier": [{"value": p.mrn}]}},
                {"resource": {"resourceType": "Coverage", "id": f"cov-{i}", "status": "active",
                              "payor": [{"identifier": {"value": p.payer_id},
                                         "display": p.payer_name}]}},
                {"resource": {"resourceType": "Claim", "id": f"clm-{i}", "status": "active",
                              "diagnosis": [{"sequence": n, "diagnosisCodeableConcept": {
                                  "coding": [{"system": "http://hl7.org/fhir/sid/icd-10-cm",
                                              "code": c}]}} for n, c in enumerate(p.dx, 1)],
                              "item": [{"sequence": n, "productOrService": {
                                  "coding": [{"system": "http://www.ama-assn.org/go/cpt",
                                              "code": c}]}} for n, c in enumerate(p.cpt, 1)],
                              "total": {"value": float(p.charge), "currency": "USD"}}},
            ],
        }
        if i == 5:   # no Coverage
            bundle["entry"].pop(1)
        if i == 12:  # empty bundle
            bundle["entry"] = []
        if i == 19:  # multiple given names, suspect CPT
            bundle["entry"][0]["resource"]["name"][0]["given"] = [p.first, "Q"]
            bundle["entry"][2]["resource"]["item"][0]["productOrService"]["coding"][0]["code"] = "9921"
        write(out / f"fhir_{i:03d}.json", json.dumps(bundle, indent=2) + "\n")


# ── EDI 837P ──────────────────────────────────────────────────────────────────

def gen_edi(out: Path) -> None:
    for i, p in enumerate(patients(4), 1):
        d = p.date.replace("-", "")
        hi = "*".join([f"HI*ABK:{p.dx[0].replace('.', '')}"] +
                      [f"ABF:{c.replace('.', '')}" for c in p.dx[1:]])
        sv = [f"SV1*HC:{c}*{float(p.charge) / len(p.cpt):.2f}*UN*1***1" for c in p.cpt]
        segs = [
            f"ISA*00*          *00*          *ZZ*SENDER{i:03d}      *ZZ*RCMPLATFORM    *{d[2:]}*1200*^*00501*{i:09d}*0*P*:",
            f"GS*HC*SENDER{i:03d}*RCMPLATFORM*{d}*1200*{i}*X*005010X222A1",
            f"ST*837*{i:04d}*005010X222A1",
            f"BHT*0019*00*{i:010d}*{d}*1200*CH",
            f"NM1*41*2*MERCY CLINIC*****46*{p.npi}",
            f"NM1*40*2*{p.payer_name.upper()}*****46*{p.payer_id}",
            f"NM1*85*2*MERCY CLINIC*****XX*{p.npi}",
            f"NM1*IL*1*{p.last.upper()}*{p.first.upper()}****MI*{p.mrn}",
            f"NM1*QC*1*{p.last.upper()}*{p.first.upper()}*A***MI*{p.mrn}",
            f"DMG*D8*{p.dob.replace('-', '')}*{'F' if i % 2 else 'M'}",
            f"REF*2U*{p.payer_id}",
            f"CLM*{p.claim}*{p.charge}***11:B:1*Y*A*Y*Y",
            hi, *sv, "SE*15*" + f"{i:04d}", f"GE*1*{i}", f"IEA*1*{i:09d}",
        ]
        if i == 4:   # no payer REF
            segs = [s for s in segs if not s.startswith("REF*2U")]
        if i == 14:  # no diagnosis
            segs = [s for s in segs if not s.startswith("HI*")]
        if i == 22:  # malformed procedure code
            segs = [s.replace(f"HC:{p.cpt[0]}", "HC:12") for s in segs]
        write(out / f"edi837_{i:03d}.edi", "~\n".join(segs) + "~\n")


# ── Webhook JSON ──────────────────────────────────────────────────────────────

def gen_webhook(out: Path) -> None:
    events = ["referral.created", "prior_auth.submitted", "claim.denied", "eligibility.checked",
              "note.uploaded"]
    for i, p in enumerate(patients(5), 1):
        ev = events[i % len(events)]
        body = {"event": ev, "event_id": f"evt-{i:05d}", "timestamp": f"{p.date}T09:{i:02d}:00Z",
                "patient": {"name": p.name, "dob": p.dob, "mrn": p.mrn},
                "payer": {"id": p.payer_id, "name": p.payer_name},
                "diagnosis_codes": p.dx, "procedure_codes": p.cpt,
                "provider_npi": p.npi, "claim_number": p.claim,
                "notes": f"{ev} for {p.name}; payer {p.payer_name}; "
                         f"ICD-10 {', '.join(p.dx)}; CPT {', '.join(p.cpt)}."}
        if ev == "claim.denied":
            code, why = DENIAL[i % len(DENIAL)]
            body["denial"] = {"reason_code": code, "reason": why, "appeal_by": "2024-12-31"}
        if ev == "prior_auth.submitted":
            body["auth_number"] = f"PA{p.npi[:7]}"
        headers = {"content-type": "application/json", "x-source-system": "partner-portal",
                   "x-signature": f"sha256=demo{i:04d}"}
        raw = json.dumps(body)
        if i == 8:   # empty body
            raw = ""
        if i == 18:  # truncated JSON
            raw = raw[:60]
        if i == 24:  # non-JSON content type
            headers["content-type"], raw = "text/plain", f"Ping from portal #{i}"
        write(out / f"webhook_{i:03d}.json",
              json.dumps({"headers": headers, "body": raw}, indent=2) + "\n")


GENERATORS = {"fax": gen_fax, "hl7v2": gen_hl7, "fhir_r4": gen_fhir,
              "edi837": gen_edi, "webhook": gen_webhook}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, default=ROOT)
    args = ap.parse_args()
    for name, fn in GENERATORS.items():
        d = args.out / name
        if d.exists():
            shutil.rmtree(d)
        fn(d)
        print(f"{name:8s} {len(list(d.iterdir()))} files -> {d}")


if __name__ == "__main__":
    main()
