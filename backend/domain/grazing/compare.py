# SPDX-License-Identifier: Apache-2.0
"""Confronto siti sul modello RAVEN: riassunto per sito di un'analisi e classifica.

Ogni sito coperto dal DEM e' analizzato con `analysis.analyze` (stessa finestra, passo, stazione, antenna, bit-rate
e k per tutti). Qui non c'e' fisica nuova: si leggono i numeri dell'analisi e si ordinano.

Regola di classifica (nessun peso nascosto): ordine decrescente per (1) ore di finestra reale (margine >= 0 al
bit-rate scelto, con diffrazione), (2) margine mediano, (3) identificativo del sito (solo per rendere l'ordine
deterministico). Le due componenti sono riportate per ogni sito. I siti fuori copertura DEM non hanno numeri ne' posizione.

Il margine minimo/mediano e' calcolato sugli istanti con la Terra sopra l'orizzonte locale (elevazione > 0): sotto
l'orizzonte il collegamento non esiste e il margine non e' significativo. La serie dell'analisi non e' decimata (il
limite di passi per sito lo garantisce): le statistiche sono quelle dell'analisi.
"""

import statistics
from typing import Any

UNCOVERED_STATE = "non confrontabile con RAVEN (fuori copertura DEM)"
ANALYSED_STATE = "analizzato con RAVEN"
MAX_STEPS_PER_SITE = 1500  # = MAX_OUTPUT_POINTS dell'analisi: nessuna decimazione
MAX_TOTAL_SAMPLES = 6000  # siti coperti x passi
MAX_CHART_POINTS = 400

RANKING_RULE = (
    "Classifica = ordine decrescente per (1) ore di finestra reale (margine >= 0 al bit-rate scelto, con diffrazione), "
    "poi (2) margine mediano (dB, sugli istanti con la Terra sopra l'orizzonte). Nessun peso nascosto: le due componenti "
    "sono nelle colonne della tabella. I siti fuori copertura DEM non hanno numeri ne' posizione."
)


def _finite(a: list[float | None]) -> list[float]:
    return [float(v) for v in a if v is not None]


def _round(v: float | None, nd: int = 3) -> float | None:
    return None if v is None else round(float(v), nd)


def uncovered_row(site: dict[str, Any]) -> dict[str, Any]:
    return {"site": site, "state": UNCOVERED_STATE, "covered": False, "rank": None}


def summarise(site: dict[str, Any], res: dict[str, Any]) -> dict[str, Any]:
    """Riga di un sito coperto, a partire dall'uscita di `analyze`."""
    s, w, fl = res["series"], res["windows"], res["flags"]
    el = s["earth_el_deg"]
    margin = s["margin_chosen_rate_db"]
    up = [m for e, m in zip(el, margin, strict=True) if e is not None and m is not None and e > 0.0]
    rates = [r for r in _finite(s["chosen_rate_bps"]) if r > 0.0]
    elf = _finite(el)
    ch = res["compensator"]["chosen"]
    n = max(1, len(el))
    pts = len(res["series_time_unix"])
    stride = max(1, -(-pts // MAX_CHART_POINTS))
    sl = slice(None, None, stride)
    row: dict[str, Any] = {
        "site": site,
        "state": ANALYSED_STATE,
        "covered": True,
        "rank": None,
        "geometric_hours": w["geometric_hours"],
        "real_hours": w["real_hours"],
        "transition_hours": w["transition_hours"],
        "total_hours": w["total_hours"],
        "margin_min_db": _round(min(up)) if up else None,
        "margin_median_db": _round(statistics.median(up)) if up else None,
        "rate_bps": {
            "min": min(rates) if rates else None,
            "median": statistics.median(rates) if rates else None,
            "max": max(rates) if rates else None,
            "mean_declared": ch["mean_rate_bps"],
            "declared_fraction": round(len(rates) / n, 4),
        },
        "compensator": {
            "k": res["compensator"]["k"],
            "outage_pct": ch["outage_pct"],
            "delivered_bits": ch["delivered_bits"],
            "scheduled_bits": ch["scheduled_bits"],
            "relative_data": ch["relative_data"],
            "declared_steps": ch["declared_steps"],
        },
        "earth_el_min_deg": _round(min(elf)) if elf else None,
        "earth_el_max_deg": _round(max(elf)) if elf else None,
        "terrain": {
            "source": fl["terrain"]["source"],
            "product_id": fl["terrain"]["product_id"],
            "synthetic": fl["terrain"]["synthetic"],
            "radius_resolved": fl["radius_resolved"],
            "radius_resolved_fraction": round(fl["radius_resolved_fraction"], 4),
            "correction_status": fl["correction"]["status"],
            "correction_label": fl["correction"]["label"],
            "multipath_status": fl["multipath"]["status"],
            "blocked_fraction": round(fl["blocked_fraction"], 4),
        },
        "series": {
            "time_unix": res["series_time_unix"][sl],
            "margin_db": margin[sl],
            "earth_el_deg": el[sl],
            "chosen_rate_bps": s["chosen_rate_bps"][sl],
            "geometric_visible": s["geometric_visible"][sl],
            "step_min": res["series_step_min"] * stride,
        },
    }
    if "window_samples" in res:
        row["window_samples"] = res["window_samples"]
    return row


def rank_rows(rows: list[dict[str, Any]]) -> list[str]:
    """Assegna `rank` ai siti analizzati e restituisce gli id in ordine di classifica."""
    done = [r for r in rows if r["covered"]]
    done.sort(
        key=lambda r: (
            -r["real_hours"],
            -(r["margin_median_db"] if r["margin_median_db"] is not None else float("-inf")),
            r["site"]["id"],
        )
    )
    for i, r in enumerate(done, start=1):
        r["rank"] = i
    return [r["site"]["id"] for r in done]
