from datetime import date

import duckdb
import pandas as pd
import pytest

from climate_water_human import acquisition
from climate_water_human.pipeline import run_pipeline
from climate_water_human.preprocessing import OUTPUT_COLUMNS


@pytest.fixture()
def result(mini_archive, tmp_path):
    return run_pipeline(root=tmp_path / "project", extracted_dir=mini_archive, today=date(2024, 12, 31),
                        offline_basemap=True)


def test_discover_csv_files(mini_archive):
    files = acquisition.discover_csv_files(mini_archive)
    assert len(files) == 7
    assert (files["Kind"] == "metadata").sum() == 3


def test_md5_and_zip_roundtrip(mini_archive, tmp_path):
    import shutil

    archive = shutil.make_archive(str(tmp_path / "GFQA_v3"), "zip", mini_archive)
    digest = acquisition.md5sum(archive)
    dest = acquisition.download_gemstat(tmp_path / "raw", zip_path=archive, expected_md5=digest)
    out = acquisition.extract_archive(dest, tmp_path / "ex")
    assert (out / "pH.csv").exists()
    with pytest.raises(ValueError):
        acquisition.download_gemstat(tmp_path / "raw2", zip_path=archive, expected_md5="0" * 32)


def test_outputs_exist(result):
    for key in ["water_quality_samples", "station_master", "inventory", "excel_report", "html_report",
                "interactive_map", "literature_review"]:
        assert result.outputs[key].exists(), key


def test_clean_table_schema_and_rules(result):
    df = duckdb.sql(f"SELECT * FROM read_parquet('{result.outputs['water_quality_samples']}')").df()
    assert list(df.columns[:6]) == OUTPUT_COLUMNS
    assert not df.duplicated(["Station_ID", "Date", "Parameter", "Value"]).any()
    assert set(df["Station_ID"]) <= {"ARG00003", "DEU00001", "IND00007"}
    assert df["Date"].min() >= pd.Timestamp("1900-01-01")
    ph = df[df["Parameter"] == "pH"]
    assert ph["Value"].between(0, 14).all()
    chl = df[df["Parameter"] == "Chlorophyll-a"].sort_values("Date")
    assert (chl["Unit"] == "µg/L").all()
    assert chl["Value"].round(6).tolist()[:2] == [5.5, 4.0]
    turb = df[df["Parameter"] == "Turbidity"]
    assert set(turb["Unit"]) == {"NTU"}
    assert "Chloride" not in set(df["Parameter"])


def test_cleaning_log_counts(result):
    log = result.cleaning_log.set_index("Step")
    assert log["Rows_Removed"].sum() == log["Rows_Before"].iloc[0] - log["Rows_After"].iloc[-1]


def test_reports(result):
    html = result.outputs["html_report"].read_text(encoding="utf-8")
    for heading in ["حساب عدد المحطات والدول", "Sentinel-2", "ERA5-Land", "Station_ID | Date | Parameter"]:
        assert heading in html
    sheets = pd.ExcelFile(result.outputs["excel_report"]).sheet_names
    assert {"Overview", "Sentinel2_ERA5_Match", "Long_Time_Series", "Readiness_Checklist"} <= set(sheets)
    long_series = pd.read_excel(result.outputs["excel_report"], sheet_name="Long_Time_Series")
    assert {"ARG00003", "DEU00001"} <= set(long_series["Station_ID"])
    match = pd.read_excel(result.outputs["excel_report"], sheet_name="Sentinel2_ERA5_Match").set_index("Station_ID")
    assert bool(match.loc["DEU00001", "Both_Matchable"])
    assert not bool(match.loc["IND00007", "Sentinel2_Matchable"])
    inv = pd.read_csv(result.outputs["inventory"])
    assert list(inv.columns[:4]) == ["Source", "Variable", "Start", "End"]
