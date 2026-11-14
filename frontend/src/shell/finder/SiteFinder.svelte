<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- Automatic site search. The prompt is read by rules (no model, no network beyond this server) into a brief that the user sees and edits in
     the form below; the form is also the way in when nothing was understood. The search runs as a job on the RAVEN core: every proposed
     site was evaluated by the core, the surrogate is shown next to it with its interval, and unknown stays unknown. Tag I (estimate). -->
<script lang="ts">
  import { onDestroy, onMount } from 'svelte';
  import { t, formatNumber, lang } from '../../i18n/i18n.svelte';
  import type { RavenOverlay } from '../ravenApi';
  import { customSites, makeId, MAX_CUSTOM_SITES } from '../customSites';
  import { scenarioStore, withScenario } from '../scenario';
  import { withBase } from '../router';
  import { BASE } from '../../registry';
  import { finder, type Brief, type FinderResult, type LlmStatus, type Parsed, type Proposal, type Summary } from './finderApi';

  // Inside the Mission Planner (`onusesites` given) the found sites are assigned to A and B in place, the period of the planner prefills the
  // brief (`defaults`), and nothing navigates away; elsewhere "Use in the planner" opens the planner on the site.
  type Pick = { p: Proposal; target: 'A' | 'B' };
  let { onresult, onshow, initialText = '', autoRead = false, defaults, onusesites, canB = true }: {
    onresult?: (o: RavenOverlay | null) => void; onshow?: (lat: number, lon: number) => void; initialText?: string; autoRead?: boolean;
    defaults?: { start: string; days: number | null }; onusesites?: (picks: Pick[], brief: Partial<Brief>) => void; canB?: boolean;
  } = $props();

  let text = $state('');
  let parsed = $state.raw<Parsed | null>(null);
  let busyParse = $state(false);
  let useModel = $state(false), external = $state(false);
  let region = $state<'polar' | 'catalogue'>('polar'), first = $state<'useful_fraction' | 'sun_fraction' | 'rf_fraction'>('useful_fraction'), frontOnly = $state(false);
  let date = $state(''), days = $state(''), priority = $state(''), sun = $state(''), rf = $state(''), kbps = $state(''), k = $state('5'), latMax = $state(''), dist = $state('');
  let running = $state(false), evaluated = $state(0), budget = $state(100), elapsed = $state(0);
  let error = $state<'none' | 'busy' | 'failed' | 'network' | 'missing' | 'full'>('none');
  let result = $state.raw<FinderResult | null>(null);
  let timer: ReturnType<typeof setInterval> | null = null;
  // the account of the search (the engine names the best site; a model, if allowed, only explains it) and the state of the local model
  let summary = $state.raw<Summary | null>(null);
  let summaryState = $state<'none' | 'pending' | 'failed'>('none');
  let llm = $state.raw<LlmStatus | null>(null);
  let lastBrief = $state.raw<Partial<Brief>>({});
  const ctl = new AbortController();
  onDestroy(() => { ctl.abort(); if (timer) clearInterval(timer); });
  // opened from the chat of RAVEN SI: the message is read at once (rules, then the assistant model if one is available)
  onMount(() => {
    if (defaults && !initialText) { date = defaults.start.slice(0, 10); days = defaults.days === null ? '' : String(defaults.days); }
    void finder.llmStatus(ctl.signal).then((r) => { if (r.ok) { llm = r.data; if (r.data.installed && r.data.enough_memory && !initialText) useModel = true; } });
    if (initialText) { text = initialText; if (autoRead) { useModel = true; void read(); } }
  });

  const num = (v: string): number | null => (v.trim() === '' || !Number.isFinite(Number(v.replace(',', '.'))) ? null : Number(v.replace(',', '.')));
  function fill(b: Brief) {
    date = b.start_utc ? b.start_utc.slice(0, 10) : ''; days = b.days === null ? '' : String(b.days); priority = b.priority ?? '';
    sun = b.min_sun_percent === null ? '' : String(b.min_sun_percent); rf = b.min_rf_percent === null ? '' : String(b.min_rf_percent);
    kbps = b.rate_bps === null ? '' : String(b.rate_bps / 1000); k = b.k === null ? k : String(b.k);
    latMax = b.lat_max_deg === null ? '' : String(b.lat_max_deg); dist = b.min_distance_km === null ? '' : String(b.min_distance_km);
  }
  const brief = $derived<Partial<Brief>>({
    start_utc: date ? `${date}T00:00:00Z` : null, days: num(days), priority: (priority || null) as Brief['priority'],
    min_sun_percent: num(sun), min_rf_percent: num(rf), rate_bps: num(kbps) === null ? null : num(kbps)! * 1000,
    k: num(k) === null ? null : Math.round(num(k)!), lat_max_deg: num(latMax), min_distance_km: num(dist),
  });
  const rows = $derived<Proposal[]>(!result ? [] : frontOnly && result.pareto ? result.pareto.map((f, i) => ({ rank: i + 1, lat_deg: f.lat_deg, lon_deg_east: f.lon_deg_east, terrain: '', meets_objectives: f.meets_objectives, name: f.name, on_front: true, core: f.core, surrogate: {}, uncertainty: null })) : result.proposals);
  const ready = $derived(!!brief.start_utc && brief.days !== null && !running);

  async function read() {
    busyParse = true; error = 'none';
    const r = await finder.parse(text, ctl.signal, useModel ? { use_model: true, allow_external: external } : {});
    busyParse = false;
    if (r.ok) { parsed = r.data; fill(r.data.brief); } else error = 'network';
  }
  async function run() {
    lastBrief = { ...brief }; error = 'none'; result = null; summary = null; summaryState = 'none'; onresult?.(null); evaluated = 0; elapsed = 0;
    const r = await finder.start(brief, budget, ctl.signal, { region, order: [first] });
    if (!r.ok) { error = r.status === 409 ? 'busy' : r.status === 422 ? 'missing' : 'network'; return; }
    running = true;
    const id = r.data.job_id;
    timer = setInterval(async () => {
      const p = await finder.poll(id, ctl.signal);
      if (!p.ok) { stop(); error = 'network'; return; }
      evaluated = p.data.evaluated; budget = p.data.budget; elapsed = p.data.elapsed_s;
      if (p.data.state === 'done' && p.data.result) { result = p.data.result; onresult?.(p.data.result.suitability); stop(); void account(id); }
      else if (p.data.state === 'failed') { stop(); error = 'failed'; }
    }, 1000);
  }
  async function account(id: string) {
    summaryState = 'pending';
    const r = await finder.summary(id, { use_model: useModel, allow_external: useModel && external, lang: lang.current === 'it' ? 'it' : 'en' }, ctl.signal);
    if (r.ok && r.data.text) { summary = r.data; summaryState = 'none'; } else summaryState = 'failed';
  }
  /** A proposed site becomes a custom site of the scenario and the Mission Planner opens on it (the same way a site added by hand does). */
  function usePlanner(p: Proposal) {
    const list = customSites.get();
    if (list.length >= MAX_CUSTOM_SITES) { error = 'full'; return; }
    const id = makeId(`found ${p.rank}`, new Set(list.map((c) => c.id)));
    const def = { id, name: `Found ${p.rank}`, lat_deg: Number(p.lat_deg.toFixed(4)), lon_deg_east: Number(p.lon_deg_east.toFixed(4)) };
    const store = scenarioStore();
    store.set({ customSites: [...list, def], site: id });
    location.assign(withBase(withScenario('/mission-planner?mp_step=sites', store.get()), BASE));
  }
  function stop() { running = false; if (timer) clearInterval(timer); timer = null; }
  const pc = (v: number | null | undefined) => (v === null || v === undefined ? t('journey.unknown') : `${formatNumber(v * 100, { maximumFractionDigits: 0 })} %`);
  const pm = (m: number | null, h: number | null) => (m === null ? t('journey.unknown') : h === null ? `${pc(m)} ± ${t('journey.unknown')}` : `${pc(m)} ± ${formatNumber(h * 100, { maximumFractionDigits: 0 })}`);
