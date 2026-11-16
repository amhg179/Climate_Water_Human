"""Step 1 of the acquisition sequence: download, verify and extract GEMStat V3."""

from __future__ import annotations

import hashlib
import logging
import zipfile
from pathlib import Path

import pandas as pd
import requests

from . import config

log = logging.getLogger(__name__)

_HEADERS = {"User-Agent": "Climate_Water_Human/0.1 (research data pipeline)"}


def md5sum(path: Path, chunk_size: int = 1 << 22) -> str:
    h = hashlib.md5()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(chunk_size), b""):
            h.update(chunk)
    return h.hexdigest()


def fetch_record_files(session: requests.Session | None = None) -> list[dict]:
    """Return the file list (key, size, md5, url) of the Zenodo record."""
    session = session or requests.Session()
    resp = session.get(config.ZENODO_API_URL, headers=_HEADERS, timeout=60)
    resp.raise_for_status()
    files = []
    for f in resp.json()["files"]:
        files.append({
            "key": f["key"],
            "size": int(f["size"]),
            "md5": f["checksum"].split(":", 1)[-1],
            "url": f["links"]["self"],
        })
    return files


def _download_with_requests(url: str, dest: Path, session: requests.Session) -> None:
    tmp = dest.with_suffix(dest.suffix + ".part")
    headers = dict(_HEADERS)
    mode = "wb"
    if tmp.exists():
        headers["Range"] = f"bytes={tmp.stat().st_size}-"
        mode = "ab"
    with session.get(url, headers=headers, stream=True, timeout=120) as resp:
        if resp.status_code == 200:
            mode = "wb"
        resp.raise_for_status()
        with open(tmp, mode) as fh:
            for chunk in resp.iter_content(chunk_size=1 << 20):
                fh.write(chunk)
    tmp.replace(dest)


def _download_with_browser(url: str, dest: Path, cdp_url: str) -> None:
    """Download through an existing Chrome session (useful when Zenodo blocks scripted clients)."""
    import asyncio

    from playwright.async_api import async_playwright

    async def _run() -> None:
        async with async_playwright() as p:
            browser = await p.chromium.connect_over_cdp(cdp_url)
            ctx = browser.contexts[0] if browser.contexts else await browser.new_context()
            resp = await ctx.request.get(url, timeout=1_800_000)
            if resp.status != 200:
                raise RuntimeError(f"Browser download failed with HTTP {resp.status}")
            dest.write_bytes(await resp.body())

    asyncio.run(_run())


def download_gemstat(
    dest_dir: Path,
    zip_path: Path | None = None,
    cdp_url: str | None = None,
    expected_md5: str = config.GEMSTAT_ARCHIVE_MD5,
) -> Path:
    """Obtain ``GFQA_v3.zip`` and verify its MD5 checksum.

    Order: an existing verified archive in ``dest_dir`` -> ``zip_path`` provided
    by the user -> direct HTTPS download from Zenodo -> optional browser (CDP).
    """
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / config.GEMSTAT_ARCHIVE_NAME
    if dest.exists() and md5sum(dest) == expected_md5:
        log.info("Archive already present and verified: %s", dest)
        return dest
    if zip_path is not None:
        zip_path = Path(zip_path)
        if md5sum(zip_path) != expected_md5:
            raise ValueError(f"MD5 mismatch for {zip_path}")
        if zip_path.resolve() != dest.resolve():
            dest.unlink(missing_ok=True)
            try:
                dest.symlink_to(zip_path.resolve())
            except OSError:
                import shutil

                shutil.copy2(zip_path, dest)
        return dest

    url = f"{config.ZENODO_API_URL}/files/{config.GEMSTAT_ARCHIVE_NAME}/content"
    try:
        _download_with_requests(url, dest, requests.Session())
    except requests.HTTPError as exc:
        if cdp_url is None:
            raise RuntimeError(
                "Direct download from Zenodo failed "
                f"({exc}). Download {url} manually and pass --zip-path, or pass --cdp-url."
            ) from exc
        log.warning("Direct download failed (%s); retrying via browser at %s", exc, cdp_url)
        _download_with_browser(url, dest, cdp_url)
    digest = md5sum(dest)
    if digest != expected_md5:
        raise ValueError(f"MD5 mismatch after download: {digest} != {expected_md5}")
    return dest


def extract_archive(archive: Path, out_dir: Path) -> Path:
    """Unzip the archive (idempotent)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive) as zf:
        for member in zf.infolist():
            target = out_dir / member.filename
            if target.exists() and target.stat().st_size == member.file_size:
                continue
            zf.extract(member, out_dir)
    return out_dir


def discover_csv_files(root: Path) -> pd.DataFrame:
    """List every CSV in the extracted archive and classify it as metadata or data."""
    rows = []
    for path in sorted(root.rglob("*.csv")):
        rows.append({
            "File": path.name,
            "Path": str(path.relative_to(root)),
            "Kind": "metadata" if path.name in config.METADATA_FILES else "measurements",
            "Size_MB": round(path.stat().st_size / 1e6, 3),
        })
    return pd.DataFrame(rows, columns=["File", "Path", "Kind", "Size_MB"])
