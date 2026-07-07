"""Ordered mapping of extraction schema fields to the target Excel sheet columns.

The order of COLUMNS is the exact column order of the registry spreadsheet;
`to_tsv_line` produces one paste-ready row in that order.
"""

COLUMNS = [
    ("patient.kod_pacienta", "Kód pacienta"),
    ("patient.birth_number", "Rodné číslo"),
    ("patient.age", "Vek"),
    ("patient.sex", "Pohlavie"),
    ("procedure.date", "Dátum"),
    ("procedure.screening_type", "Typ skríningu"),
    ("anthropometry.height_cm", "Výška (cm)"),
    ("anthropometry.weight_kg", "Hmotnosť (kg)"),
    ("anthropometry.bmi", "BMI"),
    ("audit_c.q1", "AUDIT-C 1"),
    ("audit_c.q2", "AUDIT-C 2"),
    ("audit_c.q3", "AUDIT-C 3"),
    ("audit_c.total", "AUDIT-C spolu"),
    ("lifestyle.smoking", "Fajčenie"),
    ("lifestyle.meat_frequency", "Mäso (frekvencia)"),
    ("family_history.ra_crc_first_degree", "RA CRC 1. stupeň"),
    ("family_history.ra_crc_other", "RA CRC ostatní"),
    ("family_history.ra_polypy", "RA polypy"),
    ("medical_history.hypertension", "Hypertenzia"),
    ("medical_history.diabetes", "Diabetes"),
    ("medical_history.hyperlipidemia", "Hyperlipidémia"),
    ("medical_history.metabolic_syndrome", "Metabolický syndróm"),
    ("medical_history.ichs", "ICHS"),
    ("medical_history.prior_mi", "IM v anamnéze"),
    ("medical_history.ckd", "CKD"),
    ("medical_history.copd", "CHOCHP"),
    ("medical_history.oncology_history", "Onkologická anamnéza"),
    ("medical_history.chemotherapy", "Chemoterapia"),
    ("medications.nsaid_asa", "NSAID/ASA"),
    ("medications.anticoagulants", "Antikoagulanciá"),
    ("medications.hypolipidemic_drugs", "Hypolipidemiká"),
    ("findings.nalez", "Nález"),
    ("findings.polyp_ta_tva", "Polyp TA/TVA"),
    ("findings.polyp_count", "Počet polypov"),
    ("findings.nad_1cm", "Nad 1 cm"),
    ("findings.divertikuly", "Divertikuly"),
    ("histology.low_grade", "Low-grade"),
    ("histology.high_grade", "High-grade"),
    ("histology.ssl_without_dysplasia", "SSL bez dysplázie"),
    ("histology.ssl_with_dysplasia", "SSL s dyspláziou"),
    ("histology.carcinoma", "Karcinóm"),
    ("histology.stadium_ca", "Štádium CA"),
]


def get_value(data: dict, dotted_path: str):
    node = data
    for key in dotted_path.split("."):
        if not isinstance(node, dict):
            return None
        node = node.get(key)
    return node


def header_tsv() -> str:
    return "\t".join(name for _, name in COLUMNS)


def to_tsv_line(extracted: dict) -> str:
    return "\t".join(_cell(get_value(extracted, path)) for path, _ in COLUMNS)


def build_one_liner(extracted: dict) -> str:
    """Deterministic human summary for quick oversight — no LLM call."""
    parts = []
    sex = get_value(extracted, "patient.sex")
    age = get_value(extracted, "patient.age")
    if sex or age is not None:
        parts.append(f"{sex or '?'}/{age if age is not None else '?'}")
    code = get_value(extracted, "patient.kod_pacienta")
    if code:
        parts.append(f"kód {code}")
    date = get_value(extracted, "procedure.date")
    if date:
        parts.append(str(date))
    screening = get_value(extracted, "procedure.screening_type")
    if screening is not None:
        parts.append(f"skríning {screening}")
    nalez = get_value(extracted, "findings.nalez")
    if nalez is not None:
        parts.append(f"nález {nalez}")
    polyp_count = get_value(extracted, "findings.polyp_count")
    if polyp_count:
        big = " (≥1 cm)" if get_value(extracted, "findings.nad_1cm") else ""
        parts.append(f"polypy: {polyp_count}{big}")
    if get_value(extracted, "findings.divertikuly"):
        parts.append("divertikuly")

    histo = []
    if get_value(extracted, "histology.low_grade"):
        histo.append("LG")
    if get_value(extracted, "histology.high_grade"):
        histo.append("HG")
    if get_value(extracted, "histology.ssl_without_dysplasia") or get_value(
        extracted, "histology.ssl_with_dysplasia"
    ):
        histo.append("SSL")
    if get_value(extracted, "histology.carcinoma"):
        stadium = get_value(extracted, "histology.stadium_ca")
        histo.append(f"CA {stadium}" if stadium else "CA")
    if histo:
        parts.append("histo: " + "+".join(histo))

    return " · ".join(parts) if parts else "bez extrahovaných údajov"


def _cell(value) -> str:
    if value is None:
        return ""
    return str(value)
