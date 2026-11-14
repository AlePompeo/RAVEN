// SPDX-License-Identifier: Apache-2.0

export const WEBGL_FALLBACK_MESSAGE =
  'Visualizzazione 3D non disponibile: WebGL non è supportato da questo browser o dispositivo. Usa la descrizione testuale.';

/** WebGL non utilizzabile (nessun contesto, renderer non creabile): lo strato di selezione passa a Canvas 2D. */
export class WebGLUnavailableError extends Error {
  constructor(message = 'WebGL non disponibile', options?: { cause?: unknown }) {
    super(message, options);
    this.name = 'WebGLUnavailableError';
  }
}

/** Nemmeno un contesto Canvas 2D è disponibile: resta solo la descrizione testuale. */
export class Canvas2DUnavailableError extends Error {
  constructor(message = 'Canvas 2D non disponibile') {
    super(message);
    this.name = 'Canvas2DUnavailableError';
  }
}
