<!-- SPDX-License-Identifier: Apache-2.0 -->
<!--
  Confronto siti sul modello unico RAVEN (POST /api/raven/compare): classifica lessicografica sulle componenti scelte,
  componenti sempre visibili, nessun punteggio; i siti con componenti ignote stanno a parte con il motivo.
-->
<script lang="ts">
  import { onMount, onDestroy, tick } from 'svelte';
  import { t, type MessageKey } from '../../i18n/i18n.svelte';
  import Callout from '../../components/ui/Callout.svelte';
  import { modeNow } from '../../shell/modeState.svelte';
  import { normalizeT, scenarioStore, withScenario, type Scenario } from '../../shell/scenario';
  import { withBase } from '../../shell/router';
  import { raven, checkBounds, customAsSiteInfo, type CompareIn, type RavenComparison, type RavenSiteInfo } from '../../shell/ravenApi';
  import { RANK_COMPONENTS, orderFrom, rankRows, rankingLine, type RankComponent } from './ravenRanking';

  import { customSites as customStore, isCustomId, type CustomSiteDef } from '../../shell/customSites';
  import CustomSiteControl from '../../shell/CustomSiteControl.svelte';
  let { embedded = false, onRevealSite, onEditStart }: { embedded?: boolean; onRevealSite?: (siteId: string) => void; onEditStart?: () => void } = $props();
  const BASE = import.meta.env.BASE_URL;
  const adv = $derived(modeNow.advanced);

  let loading = $state(true);
  let loadError = $state<MessageKey | ''>('');
  let catalog = $state<RavenSiteInfo[]>([]);
  // siti personalizzati (scenario condiviso): compaiono nell'elenco come quelli del catalogo
  let customList = $state<readonly CustomSiteDef[]>(customStore.get());
  const sites = $derived<RavenSiteInfo[]>([...catalog, ...customList.map(customAsSiteInfo)]);
  let rates = $state<number[]>([1e5]);
  let defaultsDays = 7;
  let defaultsStep = 10;
  let start = $state('2027-04-07T00:00:00');
  let days = $state<number | null>(7);
  let stepMin = $state<number | null>(10);
  let siteIds = $state<string[]>([]);
  let station = $state<'dsn34' | 'dsn18'>('dsn34');
  let rate = $state(1e5);
  let gain = $state<number | null>(null);
  let first = $state<RankComponent>('useful_hours');
  let running = $state(false);
  let error = $state<MessageKey | ''>('');
  let result = $state.raw<RavenComparison | null>(null);
  let lastReq = $state.raw<CompareIn | null>(null);
  let selectedSite = $state<string | null>(null);
  let alive = true;

  const names = $derived(new Map(sites.map((s) => [s.id, s.name.replace(/\s*\(.*$/, '')])));
  const stale = $derived(lastReq !== null && (normalizeT(start) !== normalizeT(lastReq.start_utc) || days !== lastReq.days || stepMin !== lastReq.step_min ||
    station !== (lastReq.station ?? 'dsn34') || rate !== (lastReq.rate_bps ?? 1e5) || [...siteIds].sort().join() !== [...lastReq.site_ids].sort().join()));
  const rows = $derived(result ? rankRows(result.ranking) : []);
  // Learning: ore utili, ore ignote e margine minimo (le componenti dell'ordine predefinito); Avanzato: tutte
  const shownComponents = $derived(adv ? RANK_COMPONENTS : RANK_COMPONENTS.slice(0, 3));

  const sizeError = $derived.by((): MessageKey | '' => {
    if (days === null || stepMin === null) return 'rank.errDays';
    const e = checkBounds({ start_utc: `${normalizeT(start) ?? ''}`, days, step_min: stepMin }, Math.max(1, siteIds.length));
    return e === 'start' ? 'rank.errStart' : e === 'days' ? 'rank.errDays' : e === 'step' ? 'rank.errStep' : e === 'sites' ? 'rank.errSites' : e === 'size' ? 'rank.errSize' : '';
  });

  async function load() {
    const [s, p] = await Promise.all([raven.sites(), raven.parameters()]);
    if (!alive) return;
    if (!s.ok || !p.ok) { loadError = 'rank.errLoad'; loading = false; return; }
    catalog = s.data.sites;
    rates = p.data.defaults.rates_bps;
    defaultsDays = p.data.defaults.window.days;
    defaultsStep = p.data.defaults.window.step_min;
    days = defaultsDays;
    stepMin = defaultsStep;
    gain = (p.data.defaults.rf['tx_gain_dbi'] as number | undefined) ?? 15;
    const sc = embedded ? scenarioStore().get() : scenarioStore().reload();
    if (sc.bitrate !== null && rates.includes(sc.bitrate)) rate = sc.bitrate;
    if (sc.gain !== null) gain = sc.gain;
    if (sc.t) start = sc.t.slice(0, 19);
    station = sc.station;
    // default: the DEM-covered sites that fit the 6000-step cap at the default window; the others stay selectable
    const covered = s.data.sites.filter((x) => x.dem_covered).map((x) => x.id);
    siteIds = sc.site && (s.data.sites.some((x) => x.id === sc.site) || customStore.find(sc.site)) ? [sc.site] : covered;
    loading = false;
  }

  onMount(() => {
    // un sito personalizzato appena aggiunto (da qualunque controllo della pagina) e' selezionato; uno rimosso esce dalla selezione
    let seen = new Set(customStore.get().map((c) => c.id));
    const offCustom = customStore.subscribe((l) => {
      customList = l;
      const fresh = l.filter((c) => !seen.has(c.id)).map((c) => c.id);
      seen = new Set(l.map((c) => c.id));
      siteIds = [...siteIds.filter((id) => !isCustomId(id) || seen.has(id)), ...fresh.filter((id) => !siteIds.includes(id))];
    });
    const store = scenarioStore();
    let previous = store.get();
    selectedSite = previous.site;
    const off = store.subscribe((sc) => {
      selectedSite = sc.site;
      if (embedded) {
        if (sc.site !== previous.site && sc.site && siteIds.length === 1 && sites.some((x) => x.id === sc.site)) siteIds = [sc.site];
        if (sc.t !== previous.t && sc.t) start = sc.t.slice(0, 19);
        if (sc.station !== previous.station) station = sc.station;
        if (sc.bitrate !== previous.bitrate && sc.bitrate !== null) rate = sc.bitrate;
        if (sc.gain !== previous.gain) gain = sc.gain;
      }
      previous = sc;
    });
    void load();
    return () => { off(); offCustom(); };
  });
  onDestroy(() => { alive = false; });

  $effect(() => {
    if (loading) return;
    const tt = normalizeT(start);
    scenarioStore().set({ ...(siteIds.length === 1 ? { site: siteIds[0]! } : {}), ...(tt ? { t: tt } : {}), station, bitrate: rate, gain });
  });

  const toggle = (id: string, on: boolean) => { siteIds = on ? [...siteIds.filter((x) => x !== id), id] : siteIds.filter((x) => x !== id); };

  async function run(e: SubmitEvent) {
    e.preventDefault();
    if (running || loading) return;
    error = '';
    const tt = normalizeT(start);
    if (!tt || sizeError || !siteIds.length || days === null || stepMin === null) {
      error = (!tt ? 'rank.errStart' : sizeError || (!siteIds.length ? 'rank.errSites' : 'rank.errDays'));
      await tick();
      document.getElementById(!tt ? 'g-start' : 'g-days')?.focus();
      return;
    }
    const req: CompareIn = {
      site_ids: [...siteIds], start_utc: tt, days, step_min: stepMin, station, rate_bps: rate,
      ...(gain !== null ? { rf_overrides: { tx_gain_dbi: gain } } : {}), order: orderFrom(first),
    };
    running = true;
    const signal = raven.latest('compare');
    const r = await raven.compare(req, { signal });
    if (!alive || signal.aborted) return;
    running = false;
    if (!r.ok) { error = r.kind === 'invalid' ? 'rank.errInvalid' : r.kind === 'unavailable' ? 'rank.errUnavailable' : 'rank.errServer'; return; }
    result = r.data;
    lastReq = req;
  }

  function scenarioFor(siteId: string): Scenario {
    return { site: siteId, t: lastReq ? normalizeT(lastReq.start_utc) : normalizeT(start), station: lastReq?.station ?? station, gain: lastReq ? ((lastReq.rf_overrides?.['tx_gain_dbi'] as number | undefined) ?? null) : gain, bitrate: lastReq?.rate_bps ?? rate, k: null, mast: null, customSites: [...customStore.get()] };
  }
  const link = (path: string, id: string) => withBase(withScenario(path, scenarioFor(id)), BASE);
  function reveal(id: string) { scenarioStore().set(scenarioFor(id)); onRevealSite?.(id); }
  const fmt = (v: number | null | undefined, digits = 1) => (v === null || v === undefined ? '—' : v.toFixed(digits));
</script>

<div class="workspace tile tile--alt" data-testid="raven-compare">
  <div class="container container--wide">
    {#if loading}
      <p role="status">{t('rank.loading')}</p>
    {:else if loadError}
      <p role="alert">{t(loadError)}</p>
      <p><button type="button" class="btn--primary" onclick={() => { loadError = ''; loading = true; void load(); }}>{t('rank.retry')}</button></p>
    {:else}
      <Callout title={t('rank.calloutTitle')}>
        <p>{t('rank.intro')}</p>
        {#if adv}<p>{t('rank.introAdv')}</p>{/if}
      </Callout>

      <form class="panel setup" onsubmit={run} novalidate aria-labelledby="g-setup-h">
        <h2 id="g-setup-h">{t('rank.scenario')}</h2>
        <div class="grid3">
          <p class="field">
            <label for="g-start">{t('rank.start')}</label>
            <input id="g-start" type="datetime-local" step="1" bind:value={start} onfocus={() => onEditStart?.()} />
          </p>
          <p class="field">
            <label for="g-days">{t('rank.days')}</label>
            <input id="g-days" type="number" inputmode="decimal" step="any" bind:value={days} aria-invalid={sizeError ? 'true' : undefined} aria-describedby={sizeError ? 'g-size-err' : undefined} />
          </p>
          {#if adv}
          <p class="field">
            <label for="g-step">{t('rank.step')}</label>
            <input id="g-step" type="number" inputmode="decimal" step="any" bind:value={stepMin} aria-invalid={sizeError ? 'true' : undefined} aria-describedby={sizeError ? 'g-size-err' : undefined} />
          </p>
          {/if}
        </div>
        {#if sizeError}<p id="g-size-err" class="field-error">{t(sizeError, { max: 1500, total: 6000 })}</p>{/if}
        <div class="grid3">
          <p class="field">
            <label for="g-station">{t('rank.station')}</label>
            <select id="g-station" bind:value={station}><option value="dsn34">DSN 34 m</option><option value="dsn18">DSN 18 m</option></select>
          </p>
          <p class="field">
            <label for="g-rate">{t('rank.rate')}</label>
            <select id="g-rate" bind:value={rate}>{#each rates as r (r)}<option value={r}>{r} bit/s</option>{/each}</select>
          </p>
          {#if adv}
          <p class="field">
            <label for="g-gain">{t('rank.gain')}</label>
            <input id="g-gain" type="number" inputmode="decimal" step="any" min="-10" max="45" bind:value={gain} />
          </p>
          <p class="field">
            <label for="g-first">{t('rank.first')}</label>
            <select id="g-first" bind:value={first}>{#each RANK_COMPONENTS as c (c)}<option value={c}>{t(`rank.c.${c}` as MessageKey)}</option>{/each}</select>
          </p>
          {/if}
        </div>
        <fieldset>
          <legend id="g-sites">{t('rank.sites')}</legend>
          <p class="bulk"><button type="button" onclick={() => (siteIds = sites.map((x) => x.id))}>{t('rank.all')}</button> <button type="button" onclick={() => (siteIds = [])}>{t('rank.none')}</button></p>
          <div class="sites">
            {#each sites as s (s.id)}
              <label class="check"><input type="checkbox" checked={siteIds.includes(s.id)} onchange={(e) => toggle(s.id, e.currentTarget.checked)} />{names.get(s.id)}{#if !s.dem_covered} <span class="muted">({t('rank.noDem')})</span>{/if}</label>
            {/each}
          </div>
        </fieldset>
        {#if !embedded}<CustomSiteControl onadd={(id) => { siteIds = [...siteIds.filter((x) => x !== id), id]; }} />{/if}
        <p class="submit"><button type="submit" class="btn--primary" aria-disabled={running}>{running ? t('rank.running') : t('rank.run')}</button></p>
      </form>

      <div class="results">
        {#if error}<div role="alert" class="err"><p>{t(error, { max: 1500, total: 6000 })}</p></div>{/if}
        {#if result}
          <section class="panel" aria-labelledby="g-rank-h">
            <h2 id="g-rank-h">{t('rank.title')}</h2>
            <p class="muted small" data-testid="rank-stamp">{t('rank.stamp', { version: result.model_version, registry: result.registry_sha256.slice(0, 12) })}</p>
            <p class="small rule" data-testid="ranking-rule">{rankingLine(result.ranking, (c) => t(`rank.c.${c}` as MessageKey), (d) => t(d === 'asc' ? 'rank.lessBetter' : 'rank.moreBetter'))}</p>
            {#if embedded && stale}<p class="small" role="status">{t('sites.outdated')}</p>{/if}
            <!-- svelte-ignore a11y_no_noninteractive_tabindex -->
            <div class="table-scroll" tabindex="0" role="region" aria-labelledby="g-rank-h">
              <table data-testid="rank-table">
                <caption>{t('rank.caption')}</caption>
                <thead>
                  <tr>
                    <th scope="col">#</th><th scope="col">{t('rank.site')}</th>
                    {#each shownComponents as c (c)}<th scope="col" data-component={c}>{t(`rank.c.${c}` as MessageKey)}</th>{/each}
                    {#if adv}<th scope="col">{t('rank.blackout')}</th>{/if}
                    <th scope="col"><span class="sr-only">{t('rank.actions')}</span></th>
                  </tr>
                </thead>
                <tbody>
                  {#each rows as r (r.site_id)}
                    <tr data-site={r.site_id} class:selected={embedded && selectedSite === r.site_id}>
                      <td class="num">{r.rank}</td>
                      <th scope="row">{names.get(r.site_id) ?? r.site_id}{#if r.tied_with.length}<span class="muted small"> ({t('rank.tied', { sites: r.tied_with.map((x) => names.get(x) ?? x).join(', ') })})</span>{/if}</th>
                      <td class="num">{fmt(r.components.useful_hours)}</td>
                      <td class="num">{fmt(r.components.unknown_hours)}</td>
                      <td class="num">{r.components.margin_blocked ? t('rank.blocked') : fmt(r.components.margin_min_db)}</td>
                      {#if adv}<td class="num">{r.components.margin_blocked ? t('rank.blocked') : fmt(r.components.margin_median_db)}</td>
                      <td class="num">{r.components.min_soc === null ? '—' : `${(r.components.min_soc * 100).toFixed(0)} %`}</td>{/if}
                      {#if adv}<td class="num">{r.components.time_to_first_blackout_h === null ? t('rank.noBlackout') : fmt(r.components.time_to_first_blackout_h)}</td>{/if}
                      <td>
                        {#if embedded}
                          <button type="button" aria-pressed={selectedSite === r.site_id} onclick={() => reveal(r.site_id)} aria-label={t('sites.globeFor', { site: names.get(r.site_id) ?? r.site_id })}>{t('sites.globe')}</button>
                        {/if}
                        <a href={link('/mission-planner', r.site_id)}>{t('rank.planner')}</a>
                      </td>
                    </tr>
                  {/each}
                </tbody>
              </table>
            </div>
            {#if result.ranking.not_comparable.length}
              <h3 id="g-nc-h">{t('rank.notComparable')}</h3>
              <ul data-testid="not-comparable" aria-labelledby="g-nc-h">
                {#each result.ranking.not_comparable as n (n.site_id)}
                  <li data-site={n.site_id}><strong>{names.get(n.site_id) ?? n.site_id}</strong>: {n.reasons.join('; ')}
                    {#if embedded}<button type="button" aria-pressed={selectedSite === n.site_id} onclick={() => reveal(n.site_id)} aria-label={t('sites.globeFor', { site: names.get(n.site_id) ?? n.site_id })}>{t('sites.globe')}</button>{/if}</li>
                {/each}
              </ul>
              <p class="small">{t('rank.notComparableHelp')}</p>
            {/if}
            <p class="small">{t('rank.noScore')}</p>
            {#if adv}
              <details>
                <summary>{t('rank.legend')}</summary>
                <dl>{#each Object.entries(result.ranking.components_legend) as [k, v] (k)}<dt>{t(`rank.c.${k}` as MessageKey)}</dt><dd>{v}</dd>{/each}</dl>
                <p class="small">{result.ranking.tie_break}</p>
                <ul>{#each result.sites[0]?.declared_limits ?? [] as l (l)}<li>{l}</li>{/each}</ul>
              </details>
            {/if}
          </section>
        {/if}
      </div>
    {/if}
  </div>
</div>

<style>
  .workspace { padding: 1rem 0; }
  .grid3 { display: grid; grid-template-columns: repeat(auto-fit, minmax(11rem, 1fr)); gap: 0.75rem; }
  .sites { display: flex; flex-wrap: wrap; gap: 0.5rem 1rem; }
  .check { display: inline-flex; gap: 0.35rem; align-items: center; }
  .field-error, .err { color: var(--danger, #b00020); }
  .workspace, .results, .panel { min-width: 0; max-width: 100%; }
  .table-scroll { position: relative; overflow-x: auto; max-width: 100%; }
  th { overflow-wrap: anywhere; }
  table { border-collapse: collapse; width: 100%; }
  th, td { padding: 0.35rem 0.5rem; text-align: left; border-bottom: 1px solid var(--line, #8884); }
  td.num { text-align: right; font-variant-numeric: tabular-nums; }
  tr.selected { background: var(--accent-soft, #8882); }
  .sr-only { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); }
</style>
