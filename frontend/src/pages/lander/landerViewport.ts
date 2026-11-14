// SPDX-License-Identifier: Apache-2.0
// Scelta del renderer della Scena lander, come /wave e il visualizzatore: WebGL se disponibile, altrimenti la sezione
// laterale in Canvas 2D. Entrambi sono chunk pigri (three e' lo stesso del visualizzatore).
import { selectViewportFactory, type ViewportMode } from '../../viewports/select';
import type { ViewportFactory } from '../../viewports/port';

export function landerViewportFactory(onMode: (m: ViewportMode) => void): ViewportFactory {
  return selectViewportFactory({
    onMode,
    three: async () => (await import('./threeLander')).threeLanderFactory(),
    canvas2d: async () => (await import('./canvasLander')).createCanvasLander(),
  });
}

/** Il pannello "Sezione laterale": sempre Canvas 2D. */
export const sectionViewportFactory: ViewportFactory = async () => (await import('./canvasLander')).createCanvasLander();
