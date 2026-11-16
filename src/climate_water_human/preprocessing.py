"""Section 7.1 — GEMStat preprocessing into the long ``Water_Quality_Samples`` table.

Output columns (exactly as in the draft):
``Station_ID | Date | Parameter | Value | Unit | Quality``
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import duckdb
import pandas as pd

from . import config

OUTPUT_COLUMNS = ["Station_ID", "Date", "Parameter", "Value", "Unit", "Quality"]


def _rules_frame() -> pd.DataFrame:
    rows = []
    for p in config.TARGET_PARAMETERS:
        for code in p.codes:
            for unit, factor in p.unit_factors.items():
                rows.append({
                    "Parameter_Code": code, "Unit_Raw": unit, "Factor": factor,
                    "Parameter": p.name, "Unit_Std": p.unit,
                    "Min_Valid": p.valid_range[0], "Max_Valid": p.valid_range[1],
                })
    return pd.DataFrame(rows)


def _target_codes_frame() -> pd.DataFrame:
    return pd.DataFrame({"Parameter_Code": list(config.CODE_TO_TARGET)})


class _Logger:
    def __init__(self, con: duckdb.DuckDBPyConnection):
        self.con = con
        self.rows: list[dict] = []

    def count(self) -> int:
        return self.con.execute("SELECT count(*) FROM wq").fetchone()[0]

    def step(self, number: int, task: str, action: str, sql: str | None = None) -> None:
        before = self.count()
        if sql:
            self.con.execute(sql)
        after = self.count()
        self.rows.append({
            "Step": number, "Task": task, "Action": action,
            "Rows_Before": before, "Rows_Removed": before - after, "Rows_After": after,
        })


def preprocess_water_quality(
    staging_glob: str,
    stations: pd.DataFrame,
    parameters: pd.DataFrame,
    out_path: Path,
    today: date | None = None,
    memory_limit: str = "3GB",
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Run the 10 tasks of section 7.1 and write ``out_path`` (Parquet).

    Returns the cleaning log and a per-parameter summary of the clean table.
    """
    today = today or date.today()
    con = duckdb.connect()
    con.execute(f"SET memory_limit='{memory_limit}'; SET preserve_insertion_order=false")
    con.register("rules", _rules_frame())
    con.register("target_codes", _target_codes_frame())
    con.register("stations_df", stations[["Station_ID", "Coordinates_Valid"]])
    con.register("params_df", parameters[["Parameter_Code"]])
    log = _Logger(con)

    con.execute(f"""
        CREATE TABLE wq AS
        SELECT s.* FROM read_parquet('{staging_glob}') s
        JOIN target_codes t USING (Parameter_Code)
    """)
    total_raw = con.execute(f"SELECT count(*) FROM read_parquet('{staging_glob}')").fetchone()[0]
    log.rows.append({"Step": 1, "Task": "قراءة جميع ملفات القياسات", "Action":
                     f"Read {total_raw:,} measurements from all files; kept the target variables of section 2.B",
                     "Rows_Before": total_raw, "Rows_Removed": total_raw - log.count(), "Rows_After": log.count()})

    log.step(2, "قراءة Metadata الخاصة بالمحطات", "Removed samples whose station is absent from station metadata",
             "DELETE FROM wq WHERE Station_ID NOT IN (SELECT Station_ID FROM stations_df)")
    log.step(3, "قراءة Metadata الخاصة بالمتغيرات",
             "Removed samples whose parameter code is absent from parameter metadata",
             "DELETE FROM wq WHERE Parameter_Code NOT IN (SELECT Parameter_Code FROM params_df)")

    con.execute("""
        CREATE TABLE wq2 AS
        SELECT w.*, r.Parameter, r.Unit_Std, r.Factor, r.Min_Valid, r.Max_Valid
        FROM wq w LEFT JOIN rules r ON w.Parameter_Code = r.Parameter_Code AND w.Unit = r.Unit_Raw
    """)
    con.execute("DROP TABLE wq; ALTER TABLE wq2 RENAME TO wq")
    log.step(4, "توحيد أسماء المتغيرات",
             "Mapped GEMStat parameter codes to standard names (e.g. Chl-a → Chlorophyll-a)")
    log.step(5, "توحيد الوحدات",
             "Converted to standard units (Chl-a mg/l→µg/L ×1000, E. coli 1/ml→CFU/100 mL ×100); "
             "removed units without a known conversion (e.g. Turbidity JCU)",
             "DELETE FROM wq WHERE Factor IS NULL")
    con.execute("UPDATE wq SET Value = Value * Factor")

    log.step(6, "توحيد التواريخ",
             f"Removed unparseable dates and dates outside {config.MIN_VALID_YEAR}-01-01 … {today.isoformat()}",
             f"DELETE FROM wq WHERE Sample_Date IS NULL OR Sample_Date < DATE '{config.MIN_VALID_YEAR}-01-01' "
             f"OR Sample_Date > DATE '{today.isoformat()}'")
    log.step(7, "فحص الإحداثيات", "Removed samples from stations with missing/invalid coordinates",
             "DELETE FROM wq WHERE Station_ID IN (SELECT Station_ID FROM stations_df WHERE NOT Coordinates_Valid)")

    con.execute("""
        CREATE TABLE wq2 AS
        SELECT DISTINCT ON (Station_ID, Sample_Date, Sample_Time, Depth, Parameter_Code, Method_Code,
                            Value_Raw, Unit) *
        FROM wq
    """)
    con.execute("DROP TABLE wq; ALTER TABLE wq2 RENAME TO wq")
    log.rows.append({"Step": 8, "Task": "إزالة السجلات المكررة",
                     "Action": "Removed exact duplicate samples (station, date, time, depth, parameter, method, value)",
                     "Rows_Before": log.rows[-1]["Rows_After"],
                     "Rows_Removed": log.rows[-1]["Rows_After"] - log.count(), "Rows_After": log.count()})

    log.step(9, "إنشاء جدول للقياسات الصحيحة", "Removed non-numeric values",
             "DELETE FROM wq WHERE Value IS NULL")
    log.step(9, "إنشاء جدول للقياسات الصحيحة", "Removed values flagged Suspect / Contamination by GEMStat",
             "DELETE FROM wq WHERE Data_Quality IN ('Suspect', 'Contamination')")
    log.step(9, "إنشاء جدول للقياسات الصحيحة", "Removed physically implausible values (outside valid range)",
             "DELETE FROM wq WHERE Value < Min_Valid OR Value > Max_Valid")

    quality_case = "CASE " + " ".join(
        f"WHEN Data_Quality = '{k}' THEN '{v}'" for k, v in config.QUALITY_MAP.items()) + " ELSE 'Valid' END"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    con.execute(f"""
        COPY (
            SELECT Station_ID,
                   Sample_Date AS Date,
                   Parameter,
                   round(Value, 6) AS Value,
                   Unit_Std AS Unit,
                   CASE WHEN Value_Flag = '<' THEN 'Below detection limit'
                        WHEN Value_Flag = '>' THEN 'Above detection limit'
                        WHEN Value_Flag = '~' THEN 'Estimated'
                        ELSE {quality_case} END AS Quality
            FROM wq
            ORDER BY Station_ID, Date, Parameter
        ) TO '{out_path.as_posix()}' (FORMAT PARQUET, COMPRESSION ZSTD, ROW_GROUP_SIZE 500000)
    """)
    log.rows.append({"Step": 10, "Task": "حفظ سجل لجميع عمليات التنظيف",
                     "Action": f"Wrote {out_path.name} and this cleaning log",
                     "Rows_Before": log.count(), "Rows_Removed": 0, "Rows_After": log.count()})

    summary = con.execute(f"""
        SELECT Parameter, Unit, count(*) AS Measurements, count(DISTINCT Station_ID) AS Stations,
               min(Date) AS First_Date, max(Date) AS Last_Date,
               round(min(Value), 4) AS Min, round(quantile_cont(Value, 0.5), 4) AS Median,
               round(max(Value), 4) AS Max,
               count(*) FILTER (WHERE Quality = 'Valid') AS Valid,
               count(*) FILTER (WHERE Quality <> 'Valid') AS Flagged
        FROM read_parquet('{out_path.as_posix()}')
        GROUP BY Parameter, Unit ORDER BY Measurements DESC
    """).df()
    con.close()
    return pd.DataFrame(log.rows), summary
