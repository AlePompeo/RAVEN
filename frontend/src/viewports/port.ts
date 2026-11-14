// SPDX-License-Identifier: Apache-2.0

/** Porta verso un modulo di visualizzazione pesante (3D, ...), isolato dalla shell. */
export interface ViewportPort {
  mount(el: HTMLElement): void;
  update(state: unknown): void;
  /** Idempotente: rilascia risorse e listener. */
  dispose(): void;
}

export type ViewportFactory = () => Promise<ViewportPort>;

export interface ViewportHandle {
  update(state: unknown): void;
  dispose(): void;
  /** Risolve quando la factory ha terminato (o è fallita/annullata). */
  ready: Promise<void>;
}

/**
 * Carica il viewport via factory e lo monta. Se `dispose` arriva prima che la factory
 * termini, il viewport creato viene smaltito senza essere montato. Gli errori della
 * factory o di mount sono passati a `onError` (nessuna eccezione non gestita).
 */
export function mountViewport(
  factory: ViewportFactory,
  el: HTMLElement,
  onError: (e: unknown) => void = () => {},
): ViewportHandle {
  let port: ViewportPort | null = null;
  let disposed = false;
  let pending: unknown;
  let hasPending = false;

  const ready = factory().then(
    (p) => {
      if (disposed) {
        p.dispose();
        return;
      }
      port = p;
      try {
        p.mount(el);
        if (hasPending) p.update(pending);
      } catch (e) {
        onError(e);
      }
    },
    (e: unknown) => {
      if (!disposed) onError(e);
    },
  );

  return {
    ready,
    update(state) {
      if (disposed) return;
      if (port) port.update(state);
      else {
        pending = state;
        hasPending = true;
      }
    },
    dispose() {
      if (disposed) return;
      disposed = true;
      hasPending = false;
      pending = undefined;
      port?.dispose();
      port = null;
    },
  };
}
