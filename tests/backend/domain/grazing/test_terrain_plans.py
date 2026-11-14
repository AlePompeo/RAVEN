# SPDX-License-Identifier: Apache-2.0
import json

from backend.domain.grazing import dem_select as ds
from scripts.build_terrain_plans import build


def test_shipped_plans_equal_the_computation() -> None:
    shipped = json.loads(ds.SHIPPED_PLANS.read_text(encoding="utf-8"))
    assert shipped == json.loads(json.dumps(build())), "run scripts/build_terrain_plans.py"


def test_a_shipped_plan_is_what_plan_site_returns() -> None:
    plan = ds._shipped(-85.9, 0.0)
    if plan is not None:
        assert plan == ds._plan(-85.9, 0.0)
