<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- The map overlays of the dashboard as images in the report: height, slope, data coverage, Sun, Earth, Sun and Earth together, longest night,
     longest blackout and the false-colour composite, each with the two sites marked and its own scale. Both sites at or south of 75 S: the
     south-polar disc; otherwise the whole Moon. A cell with no data stays hatched, never coloured as a value. Each map is ONE canvas (scale
     included) that the PDF export swaps for an <img> (reportPdf.ts, data-pdf-image). Table layout: the PDF engine has no CSS grid. -->
<script lang="ts">
  import { onDestroy } from 'svelte';
  import { rt } from './reportText';
  import { raven, type RavenEvaluation, type RavenOverlay } from '../../shell/ravenApi';
  import { overlayPixels, compositePixels, rasterDims, sequentialColor, CATEGORICAL } from '../dashboard/overlayColors';
  import { pixelFromPolar } from './moonMap';
  type Single = 'elevation' | 'slope' | 'coverage' | 'sun' | 'earth' | 'both' | 'sun_gap' | 'earth_gap';
  type Id = Single | 'composite';
  let { evaluations, onready }: { evaluations: readonly RavenEvaluation[]; onready?: (done: boolean) => void } = $props();

  const IDS: Id[] = ['elevation', 'slope', 'coverage', 'sun', 'earth', 'both', 'sun_gap', 'earth_gap', 'composite'];
  const SINGLES: Single[] = IDS.filter((i): i is Single => i !== 'composite');
  const PDF_WIDTH = 205; // CSS px of one picture on the A4 page: three across
  const SCALE = 0.9, LIMIT = -75, STRIP = 38 * SCALE, colors = ['#0b5cad', '#a15c00'];
  const sites = $derived(evaluations.slice(0, 2).map((e, i) => ({ tag: i === 0 ? 'A' : 'B', lat: e.site.lat_deg, lon: e.site.lon_deg_east })));
  const polar = $derived(sites.length > 0 && sites.every((s) => s.lat <= LIMIT));
  let data = $state.raw<Partial<Record<Single, RavenOverlay>>>({});
  let loading = $state(true), failed = $state(false);
  let canvases = $state<Partial<Record<Id, HTMLCanvasElement | null>>>({});

  $effect(() => {
    const scope = polar ? 'polar' : 'global';
    const ctl = new AbortController();
    loading = true; failed = false; data = {};
    void Promise.all(SINGLES.map((l) => raven.overlay(l, { signal: ctl.signal }, scope).then((r) => ({ l, r })))).then((all) => {
      if (ctl.signal.aborted) return;
      const got: Partial<Record<Single, RavenOverlay>> = {};
      for (const { l, r } of all) if (r.ok) got[l] = r.data;
      data = got; failed = Object.keys(got).length === 0; loading = false;
    });
    return () => ctl.abort();
  });
  $effect(() => { onready?.(!loading); });
  onDestroy(() => { onready?.(true); }); // a part that goes away (section switched off, new run) must not leave the PDF waiting for it

  const ref = (id: Id): RavenOverlay | undefined => data[id === 'composite' ? 'sun' : id];
  const have = (id: Id): boolean => (id === 'composite' ? !!(data.sun && data.earth && data.slope) : !!data[id]);
  const label = (id: Id) => rt(`ov.${id}`);
  const classColor = (v: number) => `rgb(${CATEGORICAL[(v - 1) % CATEGORICAL.length]!.join(',')})`;
  const rows = $derived(Array.from({ length: Math.ceil(IDS.length / 3) }, (_, i) => IDS.slice(i * 3, i * 3 + 3)));

  function paint(id: Id): void {
    const c = canvases[id], o = ref(id);
    if (!c || !o || !have(id)) return;
    const ctx = c.getContext('2d');
    if (!ctx) return;
    const px = id === 'composite' ? compositePixels(data.sun!, data.earth!, data.slope!, 1) : overlayPixels(o, 1);
    if (!px) return;
    const { w, h, rect } = rasterDims(o);
    const W = c.width, M = rect ? W / 2 : W; // M: height of the map part, the scale strip is below it
    ctx.fillStyle = '#2b2f36'; ctx.fillRect(0, 0, W, c.height);
    const tmp = document.createElement('canvas'); tmp.width = w; tmp.height = h;
    tmp.getContext('2d')?.putImageData(new ImageData(new Uint8ClampedArray(px), w, h), 0, 0);
    ctx.imageSmoothingEnabled = false; ctx.drawImage(tmp, 0, 0, W, M);
    if (!rect) {
      ctx.strokeStyle = 'rgba(255,255,255,0.45)'; ctx.setLineDash([4 * SCALE, 5 * SCALE]); ctx.lineWidth = SCALE;
      for (const lat of [-80, -85]) { ctx.beginPath(); ctx.arc(W / 2, M / 2, ((90 + lat) / (90 + LIMIT)) * (W / 2), 0, 7); ctx.stroke(); }
      ctx.setLineDash([]);
    }
    sites.forEach((s, i) => {
      const p = rect ? { x: ((((s.lon + 180) % 360) + 360) % 360 / 360) * W, y: ((90 - s.lat) / 180) * M } : pixelFromPolar(s.lat, s.lon, W, M, LIMIT);
      if (!p) return;
      ctx.fillStyle = colors[i]!; ctx.strokeStyle = '#ffffff'; ctx.lineWidth = 2 * SCALE;
      ctx.beginPath(); ctx.arc(p.x, p.y, 8 * SCALE, 0, 7); ctx.fill(); ctx.stroke();
      ctx.font = `bold ${19 * SCALE}px sans-serif`; ctx.textAlign = 'left'; ctx.lineWidth = 3.5 * SCALE; ctx.strokeStyle = '#000000';
      ctx.strokeText(s.tag, p.x + 12 * SCALE, p.y + 7 * SCALE); ctx.fillStyle = '#ffffff'; ctx.fillText(s.tag, p.x + 12 * SCALE, p.y + 7 * SCALE);
    });
    // the scale, drawn in the image so that the PDF carries it
    const y0 = M + 8 * SCALE, bh = 12 * SCALE;
    ctx.font = `${15 * SCALE}px sans-serif`; ctx.fillStyle = '#ffffff'; ctx.textAlign = 'left';
    if (id === 'composite') {
      [['rgb(255,0,0)', rt('ov.compR')], ['rgb(0,255,0)', rt('ov.compG')], ['rgb(0,0,255)', rt('ov.compB')]].forEach(([col, txt], i) => {
        const x = 6 * SCALE + i * (W / 3); ctx.fillStyle = col!; ctx.fillRect(x, y0, bh, bh); ctx.fillStyle = '#ffffff'; ctx.fillText(txt!, x + bh + 4 * SCALE, y0 + bh);
      });
    } else if (o.kind === 'categorical') {
      // class labels are long: the image carries the colours, the labels are written under it
      (o.classes ?? []).forEach((k, i) => {
        ctx.fillStyle = classColor(k.value); ctx.fillRect(6 * SCALE + i * 3 * bh, y0, 2 * bh, bh);
      });
    } else {
      const x0 = 6 * SCALE, bw = W * 0.42;
      for (let k = 0; k < bw; k++) { const [r, g, b] = sequentialColor(k / bw); ctx.fillStyle = `rgb(${r},${g},${b})`; ctx.fillRect(x0 + k, y0, 1, bh); }
      const f = (v: number) => `${Math.round(v * 10) / 10}`;
      ctx.fillStyle = '#ffffff'; ctx.fillText(`${f(o.min)} – ${f(o.max)} ${o.unit}`, x0 + bw + 6 * SCALE, y0 + bh);
    }
  }
  $effect(() => { void data; void canvases; void sites; void polar; for (const id of IDS) paint(id); });
  const sources = $derived(Array.from(new Set(SINGLES.map((l) => data[l]).filter((o): o is RavenOverlay => !!o).map((o) => `${o.source} (tag ${o.tag})`))));
