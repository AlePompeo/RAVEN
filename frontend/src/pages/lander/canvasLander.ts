// SPDX-License-Identifier: Apache-2.0
// Sezione laterale in Canvas 2D della Scena lander: profilo del terreno LOLA lungo l'azimut della Terra, crinale, linea di
// vista, banda della prima zona di Fresnel (coperta dal terreno, quindi "intersecata" dal crinale), antenna, cono del
// fascio e direzione della Terra. E' il ripiego senza WebGL e anche il pannello "Sezione laterale" in modalita' WebGL.
import { Canvas2DUnavailableError } from '../../viewports/errors';
import type { ViewportPort } from '../../viewports/port';
import { beamDirection, pointing, STATE_INFO } from './model';
import { beamLength, DEG, fresnelBand, sectionLayout, type LanderViewState } from './view';

const DPR_CAP = { hi: 2, lo: 1.5 } as const;
const FONT = '12px system-ui, -apple-system, "Segoe UI", sans-serif';

const fmt = (v: number | null, d = 1, dot = false) => v === null ? '?' : (dot ? v.toFixed(d) : v.toFixed(d).replace('.', ','));
/** Text of the drawing in the language of the page; the report asks for English (`LanderViewState.language`), the site pages keep Italian. */
const LINK_EN: Record<string, string> = { open: 'Open', transition: 'Transition', blocked: 'Blocked', unknown: 'Unknown' };

function rgba(hex: string, a: number): string {
  const n = parseInt(hex.slice(1), 16);
  return `rgba(${(n >> 16) & 255},${(n >> 8) & 255},${n & 255},${a})`;
}

