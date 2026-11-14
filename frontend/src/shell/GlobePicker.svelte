<!-- SPDX-License-Identifier: Apache-2.0 -->
<!--
  Globo lunare per scegliere un punto con il clic: proiezione ortografica disegnata dalla mappa a colori LROC
  (immagine illustrativa, non un DEM). Si ruota con i pulsanti o con le frecce; le coordinate del punto scelto
  compaiono accanto al globo. I campi numerici restano l'alternativa accessibile.
-->
<script lang="ts">
  import { onMount } from 'svelte';
  import { t } from '../i18n/i18n.svelte';
  import { ASSETS } from '../viewports/bodies/assets';
  import { clampLat, project, unproject, wrap, type View } from './globeProjection';

  let { lat = null, lon = null, onpick, markers = [], onmarker, overlay = null, startLat = -60, size = 280 }: {
    lat?: number | null;
    lon?: number | null;
    onpick: (lat: number, lon: number) => void;
    markers?: readonly { id: string; name: string; lat: number; lon: number }[];
    onmarker?: (id: string) => void;
    /** RGBA raster of the south-polar disc (pole at the centre, longitude clockwise from the top, radius 1 at `limit`) blended over the map. */
    overlay?: { pixels: Uint8ClampedArray; size: number; limit: number } | null;
    startLat?: number;
    size?: number;
  } = $props();

  const SIZE = $derived(size);
  let canvas = $state<HTMLCanvasElement | null>(null);
  // svelte-ignore state_referenced_locally
  let view = $state<View>({ lat0: startLat, lon0: 0 }); // the start latitude is only the first view; the user rotates from there
  let tex: ImageData | null = null;
  let failed = $state(false);

  const hasPoint = $derived(lat !== null && lon !== null && Number.isFinite(lat) && Number.isFinite(lon));

  function draw() {
    const ctx = canvas?.getContext('2d');
    if (!ctx || !tex) return;
    const img = ctx.createImageData(SIZE, SIZE);
    const w = tex.width;
    const h = tex.height;
    for (let py = 0; py < SIZE; py++) {
      for (let px = 0; px < SIZE; px++) {
        const p = unproject(((px + 0.5) / SIZE) * 2 - 1, 1 - ((py + 0.5) / SIZE) * 2, view);
        const o = (py * SIZE + px) * 4;
        if (!p) { img.data[o + 3] = 0; continue; }
        const tx = Math.min(w - 1, Math.max(0, Math.floor(((p.lon + 180) / 360) * w)));
        const ty = Math.min(h - 1, Math.max(0, Math.floor(((90 - p.lat) / 180) * h)));
        const s = (ty * w + tx) * 4;
        img.data[o] = tex.data[s]!; img.data[o + 1] = tex.data[s + 1]!; img.data[o + 2] = tex.data[s + 2]!; img.data[o + 3] = 255;
        if (overlay && p.lat <= overlay.limit) {
          const rho = (90 + p.lat) / (90 + overlay.limit), th = (p.lon * Math.PI) / 180, n = overlay.size;
          const ox = Math.floor(n / 2 + rho * (n / 2) * Math.sin(th)), oy = Math.floor(n / 2 - rho * (n / 2) * Math.cos(th));
          if (ox >= 0 && oy >= 0 && ox < n && oy < n) {
            const q = (oy * n + ox) * 4, a = overlay.pixels[q + 3]! / 255;
            if (a > 0) {
              img.data[o] = img.data[o]! * (1 - a) + overlay.pixels[q]! * a;
              img.data[o + 1] = img.data[o + 1]! * (1 - a) + overlay.pixels[q + 1]! * a;
              img.data[o + 2] = img.data[o + 2]! * (1 - a) + overlay.pixels[q + 2]! * a;
            }
          }
        }
      }
    }
    ctx.putImageData(img, 0, 0);
    for (const marker of markers) {
      const q = project(marker.lat, marker.lon, view);
      if (!q) continue;
      ctx.beginPath();
      ctx.arc((q.x + 1) / 2 * SIZE, (1 - q.y) / 2 * SIZE, 4, 0, Math.PI * 2);
      ctx.fillStyle = '#b7e9ff';
      ctx.fill();
      ctx.strokeStyle = '#081426';
      ctx.lineWidth = 1;
      ctx.stroke();
    }
    if (hasPoint) {
      const q = project(lat!, lon!, view);
      if (q) {
        const cx = ((q.x + 1) / 2) * SIZE;
        const cy = ((1 - q.y) / 2) * SIZE;
        ctx.beginPath(); ctx.arc(cx, cy, 6, 0, 2 * Math.PI);
        ctx.fillStyle = '#e33'; ctx.fill(); ctx.lineWidth = 2; ctx.strokeStyle = '#fff'; ctx.stroke();
      }
    }
  }

  onMount(() => {
    const img = new Image();
    img.onload = () => {
      try {
        const off = document.createElement('canvas');
        off.width = img.naturalWidth; off.height = img.naturalHeight;
        const c = off.getContext('2d');
        if (!c) { failed = true; return; }
        c.drawImage(img, 0, 0);
        tex = c.getImageData(0, 0, off.width, off.height);
        draw();
      } catch { failed = true; }
    };
    img.onerror = () => { failed = true; };
    img.src = ASSETS.moonColor1k.url;
  });

  $effect(() => { void view; void lat; void lon; void markers; void overlay; void SIZE; draw(); });

  function pick(e: MouseEvent) {
    if (!canvas || e.detail === 0) return;
    const r = canvas.getBoundingClientRect();
    if (r.width <= 0 || r.height <= 0) return;
    const x = (e.clientX - r.left) / r.width * SIZE;
    const y = (e.clientY - r.top) / r.height * SIZE;
    let closest: { id: string; distance: number } | null = null;
    for (const marker of markers) {
      const q = project(marker.lat, marker.lon, view);
      if (!q) continue;
      const distance = Math.hypot((q.x + 1) / 2 * SIZE - x, (1 - q.y) / 2 * SIZE - y);
      if (distance < 10 && (!closest || distance < closest.distance)) closest = { id: marker.id, distance };
    }
    if (closest && onmarker) { onmarker(closest.id); return; }
    const p = unproject(((e.clientX - r.left) / r.width) * 2 - 1, 1 - ((e.clientY - r.top) / r.height) * 2, view);
    if (p) onpick(Number(p.lat.toFixed(4)), Number(p.lon.toFixed(4)));
  }
  function rotate(dLat: number, dLon: number) {
    view = { lat0: clampLat(view.lat0 + dLat), lon0: wrap(view.lon0 + dLon) };
  }
  function key(e: KeyboardEvent) {
    const m: Record<string, [number, number]> = { ArrowUp: [15, 0], ArrowDown: [-15, 0], ArrowLeft: [0, -15], ArrowRight: [0, 15] };
    const d = m[e.key];
    if (!d) return;
    e.preventDefault();
    rotate(d[0], d[1]);
  }