</script>

<section class="finder" aria-labelledby="finder-h" data-testid="site-finder">
  <h2 id="finder-h">{t('finder.title')}</h2>
  <p class="note">{t('finder.intro')}</p>
  <label for="finder-prompt">{t('finder.prompt')}</label>
  <textarea id="finder-prompt" rows="3" maxlength="2000" bind:value={text} placeholder={t('finder.placeholder')}></textarea>
  <label class="check"><input type="checkbox" bind:checked={useModel} /> {t('finder.useModel')}</label>
  {#if useModel}<label class="check"><input type="checkbox" bind:checked={external} /> {t('finder.external')}</label>{/if}
  {#if llm}<p class="note" data-testid="finder-llm">{llm.installed ? (llm.enough_memory ? t('finder.llm.ready', { model: llm.model ?? '' }) : t('finder.llm.memory', { free: llm.free_mb ?? 0, min: llm.min_free_mb })) : t('finder.llm.none')}</p>{/if}
  <button type="button" onclick={read} disabled={!text.trim() || busyParse}>{t('finder.read')}</button>
  {#if parsed}
    <p class="note" role="status" data-testid="finder-parsed">
      {t('finder.understood', { n: parsed.found.length })}
      {#if parsed.unsupported.length}<strong>{t('finder.unsupported')}: {parsed.unsupported.join(', ')}.</strong>{/if}
      {#if parsed.rejected.length}{t('finder.rejected', { fields: parsed.rejected.join(', ') })}{/if}
      {#if parsed.filled_by_model.length}{t('finder.modelFilled', { fields: parsed.filled_by_model.join(', '), model: parsed.model ?? '' })}
      {:else if parsed.model_error}{t('finder.modelError')}
      {:else if parsed.model_available === false}{t('finder.modelNone')}{/if}
    </p>
  {/if}

  <fieldset class="brief" data-testid="finder-brief">
    <legend>{t('finder.brief')}</legend>
    <label>{t('finder.f.date')}<input type="date" bind:value={date} /></label>
    <label>{t('finder.f.days')}<input inputmode="decimal" bind:value={days} /></label>
    <label>{t('finder.f.priority')}
      <select bind:value={priority}><option value="">—</option><option value="sun">{t('finder.p.sun')}</option><option value="earth">{t('finder.p.earth')}</option><option value="radio">{t('finder.p.radio')}</option><option value="balanced">{t('finder.p.balanced')}</option></select></label>
    <label>{t('finder.f.sun')}<input inputmode="decimal" bind:value={sun} /></label>
    <label>{t('finder.f.rf')}<input inputmode="decimal" bind:value={rf} /></label>
    <label>{t('finder.f.rate')}<input inputmode="decimal" bind:value={kbps} /></label>
    <label>{t('finder.f.k')}<input inputmode="numeric" bind:value={k} /></label>
    <label>{t('finder.f.lat')}<input inputmode="decimal" bind:value={latMax} /></label>
    <label>{t('finder.f.dist')}<input inputmode="decimal" bind:value={dist} /></label>
  </fieldset>
  {#if parsed?.unresolved.length}<p class="note">{t('finder.unresolved', { fields: parsed.unresolved.join(', ') })}</p>{/if}

  <div class="brief">
    <label>{t('finder.region')}<select bind:value={region}><option value="polar">{t('finder.r.polar')}</option><option value="catalogue">{t('finder.r.catalogue')}</option></select></label>
    <label>{t('finder.first')}<select bind:value={first}><option value="useful_fraction">{t('finder.c.useful')}</option><option value="sun_fraction">{t('finder.c.sun')}</option><option value="rf_fraction">{t('finder.c.rf')}</option></select></label>
  </div>
  {#if parsed}<p class="note" data-testid="finder-confirm">{t('finder.confirm')}</p>{/if}
  <button type="button" class="primary" onclick={run} disabled={!ready}>{t(parsed ? 'finder.runConfirm' : 'finder.run')}</button>
  {#if running}
    <p role="status" data-testid="finder-progress"><progress max={budget} value={evaluated}></progress> {t('finder.progress', { n: evaluated, max: budget, s: formatNumber(elapsed, { maximumFractionDigits: 0 }) })}</p>
  {/if}
  {#if error !== 'none'}<p role="alert">{t(`finder.err.${error}`)}</p>{/if}

  {#if result}
    <div data-testid="finder-results">
      <h3>{t('finder.report.title')}</h3>
      <div class="account" data-testid="finder-account" aria-live="polite">
        {#if summary?.text}
          <p>{summary.text}</p>
          <p class="note">{summary.text_source === 'model' ? t('finder.report.model', { model: summary.model ?? '' }) : summary.model_note === 'model_text_rejected' ? t('finder.report.rejected') : t('finder.report.template')}</p>
        {:else if summaryState === 'pending'}<p role="status" class="note">{t('finder.report.pending')}</p>
        {:else if summaryState === 'failed'}<p role="status" class="note">{t('finder.report.failed')}</p>{/if}
      </div>
      <h3>{t('finder.results')}</h3>
      <p class="note">{t('finder.summary', { n: result.evaluated, nc: result.not_comparable })} {result.interval}.</p>
      <label class="check"><input type="checkbox" bind:checked={frontOnly} /> {t('finder.frontOnly')}</label>
      <p class="note">{t(frontOnly ? 'finder.frontNote' : 'finder.orderNote', { order: (result.order ?? []).map((k) => t(k === 'useful_fraction' ? 'finder.c.useful' : k === 'sun_fraction' ? 'finder.c.sun' : 'finder.c.rf')).join(' → ') })}</p>
      <table>
        <caption class="visually-hidden">{t('finder.results')}</caption>
        <thead><tr><th scope="col">#</th><th scope="col">{t('finder.c.pos')}</th><th scope="col">{t('finder.c.useful')}</th><th scope="col">{t('finder.c.sun')}</th><th scope="col">{t('finder.c.rf')}</th><th scope="col">{t('finder.c.pred')}</th><th scope="col">{t('finder.c.objectives')}</th><th scope="col">{t('finder.c.prob')}</th><th scope="col"><span class="visually-hidden">{t('finder.c.show')}</span></th></tr></thead>
        <tbody>
          {#each rows as p, i (i)}
            <tr data-testid="finder-row">
              <th scope="row">{p.rank}{#if p.on_front}<span class="front" title={t('finder.front')}> ◆<span class="visually-hidden"> {t('finder.front')}</span></span>{/if}</th>
              <td>{#if p.name}{p.name}<br />{/if}{formatNumber(p.lat_deg, { maximumFractionDigits: 2 })}°, {formatNumber(p.lon_deg_east, { maximumFractionDigits: 1 })}°</td>
              <td>{pc(p.core.useful_fraction)}</td><td>{pc(p.core.sun_fraction)}</td><td>{pc(p.core.rf_fraction)}</td>
              <td>{p.surrogate.useful_fraction ? pm(p.surrogate.useful_fraction.mean, p.surrogate.useful_fraction.half_width) : t('journey.unknown')}</td>
              <td>{p.meets_objectives === null ? t('finder.noObjective') : t(p.meets_objectives ? 'finder.meets' : 'finder.notMeets')}</td>
              <td data-testid="finder-prob">{p.uncertainty && p.uncertainty.p_meet !== null ? `${pc(p.uncertainty.p_meet)} (${pc(p.uncertainty.p_low)} – ${pc(p.uncertainty.p_high)})` : t('journey.unknown')}</td>
              <td><button type="button" onclick={() => onshow?.(p.lat_deg, p.lon_deg_east)}>{t('finder.c.show')}</button>
                {#if onusesites}<button type="button" data-testid="finder-use-a" onclick={() => onusesites([{ p, target: 'A' }], lastBrief)}>{t('finder.useA')}</button>{#if canB} <button type="button" data-testid="finder-use-b" onclick={() => onusesites([{ p, target: 'B' }], lastBrief)}>{t('finder.useB')}</button>{/if}
                {:else}<button type="button" onclick={() => usePlanner(p)}>{t('finder.planner')}</button>{/if}</td>
            </tr>
          {/each}
        </tbody>
      </table>
      {#if onusesites && canB && result.proposals.length >= 2}
        <button type="button" class="primary" data-testid="finder-use-top" onclick={() => onusesites([{ p: result!.proposals[0]!, target: 'A' }, { p: result!.proposals[1]!, target: 'B' }], lastBrief)}>{t('finder.useTop')}</button>
      {/if}
      {#if result.uncertainty_note}
        <p class="note">{result.uncertainty_note}</p>
        <details><summary>{t('finder.spreads')}</summary>
          <ul class="note">{#each result.parameter_spreads as sp}<li>{sp.name}: {sp.kind === 'rel' ? `± ${sp.width * 100} %` : `± ${sp.width}`} ({sp.why})</li>{/each}</ul>
        </details>
      {/if}
      <ul class="note">{#each result.limits as l}<li>{l}</li>{/each}</ul>
    </div>
  {/if}
</section>

<style>
  .finder { display: grid; gap: .6rem; padding: .75rem 1rem; border: 1px solid #9bdfff33; border-radius: .6rem; min-width: 0; }
  h2 { margin: 0; font-size: 1rem; letter-spacing: .08em; text-transform: uppercase; color: #a4dfff; } h3 { margin: .5rem 0 0; }
  textarea { width: 100%; min-height: 4.5rem; } button { min-height: 44px; } .primary { justify-self: start; }
  .brief { display: grid; grid-template-columns: repeat(auto-fit, minmax(11rem, 1fr)); gap: .5rem .9rem; border: 1px solid #9bdfff22; border-radius: .5rem; }
  .brief label { display: grid; gap: .2rem; font-size: .85rem; } .brief input, .brief select { min-height: 44px; }
  table { width: 100%; border-collapse: collapse; font-size: .85rem; } th, td { padding: .35rem .5rem; text-align: left; border-bottom: 1px solid #9bdfff22; font-variant-numeric: tabular-nums; }
  .account { border-left: 3px solid #a4dfff; padding: .1rem .75rem; } .note { color: var(--c-muted); font-size: .8rem; } .front { color: #ffd166; } .check { display: flex; align-items: center; gap: .5rem; min-height: 44px; font-size: .85rem; } progress { width: 10rem; vertical-align: middle; }
</style>
