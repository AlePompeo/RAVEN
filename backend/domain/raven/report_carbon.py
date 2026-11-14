# SPDX-License-Identifier: Apache-2.0
"""Declared mission emissions and a bounded paper-production comparison, not an LCA."""

from decimal import Decimal

PHASES = ("0", "A", "B", "C", "D", "E", "F")
PAPER_SOURCE = (
    "https://www.gov.uk/government/publications/greenhouse-gas-reporting-conversion-factors-2025"
)
PAPER_FACTOR = Decimal("1345.0779")
SHEET_KG = Decimal("0.210") * Decimal("0.297") * Decimal(80) / 1000


def carbon_summary(
    phases: dict[str, float | None],
    basis: str,
    boundary: str,
    compact_pages: int | None,
    reference_pages: int | None,
) -> dict[str, object]:
    known = [Decimal(str(phases[p])) for p in PHASES if phases.get(p) is not None]
    subtotal = sum(known, Decimal(0)) if known else None
    per_sheet = SHEET_KG * PAPER_FACTOR / 1000
    avoided = (
        (reference_pages - compact_pages) * per_sheet
        if compact_pages is not None and reference_pages is not None
        else None
    )
    return {
        "mission": {
            "unit": "kg CO2e",
            "known_phases": len(known),
            "missing_phases": [p for p in PHASES if phases.get(p) is None],
            "known_subtotal_kg_co2e": float(subtotal) if subtotal is not None else None,
            "total_kg_co2e": (
                float(subtotal) if len(known) == len(PHASES) and subtotal is not None else None
            ),
            "phase_emissions_kg_co2e": {p: phases.get(p) for p in PHASES},
            "basis": basis,
            "boundary": boundary,
            "source": "user_estimates",
            "independently_verified": False,
        },
        "document": {
            "compact_pages": compact_pages,
            "reference_pages": reference_pages,
            "page_count_method": "browser_layout_estimate_not_final_pdf_pagination",
            "copies": 1,
            "sides_per_sheet": 1,
            "paper_size": "A4",
            "paper_gsm": 80,
            "sheet_mass_kg": float(SHEET_KG),
            "paper_factor_kg_co2e_per_tonne": float(PAPER_FACTOR),
            "paper_factor_id": "19_506_5164_15_1",
            "paper_factor_source": PAPER_SOURCE,
            "paper_factor_scope": "UK DESNZ 2025 Material use / Paper and board: paper / Primary material production",
            "paper_production_kg_co2e_per_sheet": float(per_sheet),
            "compaction_avoided_kg_co2e": float(avoided) if avoided is not None else None,
            "not_printing_avoided_kg_co2e": (
                float(compact_pages * per_sheet) if compact_pages is not None else None
            ),
            "exclusions": "Ink/toner, printer, delivery, disposal and digital/server energy.",
            "qualification": "Potential paper-production emissions only; not verified savings, an offset, or a net digital-versus-print comparison.",
        },
    }
