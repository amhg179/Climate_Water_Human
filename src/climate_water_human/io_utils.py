"""Encoding-robust readers for GEMStat CSV files (latin-1 / cp1252 encoded)."""

from __future__ import annotations

from pathlib import Path

import duckdb
import pandas as pd

_C1_RANGE = range(0x80, 0xA0)


def detect_encoding(path: Path, sample_bytes: int | None = None) -> str:
    """Return 'utf-8', 'cp1252' or 'latin-1' for a text file."""
    with open(path, "rb") as fh:
        data = fh.read() if sample_bytes is None else fh.read(sample_bytes)
    try:
        data.decode("utf-8")
        return "utf-8"
    except UnicodeDecodeError:
        pass
    if any(b in _C1_RANGE for b in data):
        return "cp1252"
    return "latin-1"


def read_metadata_csv(path: Path) -> pd.DataFrame:
    """Read a (small) GEMStat metadata table as strings with the right encoding."""
    encoding = detect_encoding(path)
    return pd.read_csv(path, encoding=encoding, encoding_errors="replace", dtype=str, keep_default_na=False,
                       na_values=[""])


def transcode_to_utf8(src: Path, dst: Path, chunk_size: int = 1 << 24) -> Path:
    """Stream-transcode a cp1252/latin-1 file into UTF-8."""
    encoding = detect_encoding(src)
    dst.parent.mkdir(parents=True, exist_ok=True)
    with open(src, encoding=encoding, errors="replace", newline="") as fin, \
            open(dst, "w", encoding="utf-8", newline="") as fout:
        while True:
            block = fin.read(chunk_size)
            if not block:
                break
            fout.write(block)
    return dst


def duckdb_csv_source(con: duckdb.DuckDBPyConnection, path: Path, tmp_dir: Path) -> str:
    """Return a SQL table expression that reads ``path`` as all-VARCHAR columns.

    DuckDB reads strict latin-1 natively; files containing cp1252-only bytes are
    transcoded to UTF-8 first.
    """
    posix = path.as_posix().replace("'", "''")
    expr = f"read_csv('{posix}', encoding='latin-1', all_varchar=true, header=true)"
    try:
        con.sql(f"SELECT count(*) FROM {expr}").fetchone()
        return expr
    except duckdb.InvalidInputException:
        utf8 = transcode_to_utf8(path, tmp_dir / f"{path.stem}.utf8.csv")
        posix = utf8.as_posix().replace("'", "''")
        return f"read_csv('{posix}', all_varchar=true, header=true)"
