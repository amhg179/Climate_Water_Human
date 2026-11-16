"""00_References/Literature_Review.xlsx — evidence extraction template from section 3.5."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from .report import write_excel

EVIDENCE_COLUMNS = ["Paper ID", "Year", "Study Region", "Water Type", "Climate Data", "Satellite", "Ground Truth",
                    "Human Data", "Model", "Fusion", "Validation", "Uncertainty", "Limitations"]

PAPERS = [
    ("10.34133/remotesensing.0049", 2023, "Recipes for the Derivation of Water Quality Parameters Using "
     "High-Spatial-Resolution Satellite Data", "Sentinel-2 / Landsat", "طرق اشتقاق Chl-a وTurbidity وTSS"),
    ("10.1002/tqem.70493", 2026, "Artificial Intelligence and Remote Sensing for Freshwater Quality Monitoring",
     "", "31 دراسة؛ التحقق المستقل والتعميم وعدم اليقين"),
    ("10.1016/j.watres.2026.126047", 2026, "Comparing AI-driven approaches for predicting river water quality",
     "", "71 دراسة؛ 83% في آسيا؛ نقص مجموعات الاختبار المستقلة"),
    ("10.1080/01431161.2026.2637851", 2026, "Sentinel-2 for chlorophyll-a water quality monitoring",
     "Sentinel-2", "122 دراسة؛ 10% فقط تجاوزت مستوى أدلة التحقق القوية"),
    ("10.1007/s43621-025-02317-z", 2025, "Multimodal Graph Neural Networks for Earth Observation and Sustainable "
     "Resource Management", "", "اختلاف الدقة والتواتر، Domain Shift، الوسائط المفقودة"),
]

SEARCH_STRINGS = [
    ("Search 1", '("climate change" OR "climate variability" OR "extreme weather" OR heatwave OR drought) AND '
     '("water quality" OR freshwater OR turbidity OR chlorophyll OR "water pollution") AND '
     '("multimodal learning" OR "data fusion" OR "multisource learning" OR Transformer OR "deep learning") AND '
     '("human health" OR "population exposure" OR disease OR mortality OR vulnerability)'),
    ("Search 2", '("remote sensing" OR satellite OR ERA5 OR "in situ monitoring") AND '
     '("water quality prediction" OR "water quality monitoring") AND '
     '("spatial transfer" OR generalization OR uncertainty OR "missing data")'),
]

DATABASES = ["Scopus", "Web of Science Core Collection", "IEEE Xplore", "PubMed", "ScienceDirect",
             "OpenAlex (exploratory)"]

FIELD_GUIDE = [
    ("Paper ID", "DOI"), ("Year", "سنة النشر"), ("Study Region", "المنطقة"),
    ("Water Type", "River / Lake / Reservoir / Coastal"), ("Climate Data", "نوع البيانات المناخية"),
    ("Satellite", "نوع المستشعر"), ("Ground Truth", "قياسات المياه الأرضية"), ("Human Data", "هل توجد بيانات بشرية؟"),
    ("Model", "RF / CNN / Transformer / GNN"), ("Fusion", "Early / Late / Cross-Attention"),
    ("Validation", "Random / Spatial / Temporal"), ("Uncertainty", "هل قيس عدم اليقين؟"),
    ("Limitations", "القيود التي حددها المؤلفون"),
]


def write_literature_review(out: Path) -> Path:
    evidence = pd.DataFrame([
        {**dict.fromkeys(EVIDENCE_COLUMNS, ""), "Paper ID": doi, "Year": year, "Satellite": sat,
         "Limitations": notes}
        for doi, year, _title, sat, notes in PAPERS
    ], columns=EVIDENCE_COLUMNS)
    titles = pd.DataFrame([(d, y, t) for d, y, t, _, _ in PAPERS], columns=["Paper ID", "Year", "Title"])
    titles["URL"] = "https://doi.org/" + titles["Paper ID"]
    return write_excel({
        "Evidence_Extraction": evidence,
        "Papers": titles,
        "Field_Guide": pd.DataFrame(FIELD_GUIDE, columns=["الحقل", "ما نسجله"]),
        "Search_Strings": pd.DataFrame(SEARCH_STRINGS, columns=["Query", "String"]),
        "Databases": pd.DataFrame({"Database": DATABASES}),
    }, out)
