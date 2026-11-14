// SPDX-License-Identifier: Apache-2.0
// Una sola connessione SSE condivisa tra la barra di navigazione (elemento vivo) e il visualizzatore:
// si apre al primo iscritto e si chiude quando l'ultimo se ne va.
import type { Telemetry } from '../contracts/telemetry';
import { createTelemetryClient, type ConnectionStatus, type TelemetryClient, type TelemetryClientOptions } from '../pages/telemetry/client';

export interface TelemetrySnapshot {
  status: ConnectionStatus | null;
  last: Telemetry | null;
}

type Listener = (s: TelemetrySnapshot) => void;

let client: TelemetryClient | null = null;
let snap: TelemetrySnapshot = { status: null, last: null };
const listeners = new Set<Listener>();
let factory: (o: TelemetryClientOptions) => TelemetryClient = createTelemetryClient;

function emit(): void {
  listeners.forEach((l) => l(snap));
}

export function subscribeTelemetry(fn: Listener): () => void {
  listeners.add(fn);
  fn(snap);
  if (!client) {
    client = factory({
      onSample: (s) => {
        snap = { ...snap, last: s };
        emit();
      },
      onStatus: (s) => {
        snap = { ...snap, status: s };
        emit();
      },
    });
    client.start();
  }
  return () => {
    listeners.delete(fn);
    if (listeners.size === 0 && client) {
      client.stop();
      client = null;
      snap = { status: null, last: snap.last };
    }
  };
}

/** Solo test: sostituisce il client e azzera lo stato. */
export function __setTelemetryFactory(f: typeof factory): void {
  factory = f;
  snap = { status: null, last: null };
}

const nf = (d: number) => new Intl.NumberFormat('it-IT', { minimumFractionDigits: d, maximumFractionDigits: d });

/** Numero con formato italiano e cifre fisse. */
export function formatNumber(v: number, digits = 0): string {
  return nf(digits).format(v);
}

/** Ora UTC hh:mm:ss di un istante ISO (vuoto se non valido). */
export function utcClock(iso: string | Date): string {
  const d = typeof iso === 'string' ? new Date(iso) : iso;
  if (Number.isNaN(d.getTime())) return '';
  return d.toISOString().slice(11, 19);
}
