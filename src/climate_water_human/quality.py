"""Section 8.1 — data-quality tests table and Section 13 readiness checklist."""

from __future__ import annotations

import pandas as pd


def _log_removed(cleaning_log: pd.DataFrame, keyword: str) -> int:
    rows = cleaning_log[cleaning_log["Action"].str.contains(keyword, case=False, regex=False)]
    return int(rows["Rows_Removed"].sum())


def quality_tests(
    stations: pd.DataFrame,
    station_stats: dict,
    missing: pd.DataFrame,
    units: pd.DataFrame,
    quality_dist: pd.DataFrame,
    cleaning_log: pd.DataFrame,
    countries: pd.DataFrame,
) -> pd.DataFrame:
    """Build the 10 tests of section 8.1 with a measured result and a status."""
    total = int(missing["Total_Rows"].iloc[0]) if len(missing) else 0
    miss = dict(zip(missing["Column"], missing["Missing_Percent"]))
    invalid_coords = int((~stations["Coordinates_Valid"]).sum())
    dup_station = station_stats.get("exact_duplicates_removed", 0) + station_stats.get(
        "conflicting_duplicate_ids_removed", 0)
    dup_samples = _log_removed(cleaning_log, "duplicate")
    outliers = _log_removed(cleaning_log, "implausible")
    bad_dates = _log_removed(cleaning_log, "dates")
    bad_units = _log_removed(cleaning_log, "units without")
    good_share = quality_dist.loc[quality_dist["Data_Quality"].isin(["Good", "Fair"]), "Percent"].sum()
    suspect_share = quality_dist.loc[quality_dist["Data_Quality"].isin(
        ["Suspect", "Contamination", "Pending review"]), "Percent"].sum()
    st = countries.dropna(subset=["Measurements"]).sort_values("Measurements", ascending=False)
    top3 = 100 * st["Measurements"].head(3).sum() / max(st["Measurements"].sum(), 1)
    europe = 100 * (stations["Continent"] == "Europe").mean()

    rows = [
        ("Completeness", "نسبة البيانات المفقودة",
         f"Missing Value: {miss.get('Value', 0)}%, Sample_Date: {miss.get('Sample_Date', 0)}%, "
         f"Depth: {miss.get('Depth', 0)}% of {total:,} rows",
         "Pass" if miss.get("Value", 0) < 5 else "Warning"),
        ("Consistency", "اتساق الوحدات",
         f"{len(units)} parameters reported in >1 unit; {bad_units:,} target samples removed because "
         "their unit has no known conversion",
         "Pass" if bad_units == 0 else "Warning"),
        ("Spatial Accuracy", "صحة الإحداثيات",
         f"{invalid_coords} of {len(stations):,} stations with missing/invalid coordinates",
         "Pass" if invalid_coords == 0 else "Warning"),
        ("Temporal Accuracy", "صحة التواريخ",
         f"{bad_dates:,} target samples with unparseable/out-of-range dates removed",
         "Pass" if bad_dates == 0 else "Warning"),
        ("Duplicates", "التكرار",
         f"{dup_station} duplicate station-metadata rows; {dup_samples:,} duplicate target samples removed",
         "Pass" if dup_samples == 0 else "Warning"),
        ("Outliers", "القيم غير المنطقية",
         f"{outliers:,} physically implausible target values removed", "Pass" if outliers == 0 else "Warning"),
        ("Sensor Quality", "جودة المشاهد الفضائية",
         "Satellite scenes are not acquired at this stage (acquisition step 3)", "Pending"),
        ("Label Quality", "موثوقية القياسات الأرضية",
         f"Good/Fair: {good_share:.2f}%; Suspect/Contamination/Pending review: {suspect_share:.2f}%",
         "Pass" if suspect_share < 20 else "Warning"),
        ("Cross-source Agreement", "التوافق بين مصادر القياس",
         "Requires the Water Quality Portal (acquisition step 2) as a second source", "Pending"),
        ("Coverage Bias", "التحيز الجغرافي في توزيع البيانات",
         f"{europe:.1f}% of stations are in Europe; top-3 countries hold {top3:.1f}% of measurements",
         "Warning" if europe > 50 or top3 > 50 else "Pass"),
    ]
    return pd.DataFrame(rows, columns=["الاختبار", "ما الذي نتحقق منه؟", "Result", "Status"])


CHECKLIST_ITEMS = (
    "تم تنزيل GEMStat V3 وفهم Metadata",
    "تم تحديد محطات المياه ذات القياسات المناسبة",
    "تم تحديد متغيرات جودة المياه المستهدفة",
    "تم تحديد المشاهد الفضائية المتزامنة مع القياسات الأرضية",
    "تم تنزيل بيانات المناخ المتوافقة زمنيًا ومكانيًا",
    "تم تحديد التغطية البشرية والصحية الفعلية",
    "تم توحيد الوحدات والتواريخ والإحداثيات",
    "تم إعداد تقرير Missing Data وData Quality",
    "تم تحديد مجموعات Train وValidation وIndependent Test",
    "تم التأكد من عدم وجود Data Leakage",
)


def readiness_checklist(n_stations_clean: int, n_targets: int, n_s2: int, n_era5: int) -> pd.DataFrame:
    """Section 13 — Dataset Readiness Checklist with the evidence produced by this pipeline."""
    status = [
        (True, "Archive MD5 verified; station/parameter/method metadata parsed"),
        (n_stations_clean > 0, f"{n_stations_clean:,} stations with clean target-variable measurements"),
        (n_targets > 0, f"{n_targets} target variables (section 2.B) harmonised"),
        (False, f"{n_s2:,} candidate stations for Sentinel-2 matching identified; scenes not yet downloaded"),
        (False, f"{n_era5:,} candidate stations for ERA5-Land extraction identified; climate data not yet downloaded"),
        (False, "WorldPop / JMP / WHO / GBD not yet processed"),
        (True, "Units, dates and coordinates standardised for GEMStat (cleaning log)"),
        (True, "Missing-data and data-quality reports generated (06_Quality_Control)"),
        (False, "Pending — after multimodal integration"),
        (False, "Pending — after Train/Validation/Test design"),
    ]
    df = pd.DataFrame({
        "#": range(1, len(CHECKLIST_ITEMS) + 1),
        "Item": CHECKLIST_ITEMS,
        "Done": ["✔" if s else "✘" for s, _ in status],
        "Evidence": [e for _, e in status],
    })
    return df
