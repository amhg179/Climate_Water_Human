"""End-to-end pipeline: download → extract → clean → audit → reports."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import duckdb
import pandas as pd

from . import acquisition, config, maps, metadata, preprocessing, quality, references, report, staging
from .audit import GEMStatAudit
from .config import ProjectPaths
from .inventory import data_source_inventory, gemstat_variable_inventory

log = logging.getLogger(__name__)


@dataclass
class PipelineResult:
    overview: pd.DataFrame
    clean_summary: pd.DataFrame
    cleaning_log: pd.DataFrame
    readiness: pd.DataFrame
    outputs: dict[str, Path]


def run_pipeline(
    root: Path | None = None,
    zip_path: Path | None = None,
    extracted_dir: Path | None = None,
    cdp_url: str | None = None,
    expected_md5: str = config.GEMSTAT_ARCHIVE_MD5,
    today: date | None = None,
    offline_basemap: bool = False,
) -> PipelineResult:
    paths = ProjectPaths(root or config.PROJECT_ROOT)
    paths.create()
    outputs: dict[str, Path] = {}

    # 1–2. Download and extract GEMStat V3
    if extracted_dir is None:
        archive = acquisition.download_gemstat(paths.raw_gemstat, zip_path=zip_path, cdp_url=cdp_url,
                                               expected_md5=expected_md5)
        extracted_dir = acquisition.extract_archive(archive, paths.gemstat_extracted)
        archive_info = {"name": archive.name, "size_mb": round(archive.stat().st_size / 1e6, 1),
                        "md5": acquisition.md5sum(archive)}
    else:
        archive_info = {"name": Path(extracted_dir).name, "size_mb": "-", "md5": "-"}
    extracted_dir = Path(extracted_dir)
    log.info("Using extracted archive at %s", extracted_dir)

    # 3. Discover CSV files
    csv_files = acquisition.discover_csv_files(extracted_dir)
    if csv_files.empty:
        raise FileNotFoundError(f"No CSV files found in {extracted_dir}")
    csv_files.to_csv(paths.metadata / "gemstat_csv_files.csv", index=False)
    measurement_files = [extracted_dir / p for p, k in zip(csv_files["Path"], csv_files["Kind"]) if k == "measurements"]
    meta_paths = {Path(p).name: extracted_dir / p for p in csv_files.loc[csv_files["Kind"] == "metadata", "Path"]}
    missing = [m for m in config.METADATA_FILES if m not in meta_paths]
    if missing:
        raise FileNotFoundError(f"Missing metadata files: {missing}")

    # 4. Metadata
    stations, station_stats = metadata.load_station_metadata(meta_paths[config.STATION_METADATA_FILE])
    parameters = metadata.load_parameter_metadata(meta_paths[config.PARAMETER_METADATA_FILE])
    methods = metadata.load_methods_metadata(meta_paths[config.METHODS_METADATA_FILE])
    stations.to_csv(paths.metadata / "GEMStat_station_metadata_clean.csv", index=False, encoding="utf-8")
    parameters.to_csv(paths.metadata / "GEMStat_parameter_metadata_clean.csv", index=False, encoding="utf-8")
    methods.to_csv(paths.metadata / "GEMStat_methods_metadata_clean.csv", index=False, encoding="utf-8")
    master = metadata.station_master(stations)
    outputs["station_master"] = paths.integrated / "Station_Waterbody_Master.csv"
    master.to_csv(outputs["station_master"], index=False, encoding="utf-8")

    # Typed Parquet staging of every measurement file
    staging_log = staging.stage_measurements(measurement_files, paths.gemstat_staging)
    staging_log.to_csv(paths.quality_control / "staging_log.csv", index=False)
    staging_glob = (paths.gemstat_staging / "*.parquet").as_posix()

    # Section 7.1 preprocessing
    outputs["water_quality_samples"] = paths.processed_water_quality / "Water_Quality_Samples.parquet"
    cleaning_log, clean_summary = preprocessing.preprocess_water_quality(
        staging_glob, stations, parameters, outputs["water_quality_samples"], today=today)
    cleaning_log.to_csv(paths.processed_water_quality / "cleaning_log.csv", index=False, encoding="utf-8")
    clean_summary.to_csv(paths.processed_water_quality / "Water_Quality_Summary.csv", index=False)
    con = duckdb.connect()
    sample_rows = con.execute(
        f"SELECT * FROM read_parquet('{outputs['water_quality_samples'].as_posix()}') "
        "WHERE Quality = 'Valid' USING SAMPLE 12 ROWS (reservoir, 42) ORDER BY Station_ID, Date, Parameter"
    ).df()
    con.close()

    # Section 15 audit
    audit = GEMStatAudit(staging_glob, outputs["water_quality_samples"], stations, parameters)
    overview = audit.overview(len(measurement_files))
    water_types = audit.stations_by_water_type()
    variables = audit.variable_statistics()
    per_year = audit.measurements_per_year()
    target_per_year = audit.target_measurements_per_year()
    countries = audit.country_coverage()
    long_series = audit.long_time_series()
    matchability = audit.satellite_climate_matchability()
    windows = audit.window_coverage()
    quality_dist = audit.data_quality_distribution()
    missing_data = audit.missing_data()
    units = audit.units_per_parameter()
    audit.close()

    # Section 8.1 / 13
    qtests = quality.quality_tests(stations, station_stats, missing_data, units, quality_dist, cleaning_log, countries)
    n_s2 = int(matchability["Sentinel2_Matchable"].sum())
    n_era5 = int(matchability["ERA5_Land_Matchable"].sum())
    readiness = quality.readiness_checklist(len(matchability), len(clean_summary), n_s2, n_era5)
    readiness_score = int((readiness["Done"] == "✔").sum())

    qc = paths.quality_control
    qtests.to_csv(qc / "data_quality_tests.csv", index=False, encoding="utf-8")
    missing_data.to_csv(qc / "missing_data_report.csv", index=False)
    quality_dist.to_csv(qc / "data_quality_flags.csv", index=False)
    units.to_csv(qc / "parameters_with_multiple_units.csv", index=False)
    json.dump(station_stats, open(qc / "station_metadata_checks.json", "w"), indent=2)

    # Section 6.3 inventory
    inventory = data_source_inventory({"GEMStat"})
    outputs["inventory"] = paths.metadata / "data_source_inventory.csv"
    inventory.to_csv(outputs["inventory"], index=False, encoding="utf-8")
    gemstat_variable_inventory(clean_summary).to_csv(paths.metadata / "gemstat_variable_inventory.csv", index=False,
                                                     encoding="utf-8")

    # Figures and maps
    res = paths.results
    land = None if offline_basemap else maps.load_land(paths.metadata / "basemap" / "ne_110m_land.geojson")
    both = matchability.loc[matchability["Both_Matchable"], "Station_ID"]
    figures = {
        "map": maps.static_station_map(stations, res / "station_map.png", land),
        "match_map": maps.static_station_map(stations, res / "station_map_sentinel2_era5.png", land, highlight=both,
                                             title="Stations matchable with Sentinel-2 and ERA5-Land"),
        "per_year": maps.per_year_chart(per_year, res / "measurements_per_year.png"),
        "target_per_year": maps.target_per_year_chart(target_per_year, res / "target_variables_per_year.png"),
        "countries": maps.country_chart(countries, res / "stations_per_country.png"),
    }
    outputs["interactive_map"] = maps.interactive_station_map(stations, res / "station_map.html")

    long_series.to_csv(res / "long_time_series_stations.csv", index=False, encoding="utf-8")
    matchability.to_csv(res / "sentinel2_era5_matchable_stations.csv", index=False, encoding="utf-8")
    readiness.to_csv(res / "Dataset_Readiness_Checklist.csv", index=False, encoding="utf-8")

    match_counts = {"s2": n_s2, "era5": n_era5, "both": int(matchability["Both_Matchable"].sum()),
                    "s2_samples": int(matchability["S2_Optical_Samples"].sum())}
    sheets = {
        "Overview": overview, "Water_Types": water_types, "Target_Variables": clean_summary,
        "Time_Windows": windows, "All_Variables": variables, "Per_Year": per_year,
        "Target_Per_Year": target_per_year, "Countries": countries, "Long_Time_Series": long_series,
        "Sentinel2_ERA5_Match": matchability, "Quality_Tests": qtests, "Missing_Data": missing_data,
        "Data_Quality_Flags": quality_dist, "Multiple_Units": units, "Cleaning_Log": cleaning_log,
        "Staging_Log": staging_log, "Data_Source_Inventory": inventory, "Readiness_Checklist": readiness,
        "CSV_Files": csv_files,
    }
    outputs["excel_report"] = report.write_excel(sheets, res / "01_Global_Water_Quality_Data_Audit.xlsx")
    outputs["html_report"] = report.write_html({
        "archive": archive_info,
        "csv_counts": {"total": len(csv_files), "measurements": len(measurement_files),
                       "metadata": len(meta_paths)},
        "overview": overview, "water_types": water_types, "variables": variables, "countries": countries,
        "long_series": long_series, "matchability": matchability, "match_counts": match_counts,
        "windows": windows, "clean_summary": clean_summary, "sample_rows": sample_rows,
        "quality": qtests, "missing": missing_data, "quality_dist": quality_dist, "cleaning_log": cleaning_log,
        "inventory": inventory, "readiness": readiness, "readiness_score": readiness_score, "csv_files": csv_files,
    }, figures, res / "01_Global_Water_Quality_Data_Audit.html")

    outputs["literature_review"] = references.write_literature_review(paths.references / "Literature_Review.xlsx")
    log.info("Pipeline finished: %s", {k: str(v) for k, v in outputs.items()})
    return PipelineResult(overview, clean_summary, cleaning_log, readiness, outputs)
