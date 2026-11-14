<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- The Moon with the two sites and their coordinates, drawn on ONE canvas (map, graticule, markers, labels). Both sites at or
     south of 60 S: the south-polar view (azimuthal equidistant, the NASA colour map re-projected here); otherwise the whole map.
     The server's CSP does not allow data: images, so the page shows the canvas; the PDF export swaps it for an <img> (reportPdf.ts,
     data-pdf-image). The coordinates are also written as text under the figure. -->
<script lang="ts">
  import { onMount } from 'svelte';
  import { rt } from './reportText';
  import type { RavenEvaluation } from '../../shell/ravenApi';
  import { formatCoordinate } from './reportLink';
  import { pixelFromPolar, renderPolarTexture } from './moonMap';
  import { ASSETS } from '../../viewports/bodies/assets';
  let { evaluations }: { evaluations: readonly RavenEvaluation[] } = $props();

  const SCALE = 2, POLAR = 420, MAPW = 640, MAPH = 320;
  const colors = ['#0b5cad', '#a15c00'];
  const sites = $derived(evaluations.slice(0, 2).map((e, i) => ({ tag: i === 0 ? 'A' : 'B', name: e.site.name, lat: e.site.lat_deg, lon: e.site.lon_deg_east })));
  /** Latitude at the edge of the polar map: 6 degrees beyond the northernmost site, never north of 60 S. */
  const limit = $derived(Math.min(-60, Math.ceil(Math.max(...sites.map((s) => s.lat)) + 6)));
  const ringStep = $derived(-limit < 20 ? 2 : 5);
  const polar = $derived(sites.length > 0 && sites.every((s) => s.lat <= -60));
  const w = $derived((polar ? POLAR : MAPW) * SCALE);
  const h = $derived((polar ? POLAR : MAPH) * SCALE);
  let canvas = $state<HTMLCanvasElement | null>(null);
  let img = $state<HTMLImageElement | null>(null);

  function draw(): void {
    const c = canvas, im = img;
    if (!c || !im) return;
    const ctx = c.getContext('2d');
    if (!ctx) return;
    const W = c.width, H = c.height;
    ctx.fillStyle = '#2b2f36'; ctx.fillRect(0, 0, W, H);
    if (polar) {
      renderPolarTexture(ctx, im, W, H, limit);
      ctx.strokeStyle = 'rgba(255,255,255,0.4)'; ctx.setLineDash([4 * SCALE, 5 * SCALE]); ctx.lineWidth = SCALE;
      for (let lat = -90 + ringStep; lat < limit; lat += ringStep) { ctx.beginPath(); ctx.arc(W / 2, H / 2, ((90 + lat) / (90 + limit)) * (W / 2), 0, 7); ctx.stroke(); }
      ctx.setLineDash([]);
      for (const lon of [0, 90, 180, 270]) {
        ctx.beginPath(); ctx.moveTo(W / 2, H / 2);
        ctx.lineTo(W / 2 + (W / 2) * Math.sin((lon * Math.PI) / 180), H / 2 - (H / 2) * Math.cos((lon * Math.PI) / 180)); ctx.stroke();
      }
      ctx.shadowColor = '#000000'; ctx.shadowBlur = 4 * SCALE;
      ctx.fillStyle = '#ffffff'; ctx.font = `bold ${12 * SCALE}px sans-serif`; ctx.textAlign = 'center';
      ctx.fillText('0°', W / 2, 16 * SCALE); ctx.fillText('180°', W / 2, H - 8 * SCALE);
      ctx.textAlign = 'right'; ctx.fillText('90° E', W - 6 * SCALE, H / 2 - 4 * SCALE);
      ctx.textAlign = 'left'; ctx.fillText('90° W', 6 * SCALE, H / 2 - 4 * SCALE);
      ctx.fillStyle = 'rgba(255,255,255,0.8)'; ctx.textAlign = 'left';
      ctx.fillText(`${limit}°`, W / 2 + 4 * SCALE, 30 * SCALE);
      ctx.shadowBlur = 0;
    } else {
      ctx.drawImage(im, 0, 0, W, H);
    }
    sites.forEach((s, i) => {
      let x: number, y: number;
      if (polar) { const p = pixelFromPolar(s.lat, s.lon, W, H, limit)!; x = p.x; y = p.y; }
      else { x = ((((s.lon + 180) % 360) + 360) % 360 / 360) * W; y = ((90 - s.lat) / 180) * H; }
      ctx.fillStyle = colors[i]!; ctx.strokeStyle = '#ffffff'; ctx.lineWidth = 2 * SCALE;
      ctx.beginPath(); ctx.arc(x, y, 7 * SCALE, 0, 7); ctx.fill(); ctx.stroke();
      ctx.font = `bold ${15 * SCALE}px sans-serif`; ctx.textAlign = 'left'; ctx.lineWidth = 3 * SCALE; ctx.strokeStyle = '#000000';
      ctx.strokeText(s.tag, x + 11 * SCALE, y + 5 * SCALE); ctx.fillStyle = '#ffffff'; ctx.fillText(s.tag, x + 11 * SCALE, y + 5 * SCALE);
    });
  }
  onMount(() => {
    const i = new Image();
    i.onload = () => { img = i; };
    i.src = ASSETS.moonColor2k.url;
  });
  $effect(() => { void sites; void polar; void limit; if (canvas && img) draw(); });
</script>

{#if sites.length}
  <figure class="rp-moon" data-testid="report-moon" aria-label={rt('moon.q')}>
    <figcaption>{rt('moon.q')}</figcaption>
    <canvas bind:this={canvas} width={w} height={h} data-pdf-image aria-label={rt('moon.alt')}></canvas>
    <ul class="rp-legend-line">
      {#each sites as s, i}<li><span style:color={colors[i]}>●</span> <strong>{s.tag}</strong> {s.name}: {formatCoordinate(s.lat, s.lon)}</li>{/each}
      <li>{polar ? rt('moon.polar', { limit: Math.abs(limit) }) : rt('moon.map')}</li>
    </ul>
  </figure>
{/if}

<style>
  .rp-moon { margin: 1rem 0; break-inside: avoid; } figcaption { font-weight: 600; }
  canvas { display: block; width: 100%; max-width: 26rem; height: auto; margin-inline: auto; }
  ul { list-style: none; padding: 0; margin: .5rem 0 0; font-size: .85rem; }
</style>
