# SPDX-License-Identifier: Apache-2.0
"""Custom sites of the RAVEN API: request models, the terrain service (estimate, 409, caps, download).

A custom site is {id: "c-...", name, lat_deg, lon_deg_east (-180..360, normalised), panel and antenna
height}. Everything is validated twice (pydantic bounds, then `s0.custom_site(strict=True)`); the
answers never echo the input. Downloads happen only with `allow_download: true`, only for the tiles
the plan needs (<= 10 MB per site, <= 40 MB per request, <= `RAVEN_DEM_MAX_MB_PER_HOUR` per hour for
the whole server), one request at a time, always from the fixed PDS URLs of `dem.lock.json`.
"""

import asyncio
import logging
import threading
import time
from collections import deque
from typing import TYPE_CHECKING, Annotated, Any

from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, StrictFloat, StrictInt

from backend.domain.raven import s0_context as s0
from backend.domain.raven.s0_context import SiteRecord

if TYPE_CHECKING:
    from backend.domain.raven.custom_terrain import TerrainStore

log = logging.getLogger(__name__)

Num = StrictInt | StrictFloat
DEFAULT_MAX_MB_PER_HOUR = 120.0
_ID = r"^c-[a-z0-9]([a-z0-9-]{0,30}[a-z0-9])?$"
_NAME = r"^[A-Za-z0-9][A-Za-z0-9 ._,()'-]{0,39}$"


class CustomSiteIn(BaseModel):
    """A site defined by the user. `extra=forbid`, bounded numbers, a restricted name and id."""

    model_config = ConfigDict(extra="forbid")
    id: Annotated[str, Field(pattern=_ID, min_length=3, max_length=33)]
    name: Annotated[str, Field(pattern=_NAME, min_length=1, max_length=40)]
    lat_deg: Annotated[Num, Field(ge=-90, le=90, allow_inf_nan=False)]
    lon_deg_east: Annotated[Num, Field(ge=-180, le=360, allow_inf_nan=False)]
    panel_height_m: Annotated[Num, Field(ge=0.1, le=100, allow_inf_nan=False)] | None = None
    antenna_height_m: Annotated[Num, Field(ge=0.1, le=100, allow_inf_nan=False)] | None = None

    def record(self) -> SiteRecord:
        return s0.custom_site(
            self.id,
            float(self.lat_deg),
            float(self.lon_deg_east),
            name=self.name,
            panel_height_m=None if self.panel_height_m is None else float(self.panel_height_m),
            antenna_height_m=None
            if self.antenna_height_m is None
            else float(self.antenna_height_m),
            strict=True,
        )


class EstimateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sites: Annotated[list[CustomSiteIn], Field(min_length=1, max_length=s0.MAX_CUSTOM_SITES)]


def records(customs: list[CustomSiteIn]) -> dict[str, SiteRecord]:
    """Records by id; ids unique, at most `MAX_CUSTOM_SITES`. Raises `S0Error` (generic 422)."""
    if len(customs) > s0.MAX_CUSTOM_SITES:
        raise s0.S0Error("custom_sites")
    out: dict[str, SiteRecord] = {}
    for c in customs:
        if c.id in out:
            raise s0.S0Error("site_id")
        out[c.id] = c.record()
    return out


class TerrainService:
    """Owns the terrain store, the download lock and the hourly download budget."""

    def __init__(self, store: "TerrainStore | None" = None, *, mb_per_hour: float | None = None):
        self._store = store
        self._lock = threading.Lock()
        self.dl_sem = asyncio.Semaphore(1)
        self.mb_per_hour = DEFAULT_MAX_MB_PER_HOUR if mb_per_hour is None else mb_per_hour
        self._spent: deque[tuple[float, float]] = deque()  # (time, MB)

    @property
    def store(self) -> "TerrainStore":
        from backend.domain.raven.custom_terrain import TerrainStore

        with self._lock:
            if self._store is None:
                self._store = TerrainStore()
            return self._store

    def _budget_left_mb(self) -> float:
        now = time.monotonic()
        with self._lock:
            while self._spent and now - self._spent[0][0] > 3600.0:
                self._spent.popleft()
            return self.mb_per_hour - sum(mb for _, mb in self._spent)

    def _record(self, mb: float) -> None:
        with self._lock:
            self._spent.append((time.monotonic(), mb))

    async def prepare(self, sites: list[SiteRecord], allow_download: bool) -> JSONResponse | None:
        """None when the terrain of every site is in the cache (or unknown); else the answer to send:
        409 'needs download' with the estimate, 413 over a cap, 429 over the hourly budget, 503 if the
        server is busy downloading or the PDS node fails. With `allow_download` the missing tiles are
        fetched here, then None is returned."""
        from backend.domain.grazing.dem import DemUnavailable

        if not sites:
            return None
        est = await asyncio.to_thread(self.store.estimate, sites)
        if not est["needs_download"]:
            return None
        if est["request_over_cap"]:
            return JSONResponse(
                {"detail": "download over the per-request cap", "estimate": est}, status_code=413
            )
        if not allow_download:
            return JSONResponse({"detail": "needs download", "estimate": est}, status_code=409)
        if est["mb_to_download"] > self._budget_left_mb():
            return JSONResponse(
                {"detail": "hourly download budget used up", "estimate": est},
                status_code=429,
                headers={"Retry-After": "600"},
            )
        if self.dl_sem.locked():
            return JSONResponse(
                {"detail": "download in progress"}, status_code=503, headers={"Retry-After": "5"}
            )
        async with self.dl_sem:
            try:
                n = await asyncio.to_thread(self.store.download, sites)
            except DemUnavailable:
                return JSONResponse(
                    {"detail": "terrain data not reachable", "estimate": est},
                    status_code=503,
                    headers={"Retry-After": "30"},
                )
            except Exception:
                log.exception("download del terreno")
                return JSONResponse({"detail": "errore interno"}, status_code=500)
            self._record(n * est["tile_bytes"] * est["wire_factor"] / 1e6)
        return None

    def kwargs(
        self, site: SiteRecord, profile_length_m: float, *, compute: bool = True
    ) -> dict[str, Any]:
        if not site.custom:
            return {}
        return self.store.kwargs(site, profile_length_m, compute=compute)
