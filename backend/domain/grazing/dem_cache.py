# SPDX-License-Identifier: Apache-2.0
"""Disk cache of the on-demand LOLA tiles of custom sites: size cap, LRU eviction, clear command.

Tiles of custom sites live in their own directory (`custom_dir()` = `<GRAZING_DEM_DIR>/custom`) so that
the tiles of the catalogue sites (`make grazing-dem`) are never evicted. The total size of that
directory (tiles, their sha256 files and the horizon masks computed from them) is capped by
`GRAZING_DEM_CACHE_MAX_MB` (default 200 MB, decimal). When it is over the cap the OLDEST files are
removed first; a tile that is read is touched (mtime = now), so "oldest" means "least recently used".

    python -m backend.domain.grazing.dem_cache --status | --clear     (`make grazing-dem-clear`)
"""

import argparse
import json
import logging
import os
from collections.abc import Iterable
from pathlib import Path

from backend.domain.grazing.dem import dem_dir

__all__ = [
    "DEFAULT_MAX_MB",
    "cache_files",
    "clear_cache",
    "custom_dir",
    "enforce_limit",
    "max_cache_bytes",
    "touch",
    "usage_bytes",
]

DEFAULT_MAX_MB = 300
log = logging.getLogger(__name__)
_SUFFIXES = (".f32", ".sha256", ".json")


def custom_dir(env: dict[str, str] | None = None) -> Path:
    """Cache directory of the custom-site tiles (separate from the catalogue cache)."""
    base = dem_dir(env)
    return base / "custom"


def max_cache_bytes(env: dict[str, str] | None = None) -> int:
    raw = (os.environ if env is None else env).get("GRAZING_DEM_CACHE_MAX_MB", "")
    try:
        mb = float(raw) if raw else float(DEFAULT_MAX_MB)
    except ValueError:
        mb = float(DEFAULT_MAX_MB)
    if not (0.0 < mb <= 100_000.0):
        mb = float(DEFAULT_MAX_MB)
    return int(mb * 1e6)


def cache_files(directory: Path) -> list[Path]:
    """Every cache file under `directory` (tiles, their sha256 files, horizon masks)."""
    if not directory.is_dir():
        return []
    return [p for p in directory.rglob("*") if p.is_file() and p.suffix in _SUFFIXES]


def usage_bytes(directory: Path) -> int:
    total = 0
    for p in cache_files(directory):
        try:
            total += p.stat().st_size
        except OSError:
            continue
    return total


def touch(path: Path) -> None:
    """Mark a file as just used (LRU); a failure is harmless."""
    try:
        os.utime(path)
    except OSError:
        pass


def _mtime(p: Path) -> float:
    try:
        return p.stat().st_mtime
    except OSError:
        return 0.0


def enforce_limit(
    directory: Path,
    max_bytes: int,
    protect: Iterable[Path] = (),
    *,
    max_files: int | None = None,
) -> list[str]:
    """Delete the oldest files until the directory is within `max_bytes`; returns the names removed.

    A tile and its `.sha256` go together. Files in `protect` are skipped (the tiles of the request in
    progress); if only protected files are left the cache stays over the cap, which the per-request cap
    makes impossible in practice.
    """
    keep = {Path(p) for p in protect}
    removed: list[str] = []
    used = usage_bytes(directory)
    files = cache_files(directory)
    count = len(files)
    if used <= max_bytes and (max_files is None or count <= max_files):
        return removed
    for p in sorted(files, key=_mtime):
        if used <= max_bytes and (max_files is None or count <= max_files):
            break
        if p in keep or p.with_suffix(".f32") in keep:
            continue
        try:
            size = p.stat().st_size
            p.unlink()
        except OSError:
            log.warning("disk cache eviction failed", exc_info=True)
            continue
        used -= size
        count -= 1
        removed.append(p.name)
    if used > max_bytes or (max_files is not None and count > max_files):
        log.warning("disk cache quota cannot be met; protected or unavailable files remain")
    return removed


def clear_cache(directory: Path) -> int:
    """Remove every cache file of the custom directory; returns the number of bytes freed."""
    freed = usage_bytes(directory)
    for p in cache_files(directory):
        try:
            p.unlink()
        except OSError:
            continue
    return freed


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--status", action="store_true", help="print size and cap")
    g.add_argument("--clear", action="store_true", help="delete the custom-site cache")
    args = ap.parse_args(argv)
    d = custom_dir()
    if args.clear:
        print(f"freed {clear_cache(d) / 1e6:.1f} MB in {d}")
        return 0
    print(
        json.dumps(
            {
                "dir": str(d),
                "used_mb": round(usage_bytes(d) / 1e6, 2),
                "max_mb": max_cache_bytes() / 1e6,
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
