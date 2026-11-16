# Climate_Water_Human

**A Global Explainable Multimodal Learning Framework for Climate-Driven Freshwater Quality Changes and Human Health Vulnerability Assessment**

This repository implements the first executable step of the research plan: the **GEMStat V3 data audit** (section 15 of the draft:
*"أريد أن نبدأ بهذه الخطوة قبل أي نموذج أو تنزيل ضخم للصور"*). It downloads the UNEP GEMS/Water Global Freshwater Quality
Archive v3 from Zenodo, verifies it, cleans and harmonises the ground-truth measurements, and produces the audit
outputs (HTML + Excel report, maps, inventories, quality-control tables) in the folder layout of section 11.1.

| Source | Record |
| --- | --- |
| GEMStat V3 (GFQA v3) | Zenodo [10.5281/zenodo.18459694](https://doi.org/10.5281/zenodo.18459694) — `GFQA_v3.zip`, MD5 `00f3ea19ce529753977eb3aeb08fbc47`, CC BY 4.0 |

## Quick start

```bash
pip install -e ".[dev]"          # Python ≥ 3.10
python -m climate_water_human    # or: cwh-audit
pytest -q && ruff check src tests
```

Options: `--zip-path GFQA_v3.zip` (use an archive you already downloaded), `--extracted-dir DIR`,
`--cdp-url http://localhost:9222` (download through a running Chrome if Zenodo rate-limits scripted clients — needs
`pip install -e ".[browser]"`), `--offline-basemap`.

The full run over all 80 measurement files (51 M rows) takes about 2 minutes and under 3 GB RAM: CSVs are read with
DuckDB, staged as typed Parquet, and only aggregated results are loaded into pandas.

## Pipeline (draft sections in brackets)

1. **Acquisition** — Zenodo download, MD5 verification, extraction, CSV discovery (§15 steps 1–3).
2. **Metadata** — station / parameter / method metadata (cp1252-encoded), duplicate station rows removed, coordinate
   validation, `Country_ID`, continent, `Waterbody_ID` → `05_Integrated_Dataset/Station_Waterbody_Master.csv`
   (`Station_ID · Waterbody_ID · Coordinates · Water_Type · Country_ID`, §9).
3. **Staging** — every measurement CSV → typed Parquet (`01_Raw_Data/GEMStat/parquet/`).
4. **Preprocessing** (§7.1) — the ten target variables of §2.B; standard names; unit conversion only where the
   relation is known (Chl-a mg/l→µg/L ×1000, E. coli 1/ml→CFU/100 mL ×100; Turbidity in JCU is *not* converted to NTU;
   nitrate as N is never mixed with nitrate as NO₃); date and coordinate checks; duplicate removal; GEMStat
   *Suspect/Contamination* flags and physically implausible values removed; every step logged →
   `03_Processed/Water_Quality/Water_Quality_Samples.parquet` with the §7.1 schema
   `Station_ID | Date | Parameter | Value | Unit | Quality` (+ provenance columns).
5. **Audit** (§15) — stations and countries, statistics for all 621 variables, measurements per year, country coverage,
   stations with ≥ 10 years of data, Sentinel-2 / ERA5-Land matchability, 2015–2021 and 2000–2024 windows (§5).
6. **Quality control** (§8.1) — the ten data-quality tests, missing data, quality flags, multi-unit parameters.
7. **Reports** — `09_Results/01_Global_Water_Quality_Data_Audit.{html,xlsx}`, static and interactive station maps,
   `02_Metadata/data_source_inventory.csv` (§6.3), Dataset Readiness Checklist (§13),
   `00_References/Literature_Review.xlsx` evidence-extraction template (§3.5).

## Results of the current run (GEMStat V3)

| Metric | Value |
| --- | --- |
| Measurements (all variables) | 51,157,266 |
| Variables with data | 621 |
| Stations / countries | 22,946 / 42 |
| Years | 1906–2024 |
| Clean target-variable measurements | 4,770,792 at 22,009 stations |
| Stations with ≥ 10 years of target data | 3,842 |
| Sentinel-2 matchable / ERA5-Land matchable stations | 14,291 / 22,009 |

| Parameter | Unit | Measurements | Stations |
| --- | --- | ---: | ---: |
| pH | pH units | 932,301 | 20,800 |
| Water Temperature | °C | 837,190 | 18,217 |
| Nitrate (as N) | mg/L as N | 796,121 | 20,010 |
| Conductivity | µS/cm | 737,585 | 19,974 |
| DO | mg/L | 624,475 | 16,909 |
| TSS | mg/L | 336,116 | 11,151 |
| Turbidity | NTU | 202,573 | 7,122 |
| Chlorophyll-a | µg/L | 112,044 | 4,957 |
| CDOM | Absorbance (340 nm) | 100,489 | 5,427 |
| E. coli | CFU/100 mL | 91,898 | 3,237 |

*Sentinel-2 matchable* = surface-water station with valid coordinates and at least one optical/thermal target sample
(Chl-a, Turbidity, TSS, Temperature, CDOM) after 2015-06-23; *ERA5-Land matchable* = valid coordinates and samples after
1950. These are candidates only — actual matching needs scene download, cloud and water masking (next steps).

## Layout

```
00_References/        Literature_Review.xlsx, Research_Gap.md
01_Raw_Data/          GEMStat/ (downloaded, git-ignored), WQP/, Sentinel2/, Landsat/, ERA5/, CHIRPS/, WorldPop/, JMP/, Health/
02_Metadata/          cleaned metadata, data_source_inventory.csv, gemstat_variable_inventory.csv, CSV file list
03_Processed/         Water_Quality/ (clean Parquet, summary, cleaning log), Satellite/, Climate/, Population/, Health/
04_Feature_Store/ … 08_Models/   reserved for the next notebooks (§11)
05_Integrated_Dataset/ Station_Waterbody_Master.csv
06_Quality_Control/   data-quality tests, missing data, quality flags, staging log
09_Results/           HTML/Excel audit report, maps, charts, long-series and matchability tables, readiness checklist
notebooks/            01_Global_Water_Quality_Data_Audit.ipynb
src/climate_water_human/  acquisition, io_utils, metadata, staging, preprocessing, audit, quality, inventory, maps, report, pipeline
tests/                pytest suite on a synthetic GEMStat-format archive
```

Raw data (`01_Raw_Data/`) is not committed; rerun the pipeline to recreate it. All other outputs are committed.

## Next steps (draft §15.1)

Water Quality Portal for the USA → Sentinel-2 / Landsat around the matchable stations → ERA5-Land / CHIRPS →
WorldPop / JMP / WHO / GBD → Station–Climate–Satellite–Population table → baseline models.
