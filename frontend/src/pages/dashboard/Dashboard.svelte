<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- Mission control: the file manager of the saved Mission Planner sessions on the left, the Lunar Landing Sites Navigator in the
     centre (south-polar map with overlays, 3D Moon, rover scene), the key numbers of the two scenarios on the right and every
     chart in its own panel below. The cursor of the timeline drives the rover scene and the countdowns; the sessions list follows
     the other tabs (storage event). Same data and rules as the Mission Planner: unknown stays unknown. -->
<script lang="ts">
  import { onMount } from 'svelte';
  import { t, formatNumber, type MessageKey } from '../../i18n/i18n.svelte';
  import { BASE } from '../../registry';
  import { withBase } from '../../shell/router';
  import { customSites } from '../../shell/customSites';
  import { downloadText, type ParamRow } from '../compare/lunar';
  import { loadCatalog } from '../planner/ravenAdapter';
  import { DRAFT_KEY, RUN_KEY, readDraft, readRun, journeyRequests, requestKey, type JourneyRun } from '../planner/journey';
  import { archiveRun, readHistory, writeHistory, HISTORY_LIMIT, type HistoryEntry } from '../planner/history';
  import JourneyResults from '../planner/JourneyResults.svelte';
  import DashboardNavigator from './DashboardNavigator.svelte';
  import { countdownAt, siteStats, type Countdown } from '../planner/visibilityStats';

  let ready = $state(false);
  let currentRun = $state.raw<JourneyRun | null>(null);
  let entries = $state.raw<HistoryEntry[]>([]);
  let selected = $state('');
  let rows = $state.raw<ParamRow[]>([]);
  let ids = $state<string[]>([]);
  let registry = $state('');
  let version = $state('');
  let stale = $state(true);
  let error = $state<MessageKey | null>(null);
  let historyError = $state<MessageKey | null>(null);
  let message = $state<MessageKey | null>(null);
  let confirmClear = $state(false);
  let scenario = $state(0);
  let index = $state(0);
  let playing = $state(false);
  let siteList = $state.raw<{ id: string; name: string; lat: number; lon: number }[]>([]);
  const planner = (step: string) => withBase(`/mission-planner?mp_step=${step}`, BASE);
  const archived = $derived(entries.find((e) => e.id === selected));
  const run = $derived(selected ? archived ? readRun(JSON.stringify(archived.run), rows, ids, registry) : null : currentRun);
  const evals = $derived(run?.evaluations ?? []);
  const last = $derived(Math.max(0, (evals[0]?.steps?.time_unix.length ?? 1) - 1));

  function choose(id: string) { selected = id; scenario = 0; index = 0; playing = false; message = null; }
  function update(id: string | null) {
    try {
      const latest = readHistory(localStorage);
      if (id !== null && !latest.ok) { historyError = latest.error; return; }
      const next = id !== null && latest.ok ? latest.entries.filter((e) => e.id !== id) : [];
      const result = writeHistory(localStorage, next);
      if (!result.ok) { historyError = result.error; return; }
      entries = result.entries; historyError = null;
      choose(''); confirmClear = false; message = 'history.deleted';
    } catch { historyError = 'history.writeError'; }
  }
  function download() {
    if (run) downloadText(`raven-calculation-${run.createdAt.slice(0, 10)}.json`, 'application/json', JSON.stringify(run, null, 2));
  }
  function openSite(id: string) { location.assign(withBase(`/mission-planner?mp_step=sites&site=${encodeURIComponent(id)}`, BASE)); }

  // replay: the timeline cursor advances by itself (shared by the charts, the countdowns and the rover scene)
  $effect(() => {
    if (!playing) return;
    const id = setInterval(() => { index = index >= last ? 0 : index + 1; }, 700);
    return () => clearInterval(id);
  });

  const hours = (v: number | null | undefined) => (v == null ? t('journey.unknown') : `${formatNumber(v, { maximumFractionDigits: 0 })} h`);
  const pct = (v: number | null | undefined) => (v == null ? t('journey.unknown') : `${formatNumber(v * 100, { maximumFractionDigits: 1 })} %`);
  const countText = (c: Countdown | undefined, body: 'sun' | 'earth') =>
    !c || c.visible === null ? t('journey.unknown') : c.status === 'unknown' ? t('journey.changeUnknown') : c.hours === null ? t('journey.noChange')
      : t(body === 'sun' ? (c.visible ? 'journey.nextSunset' : 'journey.nextSunrise') : (c.visible ? 'journey.nextEarthset' : 'journey.nextEarthrise'), { hours: formatNumber(c.hours, { maximumFractionDigits: 1 }) });

  onMount(() => {
    let alive = true;
    const onStorage = (e: StorageEvent) => {
      if (e.storageArea !== localStorage) return;
      try {
        const history = readHistory(localStorage);
        if (history.ok) entries = history.entries;
      } catch { /* unreadable: the list stays as it is */ }
    };
    window.addEventListener('storage', onStorage);
    void (async () => {
      const cat = await loadCatalog();
      if (!alive) return;
      if (!cat.ok) {
        const errors = {
          network: 'planner.errorNetwork', aborted: 'planner.errorNetwork', invalid: 'planner.errorInvalid',
          unavailable: 'planner.errorUnavailable', server: 'planner.errorServer', response: 'planner.errorResponse',
        } as const;
        error = errors[cat.kind]; ready = true; return;
      }
      rows = cat.data.defaults.parameters;
      ids = [...cat.data.sites.map((s) => s.id), ...customSites.get().map((s) => s.id)];
      siteList = [...cat.data.sites.map((s) => ({ id: s.id, name: s.name, lat: s.lat_deg, lon: s.lon_deg_east })),
        ...customSites.get().map((s) => ({ id: s.id, name: s.name, lat: s.lat_deg, lon: s.lon_deg_east }))];
      registry = cat.data.registry_sha256; version = cat.data.model_version;
      let legacy: JourneyRun | null = null;
      try {
        const raw = sessionStorage.getItem(RUN_KEY);
        currentRun = readRun(raw, rows, ids, registry, version);
        legacy = currentRun ?? readRun(raw, rows, ids, registry);
        if (raw && !currentRun) error = 'journey.restoreWarning';
        if (currentRun) {
          const draft = readDraft(sessionStorage.getItem(DRAFT_KEY), rows, ids);
          const requests = draft ? journeyRequests(draft, rows) : null;
          stale = !requests || requestKey(requests) !== currentRun.key;
        }
      } catch { error = 'journey.storageError'; }
      try {
        const history = readHistory(localStorage);
        if (!history.ok) historyError = history.error;
        else {
          entries = history.entries;
          if (!history.exists && legacy) {
            const saved = archiveRun(localStorage, legacy, rows, ids, registry, legacy.evaluations[0]!.model_version);
            if (saved.ok) entries = saved.entries;
            else historyError = saved.error;
          }
          if (!currentRun && entries.length && !error) choose(entries[0]!.id);
        }
      } catch { historyError = 'history.readError'; }
      ready = true;
    })();
    return () => { alive = false; window.removeEventListener('storage', onStorage); };
  });
