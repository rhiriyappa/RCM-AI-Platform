"""classification/training_data.py — labelled seed corpus for EmbeddingClassifier."""
from contracts.schemas import DocumentType

SEED_CORPUS: list[tuple[str, str]] = [
    ("Claim denied. CO-4: procedure inconsistent with modifier. RARC N56. EOB enclosed.", DocumentType.DENIAL_EOB),
    ("Explanation of Benefits. CO-11 diagnosis inconsistent with procedure. PR-1 deductible $350.", DocumentType.DENIAL_EOB),
    ("Service denied as not medically necessary. CO-50. Appeal within 90 days.", DocumentType.DENIAL_EOB),
    ("EOB — claim adjustment. CO-45 contractual adjustment $120. Remark MA01.", DocumentType.DENIAL_EOB),
    ("Your claim for CPT 99215 has been denied. CO-97 bundling applies.", DocumentType.DENIAL_EOB),

    ("Prior authorization request for lumbar spinal fusion CPT 22612. Diagnosis M51.16. Medically necessary.", DocumentType.PRIOR_AUTH),
    ("Pre-certification request for Humira 40mg biweekly. Refractory rheumatoid arthritis.", DocumentType.PRIOR_AUTH),
    ("Authorization request for inpatient psychiatric admission. Patient is danger to self.", DocumentType.PRIOR_AUTH),
    ("Utilization review request. MRI lumbar spine without contrast. Radiculopathy.", DocumentType.PRIOR_AUTH),
    ("Pre-auth for bariatric surgery. BMI 42. Six-month supervised weight loss complete.", DocumentType.PRIOR_AUTH),

    ("I am referring this patient to orthopedic surgery for chronic low back pain.", DocumentType.REFERRAL),
    ("Referral to cardiology for evaluation of chest pain and dyspnea on exertion.", DocumentType.REFERRAL),
    ("Patient referred to physical therapy for post-surgical rehabilitation. 12 visits approved.", DocumentType.REFERRAL),
    ("Please see this patient for neurology consultation. Focal seizure episodes.", DocumentType.REFERRAL),
    ("Outpatient referral to wound care clinic for non-healing diabetic foot ulcer.", DocumentType.REFERRAL),

    ("837P Professional Claim. NPI 1234567890. CPT 99213. Diagnosis M54.5. Place of service 11.", DocumentType.CLAIM_837),
    ("CMS-1500 claim. Patient Johnson Robert. Service dates 02/01/2024. CPT 99233. ICD J18.9.", DocumentType.CLAIM_837),
    ("837I Institutional claim. UB-04 form. Revenue code 0450. DRG 470. Admission 03/10/2024.", DocumentType.CLAIM_837),

    ("SOAP Note. Chief Complaint: Low back pain. HPI: 45yo male acute onset LBP. Assessment: lumbar strain.", DocumentType.CLINICAL_NOTE),
    ("Discharge Summary. Patient admitted for COPD exacerbation. Treated with IV steroids.", DocumentType.CLINICAL_NOTE),
    ("Progress Note. Follow-up Type 2 DM. HbA1c 8.1%. Continue metformin 1000mg BID.", DocumentType.CLINICAL_NOTE),
    ("History of present illness: patient presents with three weeks of bilateral knee pain.", DocumentType.CLINICAL_NOTE),

    ("270 Eligibility Response. Member XY123456. Plan Blue Choice PPO. Deductible $1500 met $450.", DocumentType.ELIGIBILITY),
    ("Benefits Verification. Coverage confirmed outpatient services. Co-pay $35. OOP max $6000.", DocumentType.ELIGIBILITY),
    ("271 Eligibility Response. Subscriber Johnson Robert DOB 1965-08-22. Active coverage confirmed.", DocumentType.ELIGIBILITY),
]


def get_training_texts_and_labels() -> tuple[list[str], list[str]]:
    return [t for t, _ in SEED_CORPUS], [lbl for _, lbl in SEED_CORPUS]
