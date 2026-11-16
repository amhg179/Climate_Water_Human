import pandas as pd

from climate_water_human import metadata
from climate_water_human.io_utils import detect_encoding


def test_detect_encoding_cp1252(mini_archive):
    assert detect_encoding(mini_archive / "GEMStat_station_metadata.csv") in {"cp1252", "latin-1"}
    assert detect_encoding(mini_archive / "pH.csv") == "utf-8"


def test_validate_coordinates():
    lat = pd.Series([0.0, 91.0, 45.0, None, 0.0])
    lon = pd.Series([0.0, 10.0, 181.0, 10.0, 10.0])
    assert metadata.validate_coordinates(lat, lon).tolist() == [False, False, False, False, True]


def test_load_station_metadata(mini_archive):
    stations, stats = metadata.load_station_metadata(mini_archive / "GEMStat_station_metadata.csv")
    assert stats["rows_raw"] == 5
    assert stats["exact_duplicates_removed"] == 1
    assert stations["Station_ID"].is_unique
    assert stats["countries"] == 4
    assert stats["invalid_coordinates"] == 1
    row = stations.set_index("Station_ID").loc["ARG00003"]
    assert row["Responsible_Collection_Agency"] == "Agência" if "Responsible_Collection_Agency" in row else True
    assert row["Surface_Water"]
    assert not stations.set_index("Station_ID").loc["IND00007", "Surface_Water"]


def test_station_master_schema(mini_archive):
    stations, _ = metadata.load_station_metadata(mini_archive / "GEMStat_station_metadata.csv")
    master = metadata.station_master(stations)
    for col in ["Station_ID", "Waterbody_ID", "Coordinates", "Water_Type", "Country_ID"]:
        assert col in master.columns
    assert master["Waterbody_ID"].notna().all()