</script>

<div class="dashboard container container--wide" data-testid="mission-dashboard">
  <header>
    <p class="eyebrow">RAVEN / MISSION CONTROL</p>
    <div class="titlebar"><h1>Dashboard</h1><span class="live" role="status">{t('dash.live')}</span></div>
  </header>
  {#if !ready}<p role="status">{t('planner.loadingSites')}</p>
  {:else}
    {#if error}<p role="alert">{t(error)}</p>{/if}
    <div class="mc">
      <section class="panel kpi" aria-labelledby="kpi-title" data-testid="dashboard-kpi">
        <div class="kpi-head">
          <h2 id="kpi-title">{t('dash.kpi')}</h2>
          {#if run}
            <p class="name"><strong>{run.config.name || t('planner.libraryUnnamed')}</strong> · {run.createdAt.replace('T', ' ')}</p>
            <button type="button" onclick={() => { playing = !playing; }} aria-pressed={playing}>{t(playing ? 'planner.replayPause' : 'planner.replayPlay')}</button>
          {/if}
        </div>
        {#if run}
          {#if !selected && stale}<p class="warning" role="status">{t('journey.stale')}</p>{/if}
          {#if selected && evals[0] && evals[0].model_version !== version}<p class="warning">{t('history.oldModel', { saved: evals[0].model_version, current: version })}</p>{/if}
          <div class="tiles">
            {#each evals as e, i (e.site.id + i)}
              {@const s = siteStats(e)}
              {@const c = countdownAt(e, index)}
              <article class="tile" data-scenario={i === 0 ? 'A' : 'B'}>
                <h3><span class="tag">{i === 0 ? 'A' : 'B'}</span> {e.site.name}</h3>
                <dl>
                  <div><dt>{t('planner.abUseful')}</dt><dd>{hours(e.metrics.useful_hours)}</dd></div>
                  <div><dt>{t('vis.sunMax')}</dt><dd>{s?.sunMaxElDeg == null ? t('journey.unknown') : `${formatNumber(s.sunMaxElDeg, { maximumFractionDigits: 1 })}°`}</dd></div>
                  <div><dt>{t('vis.litH')}</dt><dd>{hours(s?.litH)}</dd></div>
                  <div><dt>{t('vis.earthH')}</dt><dd>{hours(s?.earthH)}</dd></div>
                  <div><dt>{t('planner.socChart')}</dt><dd>{pct(e.metrics.min_soc)}</dd></div>
                  <div><dt>{t('planner.sun')}</dt><dd>{countText(c?.sun, 'sun')}</dd></div>
                  <div><dt>{t('planner.earth')}</dt><dd>{countText(c?.earth, 'earth')}</dd></div>
                </dl>
              </article>
            {/each}
          </div>
        {:else if selected}
          <p role="alert">{t('history.incompatible')}</p>
        {:else}
          <h3>{t('dashboard.emptyTitle')}</h3><p>{t('dashboard.empty')}</p><a href={planner('mission')}>Mission Planner</a>
        {/if}
      </section>

      <div class="panel center">
        <DashboardNavigator sites={siteList} {run} {scenario} {index} onsite={openSite} />
      </div>

      <details class="panel sessions archive" open>
        <summary><h2 id="history-heading">{t('history.title')}</h2></summary>
        <p class="note">{t('history.intro', { limit: HISTORY_LIMIT })}</p>
        {#if historyError}<p role="alert">{t(historyError)}</p>{/if}
        {#if message}<p role="status">{t(message)}</p>{/if}
        <label for="history-selection">{t('history.select')}</label>
        <select id="history-selection" value={selected} onchange={(event) => choose(event.currentTarget.value)}>
          <option value="">{t('history.current')}</option>
          {#each entries as entry (entry.id)}
            <option value={entry.id}>{entry.name || t('planner.libraryUnnamed')} — {entry.savedAt.replace('T', ' ')}</option>
          {/each}
        </select>
        <div class="actions">
          {#if selected}<button type="button" onclick={() => update(selected)}>{t('history.delete')}</button>{/if}
          {#if entries.length || historyError}
            <label><input type="checkbox" bind:checked={confirmClear} /> {t('history.confirmClear')}</label>
            <button type="button" disabled={!confirmClear} onclick={() => update(null)}>{t('history.clear')}</button>
          {/if}
        </div>
        {#if !entries.length && !historyError}<p>{t('history.empty')}</p>{/if}
        {#if run}
          <nav aria-label={t('dashboard.actions')}>
            {#if !selected}<a href={planner('compare')}>{t('journey.compare')}</a>
              {#if !stale}<a href={planner('report')}>{t('journey.prepareReport')}</a>{/if}
            {/if}
            <button type="button" onclick={download}>{t('history.download')}</button>
          </nav>
        {/if}
      </details>

      {#if run}
        <section class="panel wide" aria-labelledby="results-title">
          <h2 id="results-title">{run.config.name || t('planner.libraryUnnamed')}</h2>
          <p class="note">{t(selected ? 'history.snapshot' : 'dashboard.snapshot')}</p>
          {#key selected}<JourneyResults {run} objectives={run.config.objectives} bind:scenario bind:index />{/key}
        </section>
      {/if}
    </div>
  {/if}
</div>

<style>
  .dashboard { padding-block: 2rem 5rem; max-width: none; padding-inline: clamp(.5rem, 1.5vw, 1.5rem); }
  header { margin-bottom: 1.5rem; } h1 { font-family: Orbitron, var(--font-sans); margin: 0; }
  .titlebar { display: flex; align-items: center; gap: 1rem; flex-wrap: wrap; }
  .live { font-size: .75rem; letter-spacing: .08em; text-transform: uppercase; color: #6ee7a8; border: 1px solid #6ee7a866; border-radius: 99px; padding: .15rem .6rem; }
  .eyebrow { color: #a4dfff; font-size: .75rem; letter-spacing: .14em; }
  .mc { display: grid; gap: 1rem; grid-template-columns: minmax(0, 1fr); align-items: start; }
  .kpi-head { display: flex; flex-wrap: wrap; align-items: center; gap: .5rem 1.5rem; } .kpi-head h2, .kpi-head .name { margin: 0; }
  .tiles { display: grid; gap: .75rem; grid-template-columns: repeat(auto-fit, minmax(17rem, 1fr)); }
  summary { cursor: pointer; min-height: 44px; display: flex; align-items: center; } summary h2 { margin: 0; display: inline; }
  .panel { background: linear-gradient(#0b1b2e, #07121f); border: 1px solid #9bdfff40; border-radius: .7rem; padding: 1rem; min-width: 0; box-shadow: inset 0 0 0 1px #0b2238; }
  .panel h2 { margin: 0 0 .6rem; font-size: 1rem; letter-spacing: .08em; text-transform: uppercase; color: #a4dfff; }
  .wide { grid-column: 1 / -1; }
  nav, .actions { display: flex; flex-wrap: wrap; align-items: center; gap: .75rem; margin-block: 1rem; }
  a, button { display: inline-flex; align-items: center; min-height: 44px; }
  select { display: block; width: 100%; min-height: 44px; margin-top: .5rem; }
  .actions label { display: flex; align-items: center; gap: .5rem; min-height: 44px; }
  .note { color: var(--c-muted); font-size: .85rem; } .warning { border-inline-start: 3px solid #d6ba7c; padding: .5rem 1rem; }
  .tile { border: 1px solid #9bdfff30; border-radius: .5rem; padding: .6rem .8rem; margin-top: .75rem; background: #08162700; }
  .tile h3 { margin: 0 0 .4rem; font-size: .95rem; } .tag { display: inline-grid; place-items: center; width: 1.4rem; height: 1.4rem; border-radius: 50%; background: #0b5cad; color: #fff; font-size: .8rem; }
  .tile[data-scenario='B'] .tag { background: #a15c00; }
  dl { margin: 0; } dl div { display: flex; justify-content: space-between; gap: .75rem; padding-block: .2rem; border-bottom: 1px solid #9bdfff1a; }
  dt { color: var(--c-muted); font-size: .8rem; } dd { margin: 0; font-variant-numeric: tabular-nums; text-align: right; }
  .name { margin: 0 0 .4rem; font-size: .85rem; overflow-wrap: anywhere; }
</style>
