// SPDX-License-Identifier: Apache-2.0
// Selezione automatica del renderer: three.js/WebGL se disponibile, altrimenti Canvas 2D;
// solo se manca anche Canvas 2D resta il messaggio testuale. three e canvas2d restano chunk pigri.
import { WEBGL_FALLBACK_MESSAGE } from './errors';
import type { ViewportFactory, ViewportPort } from './port';

export type ViewportMode = 'webgl' | 'canvas2d' | 'none';

export interface SelectOptions {
  /** Notificato quando il renderer effettivo è noto (e se cambia per un fallback a runtime). */
  onMode?: (mode: ViewportMode) => void;
  webglAvailable?: () => boolean;
  three?: ViewportFactory;
  canvas2d?: ViewportFactory;
}

/** Prova robusta: canvas usa-e-getta, webgl2 -> webgl -> experimental-webgl, poi rilascio del contesto. */
export function probeWebGL(): boolean {
  if (typeof document === 'undefined') return false;
  let canvas: HTMLCanvasElement | null = null;
  let gl: WebGLRenderingContext | WebGL2RenderingContext | null = null;
  try {
    canvas = document.createElement('canvas');
    const attrs = { failIfMajorPerformanceCaveat: false };
    for (const name of ['webgl2', 'webgl', 'experimental-webgl'] as const) {
      try {
        gl = canvas.getContext(name, attrs) as WebGLRenderingContext | WebGL2RenderingContext | null;
      } catch {
        gl = null;
      }
      if (gl) break;
    }
    return gl !== null;
  } catch {
    return false;
  } finally {
    try {
      gl?.getExtension('WEBGL_lose_context')?.loseContext();
    } catch {
      /* contesto già perso */
    }
  }
}

let probed: boolean | null = null;
/** The probe creates (and loses) a real WebGL context, which is slow on some drivers: its answer is kept for the page's lifetime. */
export function probeWebGLCached(): boolean {
  if (probed === null) probed = probeWebGL();
  return probed;
}
/** Test hook: forget the cached probe. */
export function resetWebGLProbe(): void {
  probed = null;
}

/** Ultima spiaggia: nessun grafico, resta il messaggio (la descrizione testuale è nella pagina). */
function textPort(): ViewportPort {
  let p: HTMLElement | null = null;
  return {
    mount(el) {
      if (p) return;
      p = document.createElement('p');
      p.setAttribute('role', 'alert');
      p.textContent = WEBGL_FALLBACK_MESSAGE;
      el.appendChild(p);
    },
    update() {},
    dispose() {
      p?.remove();
      p = null;
    },
  };
}

/** Avvolge il viewport primario: se il mount fallisce a runtime passa in modo trasparente al fallback. */
class FallbackPort implements ViewportPort {
  private inner: ViewportPort;
  private el: HTMLElement | null = null;
  private disposed = false;
  private state: unknown;
  private hasState = false;

  constructor(
    primary: ViewportPort,
    private readonly loadFallback: () => Promise<ViewportPort>,
  ) {
    this.inner = primary;
  }

  mount(el: HTMLElement): void {
    if (this.disposed || this.el) return;
    this.el = el;
    try {
      this.inner.mount(el);
    } catch {
      this.inner.dispose();
      this.switchToFallback(el).catch(() => {});
    }
  }

  private async switchToFallback(el: HTMLElement): Promise<void> {
    const p = await this.loadFallback();
    if (this.disposed) {
      p.dispose();
      return;
    }
    this.inner = p;
    p.mount(el);
    if (this.hasState) p.update(this.state);
  }

  update(state: unknown): void {
    if (this.disposed) return;
    this.state = state;
    this.hasState = true;
    this.inner.update(state);
  }

  dispose(): void {
    if (this.disposed) return;
    this.disposed = true;
    this.inner.dispose();
    this.state = undefined;
    this.hasState = false;
    this.el = null;
  }
}

export function selectViewportFactory(opts: SelectOptions = {}): ViewportFactory {
  const notify = opts.onMode ?? (() => {});
  const webglOk = opts.webglAvailable ?? probeWebGLCached;
  const three: ViewportFactory =
    opts.three ?? (async () => (await import('./threeViewport')).threeViewportFactory());
  const canvas2d: ViewportFactory =
    opts.canvas2d ?? (async () => (await import('./canvas2dViewport')).canvas2dViewportFactory());

  /** Canvas 2D se possibile, altrimenti il messaggio testuale: non fallisce mai. */
  const loadFallback = async (): Promise<ViewportPort> => {
    try {
      const p = await canvas2d();
      notify('canvas2d');
      return p;
    } catch {
      notify('none');
      return textPort();
    }
  };

  return async () => {
    if (webglOk()) {
      let primary: ViewportPort | null = null;
      try {
        primary = await three();
      } catch {
        primary = null; // renderer non creabile (WebGLUnavailableError) o chunk non caricabile
      }
      if (primary) {
        notify('webgl');
        return new FallbackPort(primary, loadFallback);
      }
    }
    return loadFallback();
  };
}
