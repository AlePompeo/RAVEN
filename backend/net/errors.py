# SPDX-License-Identifier: Apache-2.0
"""Errori tipizzati del livello rete. I parser sollevano SOLO sottoclassi di ProtocolError."""


class ProtocolError(ValueError):
    """Dato non valido proveniente dalla rete (framing, intestazione, CRC, indirizzo...).

    Il messaggio non include mai dati grezzi non fidati oltre pochi campi numerici.
    """


class FramingError(ProtocolError):
    """Il flusso non e' delimitabile (es. lunghezza dichiarata oltre il massimo)."""


class OversizeError(ProtocolError):
    """Dimensione dichiarata o effettiva oltre il tetto configurato."""


class CrcError(ProtocolError):
    """Controllo di ridondanza non valido: il frame va scartato e contato."""


class TransportError(Exception):
    """Errore di trasporto (non di protocollo)."""


class TransportClosed(TransportError):
    """Operazione su un trasporto chiuso o non connesso."""


class LimitExceeded(TransportError):
    """Un limite configurato (dimensione messaggio, ...) e' stato superato."""


class NetConfigError(ValueError):
    """Configurazione di rete non valida o non sicura (rifiutata, mai corretta in silenzio)."""
