from __future__ import annotations

from pathlib import Path

import pytest

STATION_HEADER = (
    "GEMS Station Number,Local Station Number,Country Name,Water Type,Station Identifier,Station Narrative,"
    "Water Body Name,Main Basin,Upstream Basin Area,Elevation,Monitoring Type,Date Station Opened,"
    "Responsible Collection Agency,Latitude,Longitude,River Width,Discharge,Max. Depth,Lake Area,Lake Volume,"
    "Average Retention,Area of Aquifer,Depth of Impermeable Lining,Production Zone,Mean Abstraction Rate,"
    "Mean Abstraction Level"
)
MEAS_HEADER = ("GEMS Station Number,Sample Date,Sample Time,Depth,Parameter Code,Analysis Method Code,Value Flags,"
               "Value,Unit,Data Quality,Integrated Value,Remark,License Information")


def _station(sid, country, wtype, ident, body, lat, lon):
    return f"{sid},L1,{country},{wtype},{ident},narr,{body},BASIN,,10,TREND,1980-01-01,Agência,{lat},{lon}" + "," * 11


@pytest.fixture()
def mini_archive(tmp_path: Path) -> Path:
    root = tmp_path / "GFQA_v3"
    root.mkdir()
    stations = [
        STATION_HEADER,
        _station("ARG00003", "Argentina", "River station", "Paraguay River - at Puerto Bermejo", "RIO PARAGUAI",
                 -26.9, -58.5),
        _station("ARG00003", "Argentina", "River station", "Paraguay River - at Puerto Bermejo", "RIO PARAGUAI",
                 -26.9, -58.5),
        _station("DEU00001", "Germany", "Lake station", "Bodensee - Mitte", "BODENSEE", 47.6, 9.4),
        _station("IND00007", "India", "Groundwater station", "Well 7", "", 22.5, 88.3),
        _station("USA00009", "United States", "Reservoir station", "Lake Mead", "LAKE MEAD", 999, -114.7),
    ]
    (root / "GEMStat_station_metadata.csv").write_bytes("\n".join(stations).encode("cp1252"))
    (root / "GEMStat_parameter_metadata.csv").write_bytes((
        "Parameter Code,Parameter Name,Parameter Long Name,Parameter Group,EC Number,CAS Number,ChEBI Number,"
        "Parameter Description\n"
        "pH,pH,pH,/Physical,,,,pH value\n"
        "Chl-a,Chlorophyll a,Chlorophyll a,/Biological,,,,chl\n"
        "TEMP,Temperature,Water Temperature,/Physical,,,,temp\n"
        "TURB,Turbidity,Turbidity,/Physical,,,,turb\n"
        "Cl-Dis,Chloride,Dissolved Chloride,/Chemical,,,,cl\n"
    ).encode("cp1252"))
    (root / "GEMStat_methods_metadata.csv").write_bytes((
        "Parameter Code,Analysis Method Code,Unit,Parameter Long Name,Method Name,Method Type,Method Number,"
        "Method Source,Method Description\n"
        "pH,0,---,pH,,,,,Undefined\n"
        "Chl-a,0,µg/l,Chlorophyll a,,,,,Undefined\n"
        "TEMP,0,°C,Water Temperature,,,,,Undefined\n"
    ).encode("cp1252"))
    ph = [MEAS_HEADER]
    for year in range(2005, 2022):
        ph.append(f"ARG00003,{year}-06-01,10:00,0.2,pH,0,,7.{year % 10},---,Good,,,")
        ph.append(f"DEU00001,{year}-07-01,10:00,1,pH,0,,8.1,---,Fair,,,")
    ph += [
        "ARG00003,2020-06-01,10:00,0.2,pH,0,,7.0,---,Good,,,",   # exact duplicate
        "ARG00003,2020-06-01,10:00,0.2,pH,0,,7.0,---,Good,,,",
        "ARG00003,2019-03-01,10:00,0.2,pH,0,,19.5,---,Good,,,",  # out of range
        "ARG00003,2019-04-01,10:00,0.2,pH,0,,7.3,---,Suspect,,,",
        "ARG00003,1850-01-01,10:00,0.2,pH,0,,7.3,---,Good,,,",   # implausible date
        "XXX00001,2019-04-01,10:00,0.2,pH,0,,7.3,---,Good,,,",   # unknown station
        "USA00009,2019-04-01,10:00,0.2,pH,0,,7.3,---,Good,,,",   # invalid coordinates
        "IND00007,2019-04-01,10:00,1,pH,0,,7.3,---,Good,,,",
    ]
    (root / "pH.csv").write_text("\n".join(ph) + "\n", encoding="utf-8")
    chl = [MEAS_HEADER,
           "DEU00001,2018-07-01,10:00,1,Chl-a,0,,5.5,µg/l,Good,,,",
           "DEU00001,2019-07-01,10:00,1,Chl-a,0,,0.004,mg/l,Good,,,",
           "DEU00001,2020-07-01,10:00,1,Chl-a,0,<,0.1,µg/l,Good,,,"]
    (root / "Chlorophyll.csv").write_bytes(("\n".join(chl) + "\n").encode("cp1252"))
    temp = [MEAS_HEADER,
            "ARG00003,2019-01-01,10:00,0.2,TEMP,0,,26.5,°C,Good,,,",
            "DEU00001,2019-08-01,10:00,1,TEMP,0,,21.0,°C,Good,,,",
            "DEU00001,2019-08-02,10:00,1,TURB,0,,4.0,JCU,Good,,,",
            "DEU00001,2019-08-03,10:00,1,TURB,0,,3.0,NTU,Good,,,"]
    (root / "Physical_parameters.csv").write_bytes(("\n".join(temp) + "\n").encode("cp1252"))
    cl = [MEAS_HEADER, "ARG00003,2019-01-01,10:00,0.2,Cl-Dis,0,,12,mg/l,Good,,,"]
    (root / "Chloride.csv").write_text("\n".join(cl) + "\n", encoding="utf-8")
    return root
