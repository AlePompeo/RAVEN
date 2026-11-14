# SPDX-License-Identifier: Apache-2.0
"""Planning arithmetic, not a spacecraft cost-estimating relationship."""

from decimal import Decimal

COST_ITEMS = (
    "mission_studies",
    "system_definition",
    "detailed_design_cost",
    "development_and_ait",
    "launch_and_transfer",
    "ground_segment",
    "operations",
    "disposal",
    "insurance_and_regulatory",
)


def budget_summary(
    costs: dict[str, float | None],
    contingency_percent: float | None,
    funding: float | None,
) -> dict[str, object]:
    known = [Decimal(str(costs[k])) for k in COST_ITEMS if costs.get(k) is not None]
    subtotal = sum(known, Decimal(0)) if known else None
    complete = len(known) == len(COST_ITEMS)
    contingency = (
        subtotal * Decimal(str(contingency_percent)) / 100
        if subtotal is not None and contingency_percent is not None
        else None
    )
    total = (
        subtotal + contingency
        if complete and subtotal is not None and contingency is not None
        else None
    )
    gap = total - Decimal(str(funding)) if total is not None and funding is not None else None
    return {
        "known_cost_items": len(known),
        "missing_cost_items": [k for k in COST_ITEMS if costs.get(k) is None],
        "known_subtotal": float(subtotal) if subtotal is not None else None,
        "contingency_amount": float(contingency) if contingency is not None else None,
        "total_lifecycle_cost": float(total) if total is not None else None,
        "funding_gap": float(gap) if gap is not None else None,
        "within_declared_funding": gap <= 0 if gap is not None else None,
        "method": "Sum of user-declared same-currency/base-year cost estimates plus stated contingency.",
        "economic_feasibility": None,
        "qualification": "Arithmetic affordability only; not a market quotation or economic feasibility finding.",
    }
