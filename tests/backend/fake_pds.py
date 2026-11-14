# SPDX-License-Identifier: Apache-2.0
"""TEST-ONLY stand-in for the PDS node: serves byte ranges of a synthetic file with the size and ETag
of the locked product (the values are NOT LOLA data: a hash of the pixel index, inside the label range)."""

import io
import urllib.request
from typing import Self

import numpy as np

from backend.domain.grazing.dem import DemSpec, load_lock


class Resp(io.BytesIO):
    def __init__(self, data: bytes, headers: dict[str, str], status: int = 206) -> None:
        super().__init__(data)
        self.headers = headers
        self.status = status

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *a: object) -> None:
        self.close()


class FakePds:
    """`open(request, timeout)` like an urllib opener; counts requests and bytes, records URLs."""

    def __init__(self) -> None:
        self.urls: list[str] = []
        self.bytes_served = 0
        self._specs: dict[str, DemSpec] = {}

    def _spec(self, url: str) -> DemSpec:
        if url not in self._specs:
            import json

            from backend.domain.grazing.dem import LOCK_PATH

            for e in json.loads(LOCK_PATH.read_text())["datasets"]:
                if e["url"] == url:
                    self._specs[url] = load_lock(dataset_id=e["id"])
            if url not in self._specs:
                raise AssertionError(f"request to a URL that is not in the lock: {url}")
        return self._specs[url]

    def open(self, req: urllib.request.Request, timeout: float) -> Resp:
        spec = self._spec(req.full_url)
        self.urls.append(req.full_url)
        rng = req.get_header("Range")
        assert rng is not None
        spans = [tuple(map(int, p.split("-"))) for p in rng.removeprefix("bytes=").split(",")]
        parts = b""
        for a, b in spans:
            idx = np.arange(a // 4, (b + 1) // 4, dtype=np.int64)
            km = (((idx * 2654435761) % 2000) - 1000) / 1000.0  # -1..1 km
            data = km.astype("<f4").tobytes()
            self.bytes_served += len(data)
            parts += (
                b"--B\r\nContent-Type: application/octet-stream\r\n"
                + f"Content-Range: bytes {a}-{b}/{spec.size}\r\n\r\n".encode()
                + data
                + b"\r\n"
            )
        parts += b"--B--\r\n"
        return Resp(parts, {"Content-Type": "multipart/byteranges; boundary=B", "ETag": spec.etag})
