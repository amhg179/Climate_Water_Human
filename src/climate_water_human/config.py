"""Project paths and scientific constants taken from the research draft."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]

ZENODO_RECORD_ID = "18459694"
ZENODO_CONCEPT_DOI = "10.5281/zenodo.13881899"
ZENODO_DOI = "10.5281/zenodo.18459694"
ZENODO_API_URL = f"https://zenodo.org/api/records/{ZENODO_RECORD_ID}"
GEMSTAT_ARCHIVE_NAME = "GFQA_v3.zip"
GEMSTAT_ARCHIVE_MD5 = "00f3ea19ce529753977eb3aeb08fbc47"

STATION_METADATA_FILE = "GEMStat_station_metadata.csv"
PARAMETER_METADATA_FILE = "GEMStat_parameter_metadata.csv"
METHODS_METADATA_FILE = "GEMStat_methods_metadata.csv"
METADATA_FILES = (STATION_METADATA_FILE, PARAMETER_METADATA_FILE, METHODS_METADATA_FILE)

SENTINEL2_START = date(2015, 6, 23)
ERA5_LAND_START = date(1950, 1, 1)
COMMON_WINDOW = (2015, 2021)
EXTENDED_WINDOW = (2000, 2024)
LONG_SERIES_MIN_YEARS = 10
MIN_VALID_YEAR = 1900

SURFACE_WATER_TYPES = ("River station", "Lake station", "Reservoir station", "Wetland station")

OPTICAL_PARAMETERS = ("Chlorophyll-a", "Turbidity", "TSS", "Water Temperature", "CDOM")


@dataclass(frozen=True)
class TargetParameter:
    """A water-quality variable from section 2.B of the draft and its harmonisation rule."""

    name: str
    codes: tuple[str, ...]
    unit: str
    unit_factors: dict[str, float]
    valid_range: tuple[float, float]
    satellite_observable: str
    notes: str = ""


TARGET_PARAMETERS: tuple[TargetParameter, ...] = (
    TargetParameter(
        "Chlorophyll-a", ("Chl-a",), "µg/L",
        {"mg/l": 1000.0, "µg/l": 1.0, "ug/l": 1.0},
        (0.0, 5000.0), "نعم، في ظروف مناسبة",
    ),
    TargetParameter(
        "Turbidity", ("TURB",), "NTU",
        {"NTU": 1.0},
        (0.0, 10000.0), "نعم، بتقدير غير مباشر ومعايرة",
        "JCU/FTU are not converted to NTU without a known relationship.",
    ),
    TargetParameter(
        "TSS", ("TSS",), "mg/L",
        {"mg/l": 1.0},
        (0.0, 100000.0), "نعم، بتقدير غير مباشر",
    ),
    TargetParameter(
        "Water Temperature", ("TEMP",), "°C",
        {"°C": 1.0},
        (-5.0, 50.0), "نعم",
    ),
    TargetParameter(
        "CDOM", ("A340",), "Absorbance (340 nm)",
        {"---": 1.0},
        (0.0, 1000.0), "في ظروف مناسبة",
        "CDOM proxy: absorbance at 340 nm as reported by GEMStat (A340).",
    ),
    TargetParameter(
        "DO", ("O2-Dis",), "mg/L",
        {"mg/l": 1.0},
        (0.0, 30.0), "ليس قياسًا مباشرًا موثوقًا من Sentinel-2",
    ),
    TargetParameter(
        "pH", ("pH",), "pH units",
        {"---": 1.0},
        (0.0, 14.0), "لا، يحتاج قياسات أرضية",
    ),
    TargetParameter(
        "Nitrate (as N)", ("NO3N",), "mg/L as N",
        {"mg/l": 1.0},
        (0.0, 500.0), "ليس قياسًا مباشرًا موثوقًا",
        "Nitrate as N and Nitrate as NO3 are different quantities; GEMStat reports NO3N as N.",
    ),
    TargetParameter(
        "E. coli", ("ECOLI",), "CFU/100 mL",
        {"1/100 ml": 1.0, "1/ml": 100.0},
        (0.0, 1.0e9), "يحتاج تحاليل مخبرية",
    ),
    TargetParameter(
        "Conductivity", ("EC",), "µS/cm",
        {"µS/cm": 1.0},
        (0.0, 200000.0), "لا، يحتاج قياسات أرضية",
    ),
)

CODE_TO_TARGET = {code: p for p in TARGET_PARAMETERS for code in p.codes}

QUALITY_MAP = {
    "Good": "Valid",
    "Fair": "Valid",
    "Unknown": "Valid",
    "Estimated": "Estimated",
    "Pending review": "Pending review",
    "Suspect": "Suspect",
    "Contamination": "Contamination",
}
EXCLUDED_QUALITY = ("Suspect", "Contamination")


@dataclass
class ProjectPaths:
    """Folder layout from section 11.1 of the draft."""

    root: Path = field(default_factory=lambda: PROJECT_ROOT)

    @property
    def references(self) -> Path:
        return self.root / "00_References"

    @property
    def raw(self) -> Path:
        return self.root / "01_Raw_Data"

    @property
    def raw_gemstat(self) -> Path:
        return self.raw / "GEMStat"

    @property
    def gemstat_extracted(self) -> Path:
        return self.raw_gemstat / "GFQA_v3"

    @property
    def gemstat_staging(self) -> Path:
        return self.raw_gemstat / "parquet"

    @property
    def metadata(self) -> Path:
        return self.root / "02_Metadata"

    @property
    def processed_water_quality(self) -> Path:
        return self.root / "03_Processed" / "Water_Quality"

    @property
    def feature_store(self) -> Path:
        return self.root / "04_Feature_Store"

    @property
    def integrated(self) -> Path:
        return self.root / "05_Integrated_Dataset"

    @property
    def quality_control(self) -> Path:
        return self.root / "06_Quality_Control"

    @property
    def results(self) -> Path:
        return self.root / "09_Results"

    RAW_SUBFOLDERS = ("GEMStat", "WQP", "Sentinel2", "Landsat", "ERA5", "CHIRPS", "WorldPop", "JMP", "Health")
    PROCESSED_SUBFOLDERS = ("Water_Quality", "Satellite", "Climate", "Population", "Health")
    TOP_LEVEL = (
        "00_References", "01_Raw_Data", "02_Metadata", "03_Processed", "04_Feature_Store",
        "05_Integrated_Dataset", "06_Quality_Control", "07_Experiments", "08_Models", "09_Results",
    )

    def create(self) -> None:
        for name in self.TOP_LEVEL:
            (self.root / name).mkdir(parents=True, exist_ok=True)
        for name in self.RAW_SUBFOLDERS:
            (self.raw / name).mkdir(parents=True, exist_ok=True)
        for name in self.PROCESSED_SUBFOLDERS:
            (self.root / "03_Processed" / name).mkdir(parents=True, exist_ok=True)
