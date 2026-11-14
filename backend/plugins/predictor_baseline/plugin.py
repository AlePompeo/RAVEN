# SPDX-License-Identifier: Apache-2.0
"""Predittore del margine di collegamento: serve SOLO il modello promosso (extra [ml]).

Le librerie ML sono importate in modo pigro: senza l'extra il plugin si carica e l'app parte;
l'uso solleva PluginError.
"""

import math
import threading
from collections.abc import Mapping
from typing import Any

from backend.core.errors import InvalidMeasurement, ModelRegistryError, PluginError
from backend.core.manifest import Manifest
from backend.ml.registry import FileModelRegistry, default_registry_dir

FEATURES = ("power_w", "distance_km")
# Limiti assoluti di sanita' (stretti); il dominio effettivo e' quello della card.
LIMITS = {"power_w": (0.1, 100.0), "distance_km": (100.0, 10_000.0)}
DOMAIN_MARGIN = 0.10  # ammesso fino a min*(1-10%) e max*(1+10%) (feature positive)

_lock = threading.Lock()
_cache: dict[str, Any] = {}  # una sola voce: (versione, sha256) -> sessione ONNX


_registries: dict[str, FileModelRegistry] = {}


def _registry() -> FileModelRegistry:
    """Un registro per directory, costruito una sola volta (niente cleanup/env a ogni chiamata)."""
    directory = default_registry_dir()
    with _lock:
        reg = _registries.get(str(directory))
        if reg is None:
            try:
                reg = FileModelRegistry(directory)
            except (ModelRegistryError, OSError):
                raise PluginError("registro dei modelli non disponibile") from None
            _registries[str(directory)] = reg
        return reg


def _validate(features: Mapping[str, float]) -> list[float]:
    out = []
    for name in FEATURES:
        v = features.get(name)
        if isinstance(v, bool) or not isinstance(v, int | float) or not math.isfinite(v):
            raise InvalidMeasurement(f"{name}: numero finito richiesto")
        lo, hi = LIMITS[name]
        if not lo <= v <= hi:
            raise InvalidMeasurement(f"{name}: fuori dall'intervallo [{lo}, {hi}]")
        out.append(float(v))
    return out


def _check_domain(values: Mapping[str, float], card: Mapping[str, Any]) -> None:
    """Rifiuta (PluginError) ingressi oltre il dominio di addestramento + 10%; senza intervalli
    nella card rifiuta (fail-closed)."""
    metrics = card.get("metrics", {})
    for name, v in values.items():
        lo, hi = metrics.get(f"train_{name}_min"), metrics.get(f"train_{name}_max")
        if lo is None or hi is None:
            raise PluginError("dominio di addestramento assente nella card del modello")
        lo_ok, hi_ok = lo * (1.0 - DOMAIN_MARGIN), hi * (1.0 + DOMAIN_MARGIN)
        if not lo_ok <= v <= hi_ok:
            raise PluginError(
                f"{name}={v}: fuori dal dominio di addestramento [{lo_ok:.4g}, {hi_ok:.4g}]"
            )


class BaselinePredictor:
    def __init__(self, manifest: Manifest | None) -> None:
        self._manifest = manifest

    def _session(self) -> tuple[Any, dict[str, Any]]:
        registry = _registry()
        try:
            promoted = registry.promoted_card()  # fail-closed; rehash solo se il file cambia
            if promoted is None:
                raise PluginError("nessun modello promosso")
            card, key = promoted
            with _lock:
                if _cache.get("key") != key:
                    from backend.plugins.predictor_baseline import training

                    # controllo e uso sulla stessa lettura: i byte verificati sono quelli usati
                    snap = registry.promoted_snapshot()
                    if snap is None:
                        raise PluginError("nessun modello promosso")
                    blob, card, key = snap
                    session = training.make_session(blob)
                    _cache.clear()
                    _cache.update(key=key, session=session, card=card)
                return _cache["session"], _cache["card"]
        except ImportError as e:
            raise PluginError("extra [ml] non installato") from e
        except ModelRegistryError:
            raise PluginError("modello promosso non disponibile") from None

    def predict(self, features: Mapping[str, float]) -> Mapping[str, float]:
        values = _validate(features)
        session, card = self._session()
        _check_domain(dict(zip(FEATURES, values, strict=True)), card)
        try:
            import numpy as np

            from backend.plugins.predictor_baseline.training import onnx_predict
        except ImportError as e:
            raise PluginError("extra [ml] non installato") from e
        y = float(onnx_predict(session, np.array([values]))[0])
        if not math.isfinite(y):
            raise PluginError("previsione non finita")
        return {"link_margin_db": y}

    def model_info(self) -> Mapping[str, Any]:
        _, card = self._session()
        return {
            "version": card["version"],
            "metrics": dict(card["metrics"]),
            "threshold": dict(card["threshold"]),
            "approved_by": card.get("approved_by"),
        }