</script>

{#if sites.length && !failed}
  <figure class="rp-overlays" data-testid="report-overlays" aria-label={rt('ov.title')}>
    <figcaption>{rt('ov.title')}</figcaption>
    {#if loading}<p role="status" class="rp-how">{rt('ov.loading')}</p>{/if}
    <table class="rp-ovtable">
      <tbody>
        {#each rows as row}
          <tr>{#each row as id}
            <td>
              {#if have(id)}
                <canvas bind:this={canvases[id]} width={(polar ? 360 : 480) * SCALE} height={(polar ? 360 : 240) * SCALE + STRIP} data-pdf-image data-pdf-width={PDF_WIDTH} aria-label={label(id)}></canvas>
                <span class="cap">{label(id)}</span>
                {#if ref(id)?.kind === 'categorical' && id !== 'composite'}
                  <span class="classes">{#each ref(id)?.classes ?? [] as k}<span><span style:color={classColor(k.value)}>■</span> {k.label}</span>{/each}</span>
                {/if}
              {/if}
            </td>
          {/each}</tr>
        {/each}
      </tbody>
    </table>
    <p class="rp-how">{polar ? rt('ov.polar') : rt('ov.global')} {rt('ov.nodata')}</p>
    {#if sources.length}<p class="rp-how">{rt('ov.sources')}</p><ul class="rp-legend-line">{#each sources as src}<li>{src}</li>{/each}</ul>{/if}
  </figure>
{:else if failed}
  <p role="status" class="rp-how" data-testid="report-overlays-failed">{rt('ov.failed')}</p>
{/if}

<style>
  .rp-overlays { margin: 1rem 0; break-inside: avoid; } figcaption { font-weight: 600; }
  .rp-ovtable { width: 100%; border-collapse: collapse; table-layout: fixed; }
  .rp-ovtable td { width: 33.33%; padding: .25rem; vertical-align: top; text-align: center; }
  canvas { display: block; width: 100%; height: auto; margin-inline: auto; }
  .cap { display: block; font-size: .8rem; font-weight: 600; }
  .classes { display: block; font-size: .7rem; text-align: left; } .classes > span { display: block; }
  ul { list-style: none; padding: 0; margin: .25rem 0 0; font-size: .75rem; }
</style>
