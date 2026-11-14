# SPDX-License-Identifier: Apache-2.0
"""Request-scoped user coordinates; never added to the published site registry."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictFloat, StrictInt

from backend.domain.lunar.model import ParamError, Site, load_sites


class CustomSite(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: Literal["custom-a", "custom-b"]
    lat_deg: Annotated[StrictInt | StrictFloat, Field(ge=-90, le=90, allow_inf_nan=False)]
    lon_deg_east: Annotated[StrictInt | StrictFloat, Field(ge=-180, le=180, allow_inf_nan=False)]

    def to_site(self) -> Site:
        return Site(
            id=self.id,
            name=f"User coordinates {self.id[-1].upper()}",
            lat_deg=float(self.lat_deg),
            lon_deg_east=float(self.lon_deg_east),
            kind="user",
            source_url="",
            verified=False,
            coordinate_basis="user supplied, not independently verified",
        )


def resolve_sites(site_ids: list[str], custom_sites: list[CustomSite]) -> dict[str, Site]:
    catalog = {site.id: site for site in load_sites()}
    custom_ids = [site.id for site in custom_sites]
    if (
        len(set(site_ids)) != len(site_ids)
        or len(set(custom_ids)) != len(custom_ids)
        or any(site_id in catalog or site_id not in site_ids for site_id in custom_ids)
    ):
        raise ParamError("site_ids")
    catalog.update((site.id, site.to_site()) for site in custom_sites)
    if any(site_id not in catalog for site_id in site_ids):
        raise ParamError("site_ids")
    return catalog