/** Disegna la sezione nel contesto `ctx` di dimensione logica w x h. Esportata per i test. */
export function drawSection(ctx: CanvasRenderingContext2D, w: number, h: number, st: LanderViewState): void {
  ctx.clearRect(0, 0, w, h);
  const bg = ctx.createLinearGradient(0, 0, 0, h);
  bg.addColorStop(0, '#05070b');
  bg.addColorStop(1, '#0d1420');
  ctx.fillStyle = bg;
  ctx.fillRect(0, 0, w, h);
  const s = st.scene;
  const en = st.language === 'en';
  const tx = (it: string, enText: string) => (en ? enText : it);
  const f = (v: number | null, d = 1) => fmt(v, d, en);
  ctx.font = FONT;
  if (!s) {
    ctx.fillStyle = '#a1a1a6';
    ctx.fillText(tx('Calcolo della scena…', 'Computing the scene…'), 16, 28);
    return;
  }
  const L = sectionLayout(s, w, h);
  const info = STATE_INFO[s.link.state];
  const el = s.earth.elDeg * DEG;
  const X = L.toX;
  const Y = L.toY;
  const hAnt = s.antenna.mastM;

  // assi e griglia
  ctx.strokeStyle = 'rgba(255,255,255,0.10)';
  ctx.fillStyle = '#a1a1a6';
  ctx.lineWidth = 1;
  const eStep = niceStep((L.eMax - L.eMin) / 6);
  ctx.textAlign = 'center';
  for (let e = Math.ceil(L.eMin / eStep) * eStep; e <= L.eMax; e += eStep) {
    ctx.beginPath();
    ctx.moveTo(X(e), Y(L.uMax));
    ctx.lineTo(X(e), Y(L.uMin));
    ctx.stroke();
    ctx.fillText(`${Math.round(e)}`, X(e), Y(L.uMin) + 16);
  }
  ctx.textAlign = 'right';
  const uStep = niceStep((L.uMax - L.uMin) / 5);
  for (let u = Math.ceil(L.uMin / uStep) * uStep; u <= L.uMax; u += uStep) {
    ctx.beginPath();
    ctx.moveTo(X(L.eMin), Y(u));
    ctx.lineTo(X(L.eMax), Y(u));
    ctx.stroke();
    ctx.fillText(`${Math.round(u)}`, X(L.eMin) - 6, Y(u) + 4);
  }
  ctx.textAlign = 'center';
  ctx.fillText(tx('distanza lungo l’azimut della Terra e (m)', 'distance along the Earth azimuth e (m)'), (X(L.eMin) + X(L.eMax)) / 2, h - 6);
  ctx.save();
  ctx.translate(12, (Y(L.uMin) + Y(L.uMax)) / 2);
  ctx.rotate(-Math.PI / 2);
  ctx.fillText(tx('quota u (m)', 'height u (m)'), 0, 0);
  ctx.restore();

  // banda della prima zona di Fresnel (sotto il terreno: il crinale la interseca)
  const band = fresnelBand(s);
  ctx.beginPath();
  band.forEach((b, i) => (i ? ctx.lineTo(X(b.e), Y(b.hi)) : ctx.moveTo(X(b.e), Y(b.hi))));
  for (let i = band.length - 1; i >= 0; i--) ctx.lineTo(X(band[i]!.e), Y(band[i]!.lo));
  ctx.closePath();
  ctx.fillStyle = rgba(info.color, 0.3);
  ctx.fill();
  ctx.strokeStyle = rgba(info.color, 0.9);
  ctx.setLineDash([5, 4]);
  ctx.stroke();
  ctx.setLineDash([]);

  // cono del fascio con HPBW vero, rosso oltre HPBW/2 di errore
  const pt = pointing(s, st.errorDeg);
  const dir = beamDirection(s.earth.elDeg, st.errorDeg);
  const Lb = Math.min(beamLength(s), L.eMax / Math.max(0.2, dir[0]));
  const half = s.antenna.hpbwDeg / 2;
  const coneColor = pt.beyond ? STATE_INFO.blocked.color : STATE_INFO.open.color;
  const ang = Math.atan2(dir[1], dir[0]);
  ctx.beginPath();
  ctx.moveTo(X(0), Y(hAnt));
  for (const a of [ang - half * DEG, ang + half * DEG]) ctx.lineTo(X(Lb * Math.cos(a)), Y(hAnt + Lb * Math.sin(a)));
  ctx.closePath();
  ctx.fillStyle = rgba(coneColor, 0.14);
  ctx.fill();
  ctx.strokeStyle = rgba(coneColor, 0.85);
  ctx.stroke();

  // terreno (copre la parte della banda sotto la superficie)
  const pe = s.terrain.profile.e;
  const pu = s.terrain.profile.u;
  ctx.beginPath();
  ctx.moveTo(X(pe[0]!), Y(L.uMin));
  let last = 0;
  for (let i = 0; i < pe.length; i++) {
    if (pe[i]! > L.eMax) break;
    ctx.lineTo(X(pe[i]!), Y(pu[i]!));
    last = i;
  }
  ctx.lineTo(X(pe[last]!), Y(L.uMin));
  ctx.closePath();
  ctx.fillStyle = '#4a4640';
  ctx.fill();
  ctx.beginPath();
  for (let i = 0; i <= last; i++) (i ? ctx.lineTo(X(pe[i]!), Y(pu[i]!)) : ctx.moveTo(X(pe[i]!), Y(pu[i]!)));
  ctx.strokeStyle = '#6ee7ff';
  ctx.lineWidth = 1.6;
  ctx.stroke();
  ctx.lineWidth = 1;

  // linea di vista geometrica verso la Terra
  const eEnd = L.eMax;
  ctx.beginPath();
  ctx.moveTo(X(0), Y(hAnt));
  ctx.lineTo(X(eEnd), Y(hAnt + eEnd * Math.tan(el)));
  ctx.strokeStyle = '#ffffff';
  ctx.lineWidth = 1.5;
  ctx.stroke();
  ctx.lineWidth = 1;

  // antenna: palo e parabola
  ctx.strokeStyle = '#f5f5f7';
  ctx.lineWidth = 2;
  ctx.beginPath();
  ctx.moveTo(X(0), Y(0));
  ctx.lineTo(X(0), Y(hAnt));
  ctx.stroke();
  ctx.beginPath();
  ctx.arc(X(0), Y(hAnt), 5, ang + Math.PI / 2 - 0.0, ang - Math.PI / 2 + 2 * Math.PI, false);
  ctx.stroke();
  ctx.lineWidth = 1;
  ctx.fillStyle = '#fff176';
  ctx.beginPath();
  ctx.arc(X(0), Y(hAnt), 3, 0, 2 * Math.PI);
  ctx.fill();

  // crinale: cima e segmento fino alla linea di vista
  const losAtRidge = hAnt + s.ridge.e * Math.tan(el);
  ctx.strokeStyle = '#ffb340';
  ctx.setLineDash([3, 3]);
  ctx.beginPath();
  ctx.moveTo(X(s.ridge.e), Y(s.ridge.u));
  ctx.lineTo(X(s.ridge.e), Y(losAtRidge));
  ctx.stroke();
  ctx.setLineDash([]);
  ctx.fillStyle = '#ffb340';
  ctx.beginPath();
  ctx.arc(X(s.ridge.e), Y(s.ridge.u), 5, 0, 2 * Math.PI);
  ctx.fill();

  // etichette
  ctx.textAlign = 'left';
  ctx.fillStyle = '#f5f5f7';
  ctx.fillText(`${tx('antenna', 'antenna')} ${f(hAnt, 1)} m`, X(0) + 8, Y(hAnt) - 8);
  ctx.fillStyle = '#ffb340';
  const lx = Math.min(X(s.ridge.e) + 8, X(L.eMax) - 150);
  ctx.fillText(tx(`crinale: h ${f(s.ridge.heightAboveLosM, 1)} m sulla linea, ν ${f(s.ridge.nu, 2)}`, `ridge: h ${f(s.ridge.heightAboveLosM, 1)} m above the line, ν ${f(s.ridge.nu, 2)}`), lx, Math.max(Y(s.ridge.u) - 8, 44));
  ctx.fillStyle = '#ffffff';
  ctx.textAlign = 'right';
  ctx.fillText(tx(`→ Terra a ${f(s.earth.elDeg, 2)}° (${Math.round(s.earth.rangeKm).toLocaleString('it-IT')} km, non in scala)`, `→ Earth at ${f(s.earth.elDeg, 2)}° (${Math.round(s.earth.rangeKm).toLocaleString('en-US')} km, not to scale)`), X(L.eMax), 16);
  ctx.fillStyle = info.color;
  ctx.fillText(tx(`${info.symbol} ${info.label}: margine ${f(s.link.margin, 1)} dB`, `${info.symbol} ${LINK_EN[info.state] ?? info.label}: margin ${f(s.link.margin, 1)} dB`), X(L.eMax), 32);
  ctx.textAlign = 'left';
  ctx.fillStyle = '#a1a1a6';
  ctx.fillText(tx(`scala verticale ×${f(L.exaggeration, L.exaggeration < 10 ? 1 : 0)} rispetto alla orizzontale`, `vertical scale ×${f(L.exaggeration, L.exaggeration < 10 ? 1 : 0)} against the horizontal`), X(L.eMin) + 4, 16);
  ctx.fillStyle = coneColor;
  ctx.fillText(tx(`fascio HPBW ${f(s.antenna.hpbwDeg, 1)}°${st.errorDeg > 0 ? `, errore ${f(st.errorDeg, 1)}°` : ''}`, `beam HPBW ${f(s.antenna.hpbwDeg, 1)}°${st.errorDeg > 0 ? `, error ${f(st.errorDeg, 1)}°` : ''}`), X(L.eMin) + 4, 32);
}

