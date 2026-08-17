"""
Pulls the pre-built corpus.db down from a GitHub Release asset if it isn't
already on disk. corpus.db is gitignored (see backend/app/config.py) and
too large for a normal git push -- Render rebuilds from git on every
deploy, so this runs as part of the build step to put the file back.
"""
from __future__ import annotations

import os
import sys
import urllib.request
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
CORPUS_DB_PATH = DATA_DIR / "corpus.db"


def main() -> None:
    if CORPUS_DB_PATH.exists():
        print(f"{CORPUS_DB_PATH} already present ({CORPUS_DB_PATH.stat().st_size / 1e6:.1f} MB), skipping download.")
        return

    url = os.environ.get("CORPUS_DB_URL")
    if not url:
        print("CORPUS_DB_URL is not set -- cannot fetch corpus.db.", file=sys.stderr)
        sys.exit(1)

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Downloading corpus.db from {url} ...")
    urllib.request.urlretrieve(url, CORPUS_DB_PATH)
    print(f"Downloaded {CORPUS_DB_PATH.stat().st_size / 1e6:.1f} MB.")


if __name__ == "__main__":
    main()