</script>

<div class="globe">
  {#if failed}
    <p role="status">{t('custom.globeFailed')}</p>
  {:else}
    <canvas bind:this={canvas} width={SIZE} height={SIZE} tabindex="0" aria-label={t('custom.globeAria')}
      onclick={pick} onkeydown={key} data-testid="globe-canvas"></canvas>
    <div class="rot" role="group" aria-label={t('custom.globeRotate')}>
      <button type="button" onclick={() => rotate(15, 0)} aria-label={t('custom.rotateNorth')}>↑</button>
      <button type="button" onclick={() => rotate(0, -15)} aria-label={t('custom.rotateWest')}>←</button>
      <button type="button" onclick={() => rotate(0, 15)} aria-label={t('custom.rotateEast')}>→</button>
      <button type="button" onclick={() => rotate(-15, 0)} aria-label={t('custom.rotateSouth')}>↓</button>
    </div>
  {/if}
  <p class="picked" aria-live="polite" data-testid="globe-picked">
    {#if hasPoint}{t('custom.picked')} {lat!.toFixed(4)}°, {lon!.toFixed(4)}°{:else}{t('custom.pickHint')}{/if}
  </p>
  <p class="credit">{t('custom.mapCredit')} <a href={ASSETS.moonColor1k.sourcePage}>NASA SVS — LROC</a>.</p>
</div>

<style>
  .globe { display: grid; gap: 0.4rem; justify-items: start; }
  canvas { border-radius: 50%; cursor: crosshair; background: #000; max-width: 100%; height: auto; }
  .rot { display: flex; gap: 0.3rem; }
  .picked { margin: 0; font-variant-numeric: tabular-nums; }
  .credit { margin: 0; font-size: 0.8em; }
</style>
