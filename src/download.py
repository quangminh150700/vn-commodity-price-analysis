"""Re-download the raw datasets into data/raw/ (to refresh with the latest month).

Each file is written to a temporary file first and only replaces the existing
copy once the download has completed, so an interrupted download never leaves
a corrupt file behind.

Run:  python src/download.py
"""
from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import urlopen

RAW = Path(__file__).resolve().parents[1] / "data" / "raw"
TIMEOUT_SECONDS = 60

SOURCES = {
    # World Bank Pink Sheet. If this link stops working, get the current one from
    # https://www.worldbank.org/en/research/commodity-markets ("Monthly prices").
    "CMO-Historical-Data-Monthly.xlsx":
        "https://thedocs.worldbank.org/en/doc/74e8be41ceb20fa0da750cda2f6b9e4e-0050012026/"
        "related/CMO-Historical-Data-Monthly.xlsx",
    # WFP Viet Nam food prices on HDX: https://data.humdata.org/dataset/wfp-food-prices-for-viet-nam
    "wfp_food_prices_vnm.csv":
        "https://data.humdata.org/dataset/e44f2ae2-a8ab-4a93-8a3b-fba51a0f0c7e/resource/"
        "a9233d94-6289-482e-9d79-8d1934820a4b/download/wfp_food_prices_vnm.csv",
}


def download(url: str, dest: Path) -> int:
    """Download `url` to `dest` atomically. Returns the number of bytes written."""
    # Only https URLs reach urlopen below (bandit B310 is therefore suppressed)
    if urlparse(url).scheme != "https":
        raise ValueError(f"Refusing non-HTTPS URL: {url}")
    fd, tmp = tempfile.mkstemp(dir=dest.parent, suffix=".part")
    try:
        with urlopen(url, timeout=TIMEOUT_SECONDS) as resp, os.fdopen(fd, "wb") as out:  # nosec B310
            shutil.copyfileobj(resp, out)
        size = os.path.getsize(tmp)
        if size == 0:
            raise ValueError(f"Empty response from {url}")
        os.replace(tmp, dest)
        return size
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def main() -> None:
    RAW.mkdir(parents=True, exist_ok=True)
    for name, url in SOURCES.items():
        size = download(url, RAW / name)
        print(f"downloaded {name} ({size / 1024:,.0f} KB)")
    print("done -> now run: python src/clean.py")


if __name__ == "__main__":
    main()
