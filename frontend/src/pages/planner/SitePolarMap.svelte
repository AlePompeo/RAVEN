<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- 2D south-polar map of the candidate sites: click a site to choose it, click anywhere to place a custom point. The sites also
     exist as a list next to the map (keyboard and screen-reader route). Sites north of the limit are not drawn. -->
<script lang="ts">
  import { onMount } from 'svelte';
  import { t } from '../../i18n/i18n.svelte';
  import { ASSETS } from '../../viewports/bodies/assets';
  import { pixelFromPolar, polarFromPixel, renderPolarTexture } from './moonMap';
  let { sites, assigned = {}, picked = null, onmarker, onpick, limit = -60, overlay = null, markerColors = {} }: {
    sites: readonly { id: string; name: string; lat: number; lon: number }[];
    /** Site ids currently used as scenario A / B (drawn with their letter). */
    assigned?: { A?: string; B?: string };
    picked?: { lat: number; lon: number } | null;
    /** Latitude at the rim of the disc (the overlays are drawn for -75). */
    limit?: number;
    /** A canvas covering the whole disc, drawn over the Moon texture (remote-sensing overlay). */
    overlay?: HTMLCanvasElement | null;
    /** Marker fill by site id (a value of the run, never an interpolation). */
    markerColors?: Record<string, string>;
    onmarker: (id: string) => void; onpick: (lat: number, lon: number) => void;
  } = $props();
  const CSS = 420, DPR = 2, PX = CSS * DPR;
  const LIMIT = $derived(limit);
  let canvas = $state<HTMLCanvasElement | null>(null);
  let img = $state<HTMLImageElement | null>(null);
  let texture: HTMLCanvasElement | null = null;
  let textureLimit = 0;

  function draw(): void {
    const c = canvas, im = img;
    const ctx = c?.getContext('2d');
    if (!c || !im || !ctx) return;
    if (!texture || textureLimit !== LIMIT) {
      texture = document.createElement('canvas'); texture.width = PX; texture.height = PX;
      const tc = texture.getContext('2d');
      if (tc) renderPolarTexture(tc, im, PX, PX, LIMIT);
      textureLimit = LIMIT;
    }
    ctx.clearRect(0, 0, PX, PX);
    ctx.fillStyle = '#10151c'; ctx.beginPath(); ctx.arc(PX / 2, PX / 2, PX / 2, 0, 7); ctx.fill();
    ctx.drawImage(texture, 0, 0);
    if (overlay) ctx.drawImage(overlay, 0, 0, PX, PX);
    ctx.strokeStyle = 'rgba(255,255,255,0.35)'; ctx.setLineDash([4 * DPR, 5 * DPR]); ctx.lineWidth = DPR;
    for (let lat = -90 + (-LIMIT < 20 ? 2 : 5); lat < LIMIT; lat += -LIMIT < 20 ? 2 : 5) { ctx.beginPath(); ctx.arc(PX / 2, PX / 2, ((90 + lat) / (90 + LIMIT)) * (PX / 2), 0, 7); ctx.stroke(); }
    ctx.setLineDash([]);
    ctx.shadowColor = '#000000'; ctx.shadowBlur = 4 * DPR; ctx.fillStyle = '#ffffff'; ctx.font = `bold ${12 * DPR}px sans-serif`; ctx.textAlign = 'center';
    ctx.fillText('0°', PX / 2, 16 * DPR); ctx.fillText('180°', PX / 2, PX - 8 * DPR);
    ctx.textAlign = 'right'; ctx.fillText('90° E', PX - 6 * DPR, PX / 2 - 4 * DPR); ctx.textAlign = 'left'; ctx.fillText('90° W', 6 * DPR, PX / 2 - 4 * DPR);
    ctx.shadowBlur = 0;
    for (const s of sites) {
      const p = pixelFromPolar(s.lat, s.lon, PX, PX, LIMIT);
      if (!p) continue;
      const letter = assigned.A === s.id ? 'A' : assigned.B === s.id ? 'B' : '';
      ctx.fillStyle = letter === 'A' ? '#0b5cad' : letter === 'B' ? '#a15c00' : (markerColors[s.id] ?? '#f2f2f2');
      ctx.strokeStyle = letter ? '#ffffff' : '#000000'; ctx.lineWidth = 2 * DPR;
      ctx.beginPath(); ctx.arc(p.x, p.y, (letter ? 7 : 5) * DPR, 0, 7); ctx.fill(); ctx.stroke();
      if (letter) {
        ctx.font = `bold ${14 * DPR}px sans-serif`; ctx.textAlign = 'left'; ctx.lineWidth = 3 * DPR; ctx.strokeStyle = '#000000';
        ctx.strokeText(letter, p.x + 10 * DPR, p.y + 5 * DPR); ctx.fillStyle = '#ffffff'; ctx.fillText(letter, p.x + 10 * DPR, p.y + 5 * DPR);
      }
    }
    if (picked) {
      const p = pixelFromPolar(picked.lat, picked.lon, PX, PX, LIMIT);
      if (p) { ctx.strokeStyle = '#ffd24a'; ctx.lineWidth = 3 * DPR; ctx.beginPath(); ctx.arc(p.x, p.y, 9 * DPR, 0, 7); ctx.stroke(); }
    }
  }
  onMount(() => { const i = new Image(); i.onload = () => { img = i; }; i.src = ASSETS.moonColor2k.url; });
  $effect(() => { void sites; void assigned.A; void assigned.B; void picked; void LIMIT; void overlay; void markerColors; if (canvas && img) draw(); });

  function click(e: MouseEvent): void {
    const c = canvas; if (!c) return;
    const r = c.getBoundingClientRect();
    const x = ((e.clientX - r.left) / r.width) * PX, y = ((e.clientY - r.top) / r.height) * PX;
    let best: { id: string; d: number } | null = null;
    for (const s of sites) {
      const p = pixelFromPolar(s.lat, s.lon, PX, PX, LIMIT);
      if (!p) continue;
      const d = Math.hypot(p.x - x, p.y - y);
      if (d <= 16 * DPR && (!best || d < best.d)) best = { id: s.id, d };
    }
    if (best) { onmarker(best.id); return; }
    const g = polarFromPixel(x, y, PX, PX, LIMIT);
    if (g) onpick(Math.round(g.lat * 1e4) / 1e4, Math.round(g.lon * 1e4) / 1e4);
  }
</script>

<figure class="polar" data-testid="site-polar-map">
  <canvas bind:this={canvas} width={PX} height={PX} aria-label={t('map.polarLabel')} onclick={click}></canvas>
  <figcaption>{t('map.polarHelp', { limit: Math.abs(limit) })}</figcaption>
</figure>

<style>
  .polar { margin: 0; }
  canvas { display: block; width: 100%; max-width: var(--polar-max, 26rem); height: auto; margin-inline: auto; cursor: crosshair; border-radius: 50%; }
  figcaption { font-size: .85rem; color: var(--c-muted); margin-top: .5rem; }
</style>
