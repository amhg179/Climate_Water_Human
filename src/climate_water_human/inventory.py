"""Section 6.3 — ``data_source_inventory.csv``."""

from __future__ import annotations

import pandas as pd

INVENTORY_COLUMNS = ["Source", "Variable", "Start", "End", "Spatial Resolution", "Temporal Resolution", "Downloaded"]

_BASE = [
    ("GEMStat", "Chlorophyll-a", "حسب المحطة", "حسب المحطة", "Station", "Irregular"),
    ("Sentinel-2", "Reflectance", "2015", "Current", "10–20 m", "Irregular"),
    ("ERA5-Land", "Temperature", "1950", "Current", "~9 km", "Hourly"),
    ("WorldPop", "Population", "2015", "2030", "~100 m", "Annual"),
    ("GBD", "Diarrhoeal disease", "1990", "2021", "Country/Subnational", "Annual"),
    ("JMP", "Drinking water", "2000", "2024", "Country/Subnational", "Irregular estimates"),
]


def data_source_inventory(downloaded: set[str]) -> pd.DataFrame:
    """Return the inventory table of the draft with the ``Downloaded`` column updated."""
    rows = [(*r, "Yes" if r[0] in downloaded else "No") for r in _BASE]
    return pd.DataFrame(rows, columns=INVENTORY_COLUMNS)


def gemstat_variable_inventory(clean_summary: pd.DataFrame) -> pd.DataFrame:
    """Actual GEMStat start/end per target variable (complements the 'حسب المحطة' entry)."""
    return pd.DataFrame({
        "Source": "GEMStat",
        "Variable": clean_summary["Parameter"],
        "Start": pd.to_datetime(clean_summary["First_Date"]).dt.year,
        "End": pd.to_datetime(clean_summary["Last_Date"]).dt.year,
        "Spatial Resolution": "Station",
        "Temporal Resolution": "Irregular",
        "Downloaded": "Yes",
        "Measurements": clean_summary["Measurements"],
        "Stations": clean_summary["Stations"],
    })
