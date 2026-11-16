"""Station maps and figures for the audit report."""

from __future__ import annotations

import json
import logging
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import folium  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402
import requests  # noqa: E402
from folium.plugins import FastMarkerCluster  # noqa: E402

log = logging.getLogger(__name__)

LAND_URL = "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_110m_land.geojson"
WATER_TYPE_COLORS = {
    "River station": "#1f77b4", "Lake station": "#2ca02c", "Reservoir station": "#9467bd",
    "Wetland station": "#8c564b", "Groundwater station": "#ff7f0e",
}


def load_land(cache: Path) -> dict | None:
    if not cache.exists():
        try:
            resp = requests.get(LAND_URL, timeout=30)
            resp.raise_for_status()
            cache.parent.mkdir(parents=True, exist_ok=True)
            cache.write_bytes(resp.content)
        except requests.RequestException as exc:
            log.warning("Basemap unavailable (%s); drawing stations without coastlines", exc)
            return None
    return json.loads(cache.read_text(encoding="utf-8"))


def _draw_land(ax, land: dict | None) -> None:
    if not land:
        return
    for feat in land["features"]:
        geom = feat["geometry"]
        polys = [geom["coordinates"]] if geom["type"] == "Polygon" else geom["coordinates"]
        for poly in polys:
            xs, ys = zip(*poly[0])
            ax.fill(xs, ys, color="#e8e8e8", edgecolor="#9e9e9e", linewidth=0.3, zorder=0)


def static_station_map(stations: pd.DataFrame, out: Path, land: dict | None,
                       highlight: pd.Series | None = None, title: str = "") -> Path:
    st = stations[stations["Coordinates_Valid"]]
    fig, ax = plt.subplots(figsize=(14, 7), dpi=130)
    _draw_land(ax, land)
    for wt, color in WATER_TYPE_COLORS.items():
        sub = st[st["Water_Type"] == wt]
        ax.scatter(sub["Longitude"], sub["Latitude"], s=2, c=color, label=f"{wt} ({len(sub):,})", alpha=0.7,
                   linewidths=0, zorder=2)
    if highlight is not None:
        hi = st[st["Station_ID"].isin(highlight)]
        ax.scatter(hi["Longitude"], hi["Latitude"], s=6, facecolors="none", edgecolors="red", linewidths=0.4,
                   label=f"Sentinel-2 + ERA5-Land matchable ({len(hi):,})", zorder=3)
    ax.set_xlim(-180, 180)
    ax.set_ylim(-60, 85)
    ax.set_xlabel("Longitude")
    ax.set_ylabel("Latitude")
    ax.set_title(title or f"GEMStat V3 stations (n = {len(st):,})")
    ax.legend(loc="lower left", markerscale=4, fontsize=8, frameon=True)
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(out)
    plt.close(fig)
    return out


def interactive_station_map(stations: pd.DataFrame, out: Path) -> Path:
    st = stations[stations["Coordinates_Valid"]]
    fmap = folium.Map(location=[30, 0], zoom_start=2, tiles="OpenStreetMap")
    callback = """function (row) {
        var m = L.circleMarker(new L.LatLng(row[0], row[1]), {radius: 4, color: row[2], fillOpacity: 0.8});
        m.bindPopup(row[3]);
        return m;
    }"""
    data = [
        [lat, lon, WATER_TYPE_COLORS.get(wt, "#333333"), f"{sid}<br>{name}<br>{country}<br>{wt}"]
        for lat, lon, wt, sid, name, country in zip(
            st["Latitude"], st["Longitude"], st["Water_Type"], st["Station_ID"],
            st["Waterbody_Name"].fillna(""), st["Country_Name"])
    ]
    FastMarkerCluster(data, callback=callback, name="GEMStat stations").add_to(fmap)
    fmap.save(str(out))
    return out


def per_year_chart(per_year: pd.DataFrame, out: Path) -> Path:
    fig, ax = plt.subplots(figsize=(12, 4.5), dpi=130)
    ax.bar(per_year["Year"], per_year["Measurements"], color="#1f77b4", width=0.9)
    ax.set_yscale("log")
    ax.set_xlabel("Year")
    ax.set_ylabel("Measurements (log scale)")
    ax.set_title("GEMStat V3 — number of measurements per year (all variables)")
    ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    fig.savefig(out)
    plt.close(fig)
    return out


def target_per_year_chart(target_per_year: pd.DataFrame, out: Path, start_year: int = 1970) -> Path:
    df = target_per_year[target_per_year["Year"] >= start_year].set_index("Year")
    fig, ax = plt.subplots(figsize=(12, 5), dpi=130)
    for col in df.columns:
        ax.plot(df.index, df[col], label=col, linewidth=1.4)
    ax.axvspan(2015, 2021, color="orange", alpha=0.12, label="Common window 2015–2021")
    ax.set_yscale("log")
    ax.set_xlabel("Year")
    ax.set_ylabel("Clean measurements (log scale)")
    ax.set_title("Target water-quality variables per year")
    ax.legend(ncol=3, fontsize=8)
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(out)
    plt.close(fig)
    return out


def country_chart(countries: pd.DataFrame, out: Path) -> Path:
    df = countries.dropna(subset=["Stations_With_Data"]).sort_values("Stations_With_Data")
    fig, ax = plt.subplots(figsize=(10, 10), dpi=130)
    ax.barh(df["Country_Name"], df["Stations_With_Data"], color="#2ca02c")
    ax.set_xscale("log")
    ax.set_xlabel("Stations with measurements (log scale)")
    ax.set_title("Stations per country")
    ax.grid(axis="x", alpha=0.3)
    fig.tight_layout()
    fig.savefig(out)
    plt.close(fig)
    return out
