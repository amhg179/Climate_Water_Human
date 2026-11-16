"""Station, parameter and method metadata (section 7.1 tasks 2–3, section 7.6 master table)."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

import numpy as np
import pandas as pd

from . import config
from .io_utils import read_metadata_csv

_EUROPE = (
    "AUT BEL BGR BIH CHE CYP CZE DEU DNK ESP EST FIN FRA GBR GRC HRV HUN IRL ISL ITA LIE LTU LUX LVA MKD MLT MNE "
    "NLD NOR POL PRT ROU SRB SVK SVN SWE"
).split()
CONTINENTS = {
    "ARG": "South America", "URY": "South America", "BRA": "South America",
    "CAN": "North America", "USA": "North America", "MEX": "North America",
    "IND": "Asia", "TUR": "Asia", "JPN": "Asia", "CHN": "Asia",
    **dict.fromkeys(_EUROPE, "Europe"),
}
DEFAULT_CONTINENT = "Unknown"

STATION_COLUMNS = {
    "GEMS Station Number": "Station_ID",
    "Local Station Number": "Local_Station_Number",
    "Country Name": "Country_Name",
    "Water Type": "Water_Type",
    "Station Identifier": "Station_Identifier",
    "Water Body Name": "Water_Body_Name",
    "Main Basin": "Main_Basin",
    "Elevation": "Elevation",
    "Monitoring Type": "Monitoring_Type",
    "Date Station Opened": "Date_Station_Opened",
    "Latitude": "Latitude",
    "Longitude": "Longitude",
}


def continent_for(country_id: str) -> str:
    return CONTINENTS.get(country_id, DEFAULT_CONTINENT)


def validate_coordinates(lat: pd.Series, lon: pd.Series) -> pd.Series:
    """True when coordinates are numeric, inside valid ranges and not the (0, 0) placeholder."""
    lat_n = pd.to_numeric(lat, errors="coerce")
    lon_n = pd.to_numeric(lon, errors="coerce")
    ok = lat_n.between(-90, 90) & lon_n.between(-180, 180)
    ok &= ~((lat_n == 0) & (lon_n == 0))
    return ok.fillna(False)


def _waterbody_name(row: pd.Series) -> tuple[str | float, str]:
    if isinstance(row["Water_Body_Name"], str) and row["Water_Body_Name"].strip():
        return row["Water_Body_Name"].strip().upper(), "Water Body Name"
    ident = row["Station_Identifier"]
    if isinstance(ident, str) and " - " in ident:
        head = ident.split(" - ")[0].strip()
        if head and not head.isdigit():
            return head.upper(), "Station Identifier"
    return np.nan, "Station (no water-body information)"


def _waterbody_id(country_id: str, name: str | float, station_id: str) -> str:
    key = f"{country_id}|{name}" if isinstance(name, str) else f"STATION|{station_id}"
    return "WB_" + hashlib.sha1(key.encode("utf-8")).hexdigest()[:10].upper()


def load_station_metadata(path: Path) -> tuple[pd.DataFrame, dict]:
    """Load, clean and de-duplicate the station metadata table."""
    raw = read_metadata_csv(path)
    stats = {"rows_raw": len(raw)}
    df = raw.rename(columns=STATION_COLUMNS)[list(STATION_COLUMNS.values())].copy()
    for col in df.columns:
        if df[col].dtype == object:
            df[col] = df[col].str.strip()
    df = df.drop_duplicates()
    stats["exact_duplicates_removed"] = stats["rows_raw"] - len(df)
    before = len(df)
    df = df.drop_duplicates(subset="Station_ID", keep="first")
    stats["conflicting_duplicate_ids_removed"] = before - len(df)
    df["Latitude"] = pd.to_numeric(df["Latitude"], errors="coerce")
    df["Longitude"] = pd.to_numeric(df["Longitude"], errors="coerce")
    df["Elevation"] = pd.to_numeric(df["Elevation"], errors="coerce")
    df["Coordinates_Valid"] = validate_coordinates(df["Latitude"], df["Longitude"])
    df["Country_ID"] = df["Station_ID"].str[:3]
    df["Continent"] = df["Country_ID"].map(continent_for)
    df["Country_Name"] = df["Country_Name"].replace({
        "Macedonia (the former Yugoslav Republic of)": "North Macedonia",
        "Netherlands (-the )": "Netherlands",
        "United States of America (the)": "United States of America",
    })
    wb = df.apply(_waterbody_name, axis=1, result_type="expand")
    df["Waterbody_Name"], df["Waterbody_Source"] = wb[0], wb[1]
    df["Waterbody_ID"] = [
        _waterbody_id(c, n, s) for c, n, s in zip(df["Country_ID"], df["Waterbody_Name"], df["Station_ID"])
    ]
    df["Surface_Water"] = df["Water_Type"].isin(config.SURFACE_WATER_TYPES)
    stats["stations"] = len(df)
    stats["invalid_coordinates"] = int((~df["Coordinates_Valid"]).sum())
    stats["countries"] = int(df["Country_ID"].nunique())
    return df.reset_index(drop=True), stats


def station_master(stations: pd.DataFrame) -> pd.DataFrame:
    """Station / Waterbody Master table of the integrated schema (section 7.6)."""
    out = pd.DataFrame({
        "Station_ID": stations["Station_ID"],
        "Waterbody_ID": stations["Waterbody_ID"],
        "Coordinates": [
            f"{lat:.6f}, {lon:.6f}" if ok else ""
            for lat, lon, ok in zip(stations["Latitude"], stations["Longitude"], stations["Coordinates_Valid"])
        ],
        "Water_Type": stations["Water_Type"].str.replace(" station", "", regex=False),
        "Country_ID": stations["Country_ID"],
        "Latitude": stations["Latitude"],
        "Longitude": stations["Longitude"],
        "Waterbody_Name": stations["Waterbody_Name"],
        "Country_Name": stations["Country_Name"],
        "Continent": stations["Continent"],
    })
    return out


def load_parameter_metadata(path: Path) -> pd.DataFrame:
    df = read_metadata_csv(path)
    df.columns = [re.sub(r"\W+", "_", c.strip()).strip("_") for c in df.columns]
    df["Standard_Name"] = df["Parameter_Code"].map(lambda c: config.CODE_TO_TARGET[c].name
                                                   if c in config.CODE_TO_TARGET else np.nan)
    return df.drop_duplicates(subset="Parameter_Code").reset_index(drop=True)


def load_methods_metadata(path: Path) -> pd.DataFrame:
    df = read_metadata_csv(path)
    df.columns = [re.sub(r"\W+", "_", c.strip()).strip("_") for c in df.columns]
    return df.drop_duplicates().reset_index(drop=True)