function niceStep(raw: number): number {
  const p = Math.pow(10, Math.floor(Math.log10(Math.max(raw, 1e-9))));
  const m = raw / p;
  return (m < 1.5 ? 1 : m < 3.5 ? 2 : m < 7.5 ? 5 : 10) * p;
}

class CanvasLander implements ViewportPort {
  private el: HTMLElement | null = null;
  private canvas: HTMLCanvasElement | null = null;
  private ctx: CanvasRenderingContext2D | null = null;
  private ro: ResizeObserver | null = null;
  private raf = 0;
  private disposed = false;
  private state: LanderViewState | null = null;
  private frames = 0;

  mount(el: HTMLElement): void {
    if (this.disposed || this.el) return;
    const canvas = document.createElement('canvas');
    const ctx = canvas.getContext('2d');
    if (!ctx) throw new Canvas2DUnavailableError();
    this.el = el;
    this.canvas = canvas;
    this.ctx = ctx;
    canvas.setAttribute('aria-hidden', 'true');
    canvas.style.cssText = 'display:block;width:100%;height:100%';
    el.appendChild(canvas);
    if (typeof ResizeObserver !== 'undefined') {
      this.ro = new ResizeObserver(() => this.schedule());
      this.ro.observe(el);
    }
    this.schedule();
  }

  update(state: unknown): void {
    if (this.disposed) return;
    this.state = state as LanderViewState;
    this.schedule();
  }

  private schedule(): void {
    if (this.disposed || this.raf) return;
    this.raf = requestAnimationFrame(() => {
      this.raf = 0;
      this.render();
    });
  }

  private render(): void {
    const { el, canvas, ctx } = this;
    if (this.disposed || !el || !canvas || !ctx) return;
    const w = Math.max(1, el.clientWidth);
    const h = Math.max(1, el.clientHeight);
    const dpr = Math.min(window.devicePixelRatio || 1, DPR_CAP[this.state?.tier ?? 'hi']);
    if (canvas.width !== Math.round(w * dpr) || canvas.height !== Math.round(h * dpr)) {
      canvas.width = Math.round(w * dpr);
      canvas.height = Math.round(h * dpr);
    }
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    if (this.state) drawSection(ctx, w, h, this.state);
    this.frames++;
    canvas.dataset.frames = String(this.frames);
    canvas.dataset.drawn = this.state?.scene ? '1' : '0';
  }

  dispose(): void {
    if (this.disposed) return;
    this.disposed = true;
    cancelAnimationFrame(this.raf);
    this.ro?.disconnect();
    this.canvas?.remove();
    this.canvas = null;
    this.ctx = null;
    this.el = null;
    this.state = null;
  }
}

export const createCanvasLander = (): ViewportPort => new CanvasLander();
