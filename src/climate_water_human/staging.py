"""Convert every GEMStat measurement CSV into a typed Parquet file using DuckDB."""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path

import duckdb
import pandas as pd

from .io_utils import duckdb_csv_source

log = logging.getLogger(__name__)

STAGING_SELECT = """
SELECT
    trim("GEMS Station Number")                         AS Station_ID,
    try_cast("Sample Date" AS DATE)                     AS Sample_Date,
    "Sample Date"                                       AS Sample_Date_Raw,
    "Sample Time"                                       AS Sample_Time,
    try_cast("Depth" AS DOUBLE)                         AS Depth,
    trim("Parameter Code")                              AS Parameter_Code,
    "Analysis Method Code"                              AS Method_Code,
    nullif(trim("Value Flags"), '')                     AS Value_Flag,
    try_cast("Value" AS DOUBLE)                         AS Value,
    "Value"                                             AS Value_Raw,
    trim("Unit")                                        AS Unit,
    coalesce(nullif(trim("Data Quality"), ''), 'Unknown') AS Data_Quality,
    nullif(trim("Integrated Value"), '')                AS Integrated_Value,
    '{source}'                                          AS Source_File
FROM {src}
"""


def stage_measurements(files: list[Path], out_dir: Path, threads: int = 2,
                       memory_limit: str = "3GB", overwrite: bool = False) -> pd.DataFrame:
    """Write ``<stem>.parquet`` for each CSV and return a per-file staging log."""
    out_dir.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    con.execute(f"SET threads={threads}; SET memory_limit='{memory_limit}'; SET preserve_insertion_order=false")
    rows = []
    with tempfile.TemporaryDirectory(dir=out_dir) as tmp:
        for path in files:
            target = out_dir / f"{path.stem}.parquet"
            if overwrite or not target.exists():
                src = duckdb_csv_source(con, path, Path(tmp))
                query = STAGING_SELECT.format(src=src, source=path.name.replace("'", "''"))
                tmp_target = target.with_suffix(".tmp.parquet")
                con.execute(f"COPY ({query}) TO '{tmp_target.as_posix()}' (FORMAT PARQUET, COMPRESSION ZSTD)")
                tmp_target.replace(target)
                log.info("Staged %s", path.name)
            stats = con.execute(f"""
                SELECT count(*),
                       count(*) FILTER (WHERE Sample_Date IS NULL),
                       count(*) FILTER (WHERE Value IS NULL),
                       count(DISTINCT Parameter_Code),
                       count(DISTINCT Station_ID)
                FROM read_parquet('{target.as_posix()}')
            """).fetchone()
            rows.append({
                "File": path.name, "Rows": stats[0], "Invalid_Dates": stats[1],
                "Non_Numeric_Values": stats[2], "Parameters": stats[3], "Stations": stats[4],
            })
    con.close()
    return pd.DataFrame(rows)
