# SPDX-License-Identifier: Apache-2.0
"""Exploratory LOLA 5/20/240 m comparison, not independent validation.

Run from the repository root with tifffile and imagecodecs installed separately:
    python -m scripts.compare_lola_resolution

The 20/240 m cache must already exist. The 5 m products are read via HTTP ranges;
no whole GeoTIFF is downloaded. The remote ETags identify the examined revisions,
not cryptographic hashes of the complete products.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import urllib.request
from functools import cache

import numpy as np

from backend.domain.grazing.dem import FAR_DEM_ID, LolaDem, load_lock
from backend.domain.grazing.geometry import great_circle_destination
from backend.domain.grazing.horizon import _Grid

RADIUS = 1_737_400.0
LAT, LON = -89.67, 129.78
URL = "https://pgda.gsfc.nasa.gov/data/LOLA_5mpp/87S/"
DEM = ("ldem_87s_5mpp.tif", 3_465_285_714, 'W/"ce8c1052-17c7ede95a8"')
COUNTS = ("ldec_87s_5mpp.tif", 145_895_726, 'W/"8b2312e-17c7f5b5b10"')


class Remote(io.RawIOBase):
    """Seekable HTTP reader which rejects changed or incomplete responses."""

    def __init__(self, product: tuple[str, int, str]) -> None:
        self.name, self.size, self.etag = product
        self.position = 0

    def readable(self) -> bool:
        return True

    def seekable(self) -> bool:
        return True

    def tell(self) -> int:
        return self.position

    def seek(self, offset: int, whence: int = 0) -> int:
        position = (0 if whence == 0 else self.position if whence == 1 else self.size) + offset
        if position < 0:
            raise ValueError("negative seek")
        self.position = position
        return position

    def read(self, size: int = -1) -> bytes:
        if size < 0:
            size = self.size - self.position
        if size == 0 or self.position >= self.size:
            return b""
        start, end = self.position, min(self.size, self.position + size) - 1
        req = urllib.request.Request(URL + self.name, headers={"Range": f"bytes={start}-{end}"})
        with urllib.request.urlopen(req, timeout=60) as response:
            if response.status != 206 or response.headers.get("ETag") != self.etag:
                raise ValueError(f"{self.name}: unexpected HTTP status or changed ETag")
            if response.headers.get("Content-Range") != f"bytes {start}-{end}/{self.size}":
                raise ValueError(f"{self.name}: incorrect Content-Range")
            data = response.read()
        if len(data) != end - start + 1:
            raise ValueError(f"{self.name}: incomplete range")
        self.position += len(data)
        return data


def samples(
    product: tuple[str, int, str], row: np.ndarray, col: np.ndarray
) -> tuple[np.ndarray, str]:
    """Read the four surrounding pixels per position and hash fetched tile payloads."""
    import tifffile

    digest = hashlib.sha256()
    with tifffile.TiffFile(Remote(product)) as tif:
        page = tif.pages[0]
        if (
            page.shape != (40_000, 40_000)
            or page.tilewidth != 256
            or page.tilelength != 256
            or page.tags["ModelPixelScaleTag"].value != (5.0, 5.0, 0.0)
            or page.tags["ModelTiepointTag"].value != (0.0, 0.0, 0.0, -100_000.0, 100_000.0, 0.0)
            or page.geotiff_tags["GTRasterTypeGeoKey"] != 1
        ):
            raise ValueError(f"{product[0]}: unexpected geometry or registration")
        source = Remote(product)

        @cache
        def tile(r: int, c: int) -> np.ndarray:
            index = r * 157 + c
            source.seek(page.dataoffsets[index])
            data = source.read(page.databytecounts[index])
            digest.update(index.to_bytes(4, "big"))
            digest.update(data)
            decoded, _, _ = page.decode(data, index)
            return decoded[0, :, :, 0]

        ir, ic = np.floor(row).astype(int), np.floor(col).astype(int)
        if np.any(ir < 0) or np.any(ic < 0) or np.any(ir + 1 >= 40_000) or np.any(ic + 1 >= 40_000):
            raise ValueError("sample outside 5 m product")
        corners = np.array(
            [
                [
                    tile(int(r // 256), int(c // 256))[int(r % 256), int(c % 256)]
                    for r, c in zip(ir + dr, ic + dc, strict=True)
                ]
                for dr, dc in ((0, 0), (0, 1), (1, 0), (1, 1))
            ],
            dtype=float,
        )
    return corners, digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lat", type=float, default=LAT, help="latitude in degrees, -90 to -87")
    parser.add_argument("--lon", type=float, default=LON, help="east longitude in degrees")
    args = parser.parse_args()
    if not np.isfinite(args.lat) or not -90 <= args.lat <= -87:
        parser.error("latitude must be between -90 and -87 degrees")
    if not np.isfinite(args.lon) or not -180 <= args.lon <= 360:
        parser.error("east longitude must be between -180 and 360 degrees")
    site_lat, site_lon = args.lat, args.lon
    distance = np.arange(20.0, 10_000.1, 20.0)
    azimuths = np.radians([0.0, 90.0, 180.0, 270.0])[:, None]
    point_lat, point_lon = great_circle_destination(
        site_lat, site_lon, azimuths, distance[None, :] / RADIUS
    )
    lat, lon = np.r_[site_lat, point_lat.ravel()], np.r_[site_lon, point_lon.ravel()]
    rho = 2 * RADIUS * np.tan(np.radians(90 + lat) / 2)
    x, y = rho * np.sin(np.radians(lon)), rho * np.cos(np.radians(lon))
    col, row = (x + 100_000) / 5 - 0.5, (100_000 - y) / 5 - 0.5
    grid20 = _Grid(LolaDem(allow_download=False), site_lat, site_lon, 10_200)
    grid240 = _Grid(
        LolaDem(spec=load_lock(dataset_id=FAR_DEM_ID), allow_download=False),
        site_lat,
        site_lon,
        10_200,
    )
    z20, z240 = grid20.sample(lat, lon), grid240.sample(lat, lon)
    if not all(np.isfinite(z).all() for z in (z20, z240)):
        raise ValueError("non-finite PDS terrain samples; comparison is incomplete")
    corners, dem_hash = samples(DEM, row, col)
    counts, counts_hash = samples(COUNTS, row, col)
    fr, fc = row - np.floor(row), col - np.floor(col)
    z5 = corners[0] * (1 - fr) * (1 - fc) + corners[1] * (1 - fr) * fc
    z5 += corners[2] * fr * (1 - fc) + corners[3] * fr * fc
    if not all(np.isfinite(z).all() for z in (z5, z20, z240)):
        raise ValueError("non-finite terrain samples; comparison is incomplete")
    print("missing window tiles (20 m, 240 m):", grid20.tiles_missing, grid240.tiles_missing)
    print("site:", site_lat, site_lon, "sample positions:", len(lat))
    print(
        "5 m corner count >0:",
        [int(np.count_nonzero(counts > 0, axis=0).tolist().count(i)) for i in range(5)],
    )
    print("SHA-256 of ordered (tile index, compressed tile bytes):", dem_hash, counts_hash)
    print("site elevations 5 m, 20 m, 240 m:", z5[0], z20[0], z240[0])
    diff = z5 - z20
    print(
        "5 m - 20 m elevations: mean, RMS, max abs (m):",
        np.mean(diff),
        np.sqrt(np.mean(diff**2)),
        np.max(np.abs(diff)),
    )
    for i, az in enumerate((0, 90, 180, 270)):
        delta = distance / RADIUS
        maxima = []
        for z in (z5, z20, z240):
            heights = z[1:].reshape(4, -1)[i]
            angle = np.degrees(
                np.arctan2(
                    (RADIUS + heights) * np.cos(delta) - (RADIUS + z[0] + 2),
                    (RADIUS + heights) * np.sin(delta),
                )
            )
            maxima.append(float(np.max(angle)))
        print(f"azimuth {az}° maxima (5/20/240 m):", *maxima, "5-20:", maxima[0] - maxima[1])


if __name__ == "__main__":
    main()
