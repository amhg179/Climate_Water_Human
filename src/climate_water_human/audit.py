"""Section 15 — automatic global audit of the GEMStat V3 archive."""

from __future__ import annotations

from pathlib import Path

import duckdb
import pandas as pd

from . import config


class GEMStatAudit:
    """Runs every audit query of section 15 on the staged Parquet files and the clean table."""

    def __init__(self, staging_glob: str, clean_path: Path, stations: pd.DataFrame,
                 parameters: pd.DataFrame, memory_limit: str = "3GB"):
        self.staging_glob = staging_glob
        self.clean = clean_path.as_posix()
        self.con = duckdb.connect()
        self.con.execute(f"SET memory_limit='{memory_limit}'; SET preserve_insertion_order=false")
        self.stations = stations
        self.con.register("stations", stations[[
            "Station_ID", "Country_ID", "Country_Name", "Continent", "Water_Type", "Latitude", "Longitude",
            "Coordinates_Valid", "Surface_Water", "Waterbody_ID",
        ]])
        self.con.register("params", parameters[[
            "Parameter_Code", "Parameter_Name", "Parameter_Long_Name", "Parameter_Group",
        ]])

    def close(self) -> None:
        self.con.close()

    def _raw(self) -> str:
        return f"read_parquet('{self.staging_glob}')"

    def _clean(self) -> str:
        return f"read_parquet('{self.clean}')"

    def overview(self, n_files: int) -> pd.DataFrame:
        r = self.con.execute(f"""
            SELECT count(*), count(DISTINCT Parameter_Code), count(DISTINCT Station_ID),
                   count(DISTINCT substr(Station_ID, 1, 3)), min(year(Sample_Date)), max(year(Sample_Date))
            FROM {self._raw()}
        """).fetchone()
        c = self.con.execute(f"SELECT count(*), count(DISTINCT Station_ID) FROM {self._clean()}").fetchone()
        st = self.stations
        items = [
            ("Measurement CSV files", n_files),
            ("Total measurements (all variables)", r[0]),
            ("Water-quality variables with data", r[1]),
            ("Stations in metadata", len(st)),
            ("Stations with measurements", r[2]),
            ("Countries", st["Country_ID"].nunique()),
            ("Countries with measurements", r[3]),
            ("First year", r[4]),
            ("Last year", r[5]),
            ("Stations with valid coordinates", int(st["Coordinates_Valid"].sum())),
            ("Surface-water stations", int(st["Surface_Water"].sum())),
            ("Clean target-variable measurements", c[0]),
            ("Stations in clean target table", c[1]),
        ]
        return pd.DataFrame(items, columns=["Metric", "Value"])

    def stations_by_water_type(self) -> pd.DataFrame:
        return (self.stations.groupby("Water_Type").size().rename("Stations")
                .sort_values(ascending=False).reset_index())

    def variable_statistics(self) -> pd.DataFrame:
        """Statistics for every water-quality variable (all 600+ parameters)."""
        return self.con.execute(f"""
            WITH r AS (SELECT * FROM {self._raw()})
            SELECT r.Parameter_Code, p.Parameter_Name, p.Parameter_Long_Name, p.Parameter_Group,
                   count(*) AS Measurements,
                   count(DISTINCT r.Station_ID) AS Stations,
                   count(DISTINCT substr(r.Station_ID, 1, 3)) AS Countries,
                   min(year(r.Sample_Date)) AS First_Year,
                   max(year(r.Sample_Date)) AS Last_Year,
                   count(DISTINCT year(r.Sample_Date)) AS Years,
                   string_agg(DISTINCT r.Unit, ', ') AS Units,
                   round(100.0 * count(r.Value) / count(*), 2) AS Numeric_Percent,
                   round(100.0 * count(*) FILTER (WHERE r.Value_Flag = '<') / count(*), 2) AS Below_LOQ_Percent
            FROM r LEFT JOIN params p USING (Parameter_Code)
            GROUP BY ALL ORDER BY Measurements DESC
        """).df()

    def measurements_per_year(self) -> pd.DataFrame:
        return self.con.execute(f"""
            SELECT year(Sample_Date) AS Year, count(*) AS Measurements,
                   count(DISTINCT Station_ID) AS Stations, count(DISTINCT Parameter_Code) AS Variables
            FROM {self._raw()} WHERE Sample_Date IS NOT NULL
            GROUP BY 1 ORDER BY 1
        """).df()

    def target_measurements_per_year(self) -> pd.DataFrame:
        df = self.con.execute(f"""
            SELECT year(Date) AS Year, Parameter, count(*) AS n FROM {self._clean()} GROUP BY 1, 2
        """).df()
        out = df.pivot(index="Year", columns="Parameter", values="n").fillna(0).astype("int64")
        order = [p.name for p in config.TARGET_PARAMETERS if p.name in out.columns]
        return out[order].reset_index()

    def country_coverage(self) -> pd.DataFrame:
        """Section 8.3 — stations, measurements, variables and years per country."""
        data = self.con.execute(f"""
            SELECT substr(Station_ID, 1, 3) AS Country_ID, count(*) AS Measurements,
                   count(DISTINCT Station_ID) AS Stations_With_Data,
                   count(DISTINCT Parameter_Code) AS Variables,
                   min(year(Sample_Date)) AS First_Year, max(year(Sample_Date)) AS Last_Year,
                   count(DISTINCT year(Sample_Date)) AS Years
            FROM {self._raw()} GROUP BY 1
        """).df()
        meta = (self.stations.groupby(["Country_ID", "Country_Name", "Continent"]).size()
                .rename("Stations").reset_index())
        out = meta.merge(data, on="Country_ID", how="left")
        out["Measurements_per_Station"] = (out["Measurements"] / out["Stations_With_Data"]).round(1)
        return out.sort_values("Measurements", ascending=False).reset_index(drop=True)

    def long_time_series(self, min_years: int = config.LONG_SERIES_MIN_YEARS) -> pd.DataFrame:
        """Stations with ≥ ``min_years`` distinct years of measurements for a target variable."""
        return self.con.execute(f"""
            WITH py AS (
                SELECT Station_ID, Parameter, count(DISTINCT year(Date)) AS Years,
                       min(year(Date)) AS First_Year, max(year(Date)) AS Last_Year, count(*) AS n
                FROM {self._clean()} GROUP BY 1, 2
            ), lng AS (SELECT * FROM py WHERE Years >= {min_years})
            SELECT l.Station_ID, s.Country_Name, s.Water_Type, s.Latitude, s.Longitude,
                   max(l.Years) AS Max_Years, min(l.First_Year) AS First_Year, max(l.Last_Year) AS Last_Year,
                   max(l.Last_Year) - min(l.First_Year) + 1 AS Span_Years,
                   sum(l.n) AS Measurements,
                   count(*) AS Long_Series_Variables,
                   string_agg(l.Parameter || ' (' || l.Years || 'y)', '; ' ORDER BY l.Years DESC) AS Variables
            FROM lng l JOIN stations s USING (Station_ID)
            GROUP BY ALL ORDER BY Max_Years DESC, Measurements DESC
        """).df()

    def satellite_climate_matchability(self) -> pd.DataFrame:
        """Stations that can be matched with Sentinel-2 and ERA5-Land (section 15)."""
        optical = ", ".join(f"'{p}'" for p in config.OPTICAL_PARAMETERS)
        c0, c1 = config.COMMON_WINDOW
        e0, e1 = config.EXTENDED_WINDOW
        df = self.con.execute(f"""
            WITH c AS (SELECT * FROM {self._clean()})
            SELECT s.Station_ID, s.Country_ID, s.Country_Name, s.Continent, s.Water_Type,
                   s.Latitude, s.Longitude, s.Waterbody_ID,
                   count(*) AS Measurements,
                   count(*) FILTER (WHERE c.Parameter IN ({optical})
                                    AND c.Date >= DATE '{config.SENTINEL2_START}') AS S2_Optical_Samples,
                   count(DISTINCT c.Date) FILTER (WHERE c.Parameter IN ({optical})
                                    AND c.Date >= DATE '{config.SENTINEL2_START}') AS S2_Sample_Dates,
                   count(*) FILTER (WHERE c.Date >= DATE '{config.ERA5_LAND_START}') AS ERA5_Samples,
                   count(*) FILTER (WHERE year(c.Date) BETWEEN {c0} AND {c1}) AS Common_Window_Samples,
                   count(*) FILTER (WHERE year(c.Date) BETWEEN {e0} AND {e1}) AS Extended_Window_Samples,
                   string_agg(DISTINCT c.Parameter, ', ') FILTER (
                       WHERE c.Parameter IN ({optical}) AND c.Date >= DATE '{config.SENTINEL2_START}'
                   ) AS S2_Variables,
                   min(c.Date) AS First_Date, max(c.Date) AS Last_Date,
                   bool_and(s.Surface_Water) AS Surface_Water
            FROM c JOIN stations s USING (Station_ID)
            GROUP BY ALL
        """).df()
        df["Sentinel2_Matchable"] = df["Surface_Water"] & (df["S2_Optical_Samples"] > 0)
        df["ERA5_Land_Matchable"] = df["ERA5_Samples"] > 0
        df["Both_Matchable"] = df["Sentinel2_Matchable"] & df["ERA5_Land_Matchable"]
        return df.sort_values(["Both_Matchable", "S2_Optical_Samples"], ascending=False).reset_index(drop=True)

    def window_coverage(self) -> pd.DataFrame:
        """Section 5 — coverage of each target variable in the two time windows."""
        c0, c1 = config.COMMON_WINDOW
        e0, e1 = config.EXTENDED_WINDOW
        df = self.con.execute(f"""
            SELECT Parameter, Unit,
                   count(*) AS All_Years,
                   count(*) FILTER (WHERE year(Date) BETWEEN {c0} AND {c1}) AS "Common_{c0}_{c1}",
                   count(DISTINCT Station_ID) FILTER (WHERE year(Date) BETWEEN {c0} AND {c1})
                       AS "Stations_{c0}_{c1}",
                   count(*) FILTER (WHERE year(Date) BETWEEN {e0} AND {e1}) AS "Extended_{e0}_{e1}",
                   count(DISTINCT Station_ID) FILTER (WHERE year(Date) BETWEEN {e0} AND {e1})
                       AS "Stations_{e0}_{e1}"
            FROM {self._clean()} GROUP BY 1, 2
        """).df()
        order = {p.name: i for i, p in enumerate(config.TARGET_PARAMETERS)}
        return df.sort_values("Parameter", key=lambda s: s.map(order)).reset_index(drop=True)

    def data_quality_distribution(self) -> pd.DataFrame:
        return self.con.execute(f"""
            SELECT Data_Quality, count(*) AS Measurements,
                   round(100.0 * count(*) / sum(count(*)) OVER (), 3) AS Percent
            FROM {self._raw()} GROUP BY 1 ORDER BY 2 DESC
        """).df()

    def missing_data(self) -> pd.DataFrame:
        cols = ["Station_ID", "Sample_Date", "Sample_Time", "Depth", "Parameter_Code", "Method_Code",
                "Value", "Unit", "Data_Quality"]
        expr = ", ".join(f"count(*) FILTER (WHERE {c} IS NULL OR CAST({c} AS VARCHAR) = '') AS \"{c}\""
                         for c in cols)
        row = self.con.execute(f"SELECT count(*) AS total, {expr} FROM {self._raw()}").df().iloc[0]
        total = int(row["total"])
        out = pd.DataFrame({"Column": cols, "Missing": [int(row[c]) for c in cols]})
        out["Missing_Percent"] = (100 * out["Missing"] / max(total, 1)).round(3)
        out["Total_Rows"] = total
        return out

    def units_per_parameter(self) -> pd.DataFrame:
        return self.con.execute(f"""
            SELECT Parameter_Code, count(DISTINCT Unit) AS Units, string_agg(DISTINCT Unit, ', ') AS Unit_List
            FROM {self._raw()} GROUP BY 1 HAVING count(DISTINCT Unit) > 1 ORDER BY 2 DESC, 1
        """).df()
