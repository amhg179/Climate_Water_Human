"""Command line entry point: ``python -m climate_water_human``."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from .pipeline import run_pipeline


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="GEMStat V3 global water-quality data audit pipeline")
    parser.add_argument("--root", type=Path, default=None, help="Project root (default: repository root)")
    parser.add_argument("--zip-path", type=Path, default=None, help="Use an already downloaded GFQA_v3.zip")
    parser.add_argument("--extracted-dir", type=Path, default=None, help="Use an already extracted archive folder")
    parser.add_argument("--cdp-url", default=None,
                        help="Chrome DevTools URL used as a download fallback if Zenodo blocks scripted clients")
    parser.add_argument("--offline-basemap", action="store_true", help="Do not download the coastline basemap")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    result = run_pipeline(root=args.root, zip_path=args.zip_path, extracted_dir=args.extracted_dir,
                          cdp_url=args.cdp_url, offline_basemap=args.offline_basemap)
    print(result.overview.to_string(index=False))
    print()
    print(result.clean_summary.to_string(index=False))
    for name, path in result.outputs.items():
        print(f"{name}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
