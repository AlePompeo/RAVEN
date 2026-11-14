# SPDX-License-Identifier: Apache-2.0
"""Explicit, server-configured cloud access shared by RAVEN SI and report prose."""

import math
import re
from collections.abc import Mapping

GROQ_ID = "groq"
GROQ_URL = "https://api.groq.com/openai/v1"
PUBLIC_KNOWLEDGE_ID = "raven-si-guide"
_MODEL_SHAPE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/@+-]{0,127}$")
# Policy (12 Nov 2026): only Western models. Models of organisations affiliated with China or Russia are refused whatever the host (a Western
# service can host them). A name is matched on its words, so "qwen3-32b", "deepseek-r1-distill" and "alibaba/anything" are all refused.
DENIED_MODELS = re.compile(
    r"(?:^|[/:@._-])(?:qwen\w*|qwq|deepseek\w*|chatglm\w*|glm|zhipu\w*|z-?ai|kimi\w*|moonshot\w*|internlm\w*|baichuan\w*|minimax\w*|ernie\w*|"
    r"hunyuan\w*|doubao\w*|bytedance|seed-oss|stepfun|yi|alibaba|tencent|baidu|gigachat\w*|yandex\w*|yagpt|sber\w*|rugpt\w*|saiga|kandinsky)"
    r"(?:$|[/:@._0-9-])",
    re.IGNORECASE,
)


class _AllowedModel:
    pattern = _MODEL_SHAPE.pattern  # for request models (shape only; the denylist is applied by fullmatch/match and in the route)

    """A drop-in for the old `MODEL_RE`: the same `fullmatch`/`match`, but a denied model never matches."""

    def fullmatch(self, name: str) -> re.Match[str] | None:
        return None if DENIED_MODELS.search(name) else _MODEL_SHAPE.fullmatch(name)

    def match(self, name: str) -> re.Match[str] | None:
        return None if DENIED_MODELS.search(name) else _MODEL_SHAPE.match(name)


MODEL_RE = _AllowedModel()


def model_allowed(name: str) -> bool:
    return MODEL_RE.fullmatch(name) is not None


NUMERIC_FIELDS = {
    "metrics": frozenset(
        (
            "n_steps",
            "known_steps",
            "unknown_steps",
            "useful_hours",
            "unknown_hours",
            "sun_hours",
            "min_soc",
            "unmet_wh",
            "harvested_wh",
            "useful_fraction",
            "useful_fraction_of_known",
            "time_to_first_blackout_h",
            "blackout_within_known",
            "longest_unuseful_h",
        )
    ),
    "rf": frozenset(
        (
            "frequency_ghz",
            "tx_power_dbw",
            "tx_gain_dbi",
            "antenna_eta",
            "tsys_k",
            "ebn0_db",
            "misc_loss_db",
            "antenna_height_m",
            "regolith_eps_real",
            "regolith_eps_imag",
            "roughness_rms_m",
            "compensator_sigma_db",
            "compensator_k",
            "truth_height_offset_m",
            "profile_length_m",
            "tracking_error_deg",
            "gimbal_budget_db",
            "rate_bps",
            "station_gain_dbi",
            "apply_correction",
            "apply_multipath",
        )
    ),
    "energy": frozenset(
        (
            "array_area_m2",
            "cell_efficiency",
            "packing_factor",
            "degradation_fraction",
            "tilt_deg",
            "tilt_azimuth_deg",
            "sun_elevation_mask_deg",
            "battery_capacity_wh",
            "charge_efficiency",
            "discharge_efficiency",
            "min_soc",
            "initial_soc",
            "survival_load_w",
            "active_load_w",
            "pa_efficiency",
            "comms_duty",
        )
    ),
    "scenario": frozenset(("panel_height_m", "required_margin_db", "dsn_min_elevation_deg")),
}


def groq_config(env: Mapping[str, str]) -> tuple[str, str, str] | None:
    if env.get("RAVEN_SI_CLOUD_ENABLED") != "1":
        return None
    key = env.get("GROQ_API_KEY", "").strip()
    model = env.get("GROQ_MODEL", "openai/gpt-oss-20b").strip()
    if not key or not MODEL_RE.fullmatch(model):
        return None
    return GROQ_URL, model, key


def report_technical_profile(context: object) -> dict[str, object]:
    """Exclude free-text dossiers, financial assumptions, names and source documents."""
    data = context if isinstance(context, dict) else {}
    scenarios = data.get("scenarios")
    out: list[dict[str, object]] = []
    for scenario in scenarios[:2] if isinstance(scenarios, list) else []:
        if not isinstance(scenario, dict):
            continue
        item: dict[str, object] = {}
        for field in ("metrics", "parameters_used"):
            raw = scenario.get(field)
            if not isinstance(raw, dict):
                continue
            groups = raw if field == "parameters_used" else {"metrics": raw}
            values = {}
            for group, params in groups.items():
                if group not in ("metrics", "rf", "energy", "scenario") or not isinstance(
                    params, dict
                ):
                    continue
                values[group] = {
                    k: v
                    for k, v in params.items()
                    if isinstance(k, str)
                    and k in NUMERIC_FIELDS[group]
                    and (
                        v is None
                        or isinstance(v, int)
                        or (isinstance(v, float) and math.isfinite(v))
                    )
                }
            item[field] = values if field == "parameters_used" else values.get("metrics", {})
        out.append(item)
    return {
        "scope": "Anonymous numerical study profiles only; no full mission design or verified approvals.",
        "scenarios": out,
    }
