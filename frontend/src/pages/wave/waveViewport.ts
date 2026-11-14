// SPDX-License-Identifier: Apache-2.0
// Scelta del renderer della pagina Onda 3D, identica a quella del visualizzatore (selectViewportFactory): WebGL se
// disponibile, altrimenti (o se il contesto non si crea) Canvas 2D. Entrambi sono chunk pigri; three è lo stesso del viewer.
import { selectViewportFactory, type ViewportMode } from '../../viewports/select';
import type { ViewportFactory } from '../../viewports/port';

export function waveViewportFactory(onMode: (m: ViewportMode) => void): ViewportFactory {
  return selectViewportFactory({
    onMode,
    three: async () => (await import('./threeWave')).threeWaveFactory(),
    canvas2d: async () => (await import('./canvasWave')).createCanvasWave(),
  });
}
