# SPDX-License-Identifier: Apache-2.0
class PluginError(Exception): ...


class ManifestError(PluginError): ...


class PluginNotFound(PluginError): ...


class SimulationTimeout(PluginError): ...


class InvalidOutput(PluginError): ...


class InvalidMeasurement(ValueError):
    """Misura/parametro non valido rilevato dalla validazione del plugin: il messaggio e' sicuro da mostrare."""


class ModelRegistryError(Exception):
    """Base degli errori del registro modelli; i messaggi sono sicuri da mostrare."""


class InvalidVersion(ModelRegistryError): ...


class ModelNotFound(ModelRegistryError): ...


class ModelIntegrityError(ModelRegistryError): ...


class PromotionRefused(ModelRegistryError): ...
