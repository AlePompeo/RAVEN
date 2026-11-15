<!-- SPDX-License-Identifier: Apache-2.0 -->
<script lang="ts">
  import { onMount, onDestroy, tick } from 'svelte';
  import SubNav from '../../components/ui/SubNav.svelte';
  import AntennaGuide from './AntennaGuide.svelte';
  import Callout from '../../components/ui/Callout.svelte';
  import { modeNow } from '../../shell/modeState.svelte';
  import { t } from '../../i18n/i18n.svelte';
  import { setPageContext, clearPageContext } from '../../shell/pageContext.svelte';
  import { sanitizeParams } from '../chat/assistant';
  import { normalizeT, scenarioStore } from '../../shell/scenario';
  import TabTime from './TabTime.svelte';
  import TabWindows from './TabWindows.svelte';
  import TabDiffraction from './TabDiffraction.svelte';
  import TabAntenna from './TabAntenna.svelte';
  import TabCompensator from './TabCompensator.svelte';
  import TabParams from './TabParams.svelte';
  import {
    antennaRequest,
    buildRequest,
    DEFAULT_START,
    extraParams,
    fetchCompensation,
    fetchDefaults,
    fetchStatus,
    initialValues,
    hoursText,
    MAX_PROFILE_BYTES,
    parseNumberList,
    parseProfileCsv,
    rateLabel,
    runAnalysis,
    runAntenna,
    syntheticRidgeCsv,
    validateForm,
    type AnalysisResult,
    type ApiFailure,
    type AnalyzeRequest,
    type AntennaReport,
    type Compensation,
    type Defaults,
    type Form,
    type FormErrors,
    type Profile,
    type Status,
  } from './grazing';

  const TABS = [
    { id: 'time', label: 'analysis.page.tabTime' },
    { id: 'windows', label: 'analysis.page.tabWindows' },
    { id: 'diffraction', label: 'analysis.page.tabDiffraction' },
    { id: 'antenna', label: 'analysis.page.tabAntenna' },
    { id: 'compensator', label: 'analysis.page.tabCompensator' },
    { id: 'params', label: 'analysis.page.tabParams' },
  ] as const;
  type TabId = (typeof TABS)[number]['id'];

  /**
   * Learning | Avanzato (docs/design/grazinglink-ux.md). Stessa richiesta e stessi numeri in entrambe: Learning mostra
   * solo i campi essenziali (sito, inizio, durata, stazione, velocità) e due grafici; gli altri campi
   * restano ai loro valori e le schede tecniche sono raggiungibili passando ad Avanzato.
   */
  const ADV_FIELDS = [
    ['tx_gain_dbi', 'analysis.page.txGain'],
    ['tx_power_dbw', 'analysis.page.txPower'],
    ['compensator_k', 'analysis.page.compMargin'],
  ] as const;
  /** Campi visibili anche in Learning: un errore altrove va segnalato, non nascosto. */
  const LEARN_FIELDS = ['site', 'start', 'days'];
  const hiddenError = $derived.by(() => Object.entries(errors).some(([k, v]) => v && !LEARN_FIELDS.includes(k)));
  const adv = $derived(modeNow.advanced);
  const tabs = TABS;

  let loading = $state(true);
  let loadError = $state<ApiFailure | null>(null);
  let status = $state.raw<Status | null>(null);
  let defaults = $state.raw<Defaults | null>(null);

  let siteId = $state('');
  let start = $state(DEFAULT_START);
  let days = $state<number | null>(2);
  let stepMin = $state<number | null>(30);
  let station = $state<'dsn34' | 'dsn18'>('dsn34');
  let mount = $state<'tracking' | 'fixed' | 'gimbal'>('tracking');
  let rate = $state(1e5);
  let values = $state<Record<string, number | null>>({});
  let sweep = $state(false);
  let elStart = $state<number | null>(-1);
  let elEnd = $state<number | null>(3);
  let profile = $state.raw<Profile | null>(null);
  let profileName = $state('');
  let profileError = $state('');
  let syntheticMark = $state(false);
  let diameters = $state('0.1 0.2 0.3 0.5 1.0');
  let antRates = $state('1e4 3e4 1e5 3e5 1e6 3e6');

  let errors = $state<FormErrors>({});
  let running = $state(false);
  let error = $state(false);
  let errorKind = $state<ApiFailure | ''>('');
  let message = $state<'' | 'running' | 'complete'>('');
  let result = $state.raw<AnalysisResult | null>(null);
  let lastReq = $state.raw<AnalyzeRequest | null>(null);
  let usedProfile = $state(false);
  let usedSynthetic = $state(false);
  let comp = $state.raw<Compensation | null>(null);
  let compError = $state<ApiFailure | null>(null);
  let report = $state.raw<AntennaReport | null>(null);
  let antError = $state<ApiFailure | null>(null);
  let tab = $state<TabId>('time');
  const shown = $derived(tab);
  let ctrl: AbortController | null = null;

  const rows = $derived(defaults?.parameters ?? []);
  const translateFailure = (kind: ApiFailure) => t(`analysis.failure.${kind}`);
  const extras = $derived(extraParams(rows));
  const sites = $derived(status?.sites ?? []);
  const covered = $derived(sites.filter((s) => s.dem_covered));
  const row = (k: string) => rows.find((r) => r.key === k);
  const short = (n: string) => n.replace(/\s*\(.*$/, '');

  async function load() {
    loading = true;
    loadError = null;
    const [s, d] = await Promise.all([fetchStatus(fetch), fetchDefaults(fetch)]);
    if (!s.ok || !d.ok) {
      loadError = !s.ok ? s.kind : !d.ok ? d.kind : 'server';
      loading = false;
      return;
    }
    status = s.data;
    defaults = d.data;
    values = initialValues(d.data.parameters);
    rate = (d.data.parameters.find((p) => p.key === 'rate_bps')?.value as number | undefined) ?? 1e5;
    // scenario condiviso (URL o memoria): valori gia' validati dallo store, qui solo applicati
    const sc = scenarioStore().reload();
    if (sc.bitrate !== null && d.data.rates_bps.includes(sc.bitrate)) rate = sc.bitrate;
    if (sc.gain !== null) values.tx_gain_dbi = sc.gain;
    if (sc.k !== null) values.compensator_k = sc.k;
    if (sc.t) start = sc.t.slice(0, 19);
    station = d.data.stations.some((x) => x.key === sc.station) ? sc.station : 'dsn34';
    const first = s.data.sites.find((x) => x.id === sc.site && x.dem_covered) ?? s.data.sites.find((x) => x.dem_covered);
    siteId = first?.id ?? '';
    loading = false;
  }
  onMount(() => void load());
  // scrive lo scenario condiviso quando l'utente cambia sito, inizio, stazione, velocita', guadagno o k
  $effect(() => {
    if (loading || !defaults) return;
    scenarioStore().set({
      site: siteId || null,
      t: normalizeT(start),
      station,
      bitrate: rate,
      gain: values.tx_gain_dbi ?? null,
      k: values.compensator_k ?? null,
    });
  });
  onDestroy(() => {
    ctrl?.abort();
    clearPageContext();
  });

  $effect(() => {
    setPageContext({
      params: sanitizeParams({
        sito: siteId || undefined,
        giorni: days ?? undefined,
        passo_min: stepMin ?? undefined,
        scheda: adv ? tab : 'riepilogo',
        profilo_utente: profile ? 1 : 0,
        ...(result
          ? {
              ore_geometriche: Number(result.windows.geometric_hours.toFixed(1)),
              ore_reali: Number(result.windows.real_hours.toFixed(1)),
              ore_transizione: Number(result.windows.transition_hours.toFixed(1)),
            }
          : {}),
      }),
    });
  });

  async function onFile(e: Event) {
    const input = e.currentTarget as HTMLInputElement;
    const file = input.files?.[0];
    profileError = '';
    if (!file) return;
    if (file.size > MAX_PROFILE_BYTES) {
      profileError = `File troppo grande (massimo ${MAX_PROFILE_BYTES / 1000} kB).`;
      input.value = '';
      return;
    }
    const p = parseProfileCsv(await file.text(), status?.limits.max_profile_points);
    if (!p.ok) {
      profileError = p.error;
      input.value = '';
      return;
    }
    profile = p.profile;
    profileName = file.name;
  }
  function useSynthetic() {
    const p = parseProfileCsv(syntheticRidgeCsv());
    if (!p.ok) return;
    profile = p.profile;
    profileName = 'crinale-sintetico-di-prova.csv';
    syntheticMark = true;
    profileError = '';
  }
  function dropProfile() {
    profile = null;
    profileName = '';
    syntheticMark = false;
    sweep = false;
    profileError = '';
  }

  const form = (): Form => ({ siteId, start, days, stepMin, station, mount, rate, profile, sweep, elStart, elEnd, values });

  async function run(e: SubmitEvent) {
    e.preventDefault();
    if (running || !defaults || !status) return;
    error = false;
    errorKind = '';
    message = '';
    errors = validateForm(form(), rows, status);
    const lists = { d: parseNumberList(diameters, 0.01, 100), r: parseNumberList(antRates, 1e2, 1e10) };
    if (!lists.d) errors = { ...errors, diameters: 'Fino a 12 diametri tra 0,01 e 100 m, separati da spazi.' };
    if (!lists.r) errors = { ...errors, antRates: 'Fino a 12 velocità tra 100 bit/s e 10 Gbit/s, separate da spazi.' };
    const keys = Object.keys(errors).filter((k) => errors[k]);
    if (keys.length) {
      error = true;
      await tick();
      const k = keys[0] as string;
      document.getElementById(k.startsWith('p-') ? k : `f-${k}`)?.focus();
      return;
    }
    const req = buildRequest(form(), rows);
    running = true;
    message = 'running';
    ctrl?.abort();
    ctrl = new AbortController();
    const signal = ctrl.signal;
    const r = await runAnalysis(fetch, req, signal);
    if (signal.aborted) return;
    running = false;
    if (!r.ok) {
      message = '';
      error = true;
      errorKind = r.kind;
      return;
    }
    result = r.data;
    lastReq = req;
    usedProfile = profile !== null;
    usedSynthetic = syntheticMark && profile !== null;
    tab = 'time';
    message = 'complete';
    report = null;
    antError = null;
    void loadExtras(r.data, signal, lists.r as number[], lists.d as number[]);
  }

  async function loadExtras(res: AnalysisResult, signal: AbortSignal, rates: number[], dia: number[]) {
    if (!comp) {
      const c = await fetchCompensation(fetch);
      if (c.ok) {
        comp = c.data;
        compError = null;
      } else compError = c.kind;
    }
    const a = await runAntenna(fetch, antennaRequest(res, station, rates, dia), signal);
    if (signal.aborted) return;
    if (a.ok) report = a.data;
    else antError = a.kind;
  }

  /* schede ARIA: frecce, Home, Fine; l'attivazione segue il focus */
  function onTabKey(e: KeyboardEvent) {
    const i = tabs.findIndex((t) => t.id === shown);
    const next = e.key === 'ArrowRight' ? i + 1 : e.key === 'ArrowLeft' ? i - 1 : e.key === 'Home' ? 0 : e.key === 'End' ? tabs.length - 1 : null;
    if (next === null) return;
    e.preventDefault();
    const t = tabs[(next + tabs.length) % tabs.length]!;
    tab = t.id;
    void tick().then(() => document.getElementById(`tab-${t.id}`)?.focus());
  }
</script>

<SubNav title={t('title.analyze')} learn={t('analysis.page.learn')} />
<div class="container container--wide"><AntennaGuide /></div>
<p class="experiment-scope" role="note">{t('grazing.experimentScope')}</p>

<div class="workspace tile tile--alt">
  <div class="container container--wide">
    {#if loading}
      <p role="status">{t('analysis.page.loading')}</p>
    {:else if loadError}
      <p role="alert">{t(`analysis.failure.${loadError}`)}</p>
      <p><button type="button" class="btn--primary" onclick={load}>{t('analysis.page.retry')}</button></p>
    {:else if defaults && status}
      <Callout title={t('analysis.page.introTitle')} id="intro">
        {#if adv}
          <p>
            {t('analysis.page.introAdvanced')}
          </p>
        {:else}
          <p>{t('analysis.page.introSimple')}</p>
        {/if}
        <p data-testid="illustrative-note">
          <strong>{t('analysis.page.radioAssumptions')}</strong>: {t('analysis.page.radioAssumptionsDetail')}
        </p>
      </Callout>

      {#if !status.dem.available}
        <p role="alert" class="notice" data-testid="dem-missing">
          {t('analysis.page.demMissing')}
        </p>
      {/if}

      <form class="panel setup" onsubmit={run} novalidate aria-labelledby="setup-h">
        <h2 id="setup-h">Scenario</h2>
        <div class="grid">
          <p class="field">
            <label for="f-site">{t(adv ? 'analysis.page.site' : 'analysis.page.simpleSite')}</label>
            <select id="f-site" bind:value={siteId} disabled={sweep} aria-invalid={errors.site ? 'true' : undefined} aria-describedby="f-site-hint{errors.site ? ' f-site-err' : ''}">
              {#each sites as s (s.id)}
                <option value={s.id} disabled={!s.dem_covered && !profile}>
                  {short(s.name)} ({s.lat_deg.toFixed(1)}°){s.dem_covered ? '' : ` - ${t('analysis.page.outsideDem')}`}
                </option>
              {/each}
            </select>
            <span id="f-site-hint" class="hint">
              {t('analysis.page.coverage', { covered: covered.length, total: sites.length, coverage: status.dem.product.coverage })}
            </span>
            {#if errors.site}<span id="f-site-err" class="field-error">{errors.site}</span>{/if}
          </p>
          <p class="field">
            <label for="f-start">{adv ? t('analysis.page.startUtc') : t('analysis.start')}</label>
            <input id="f-start" type="datetime-local" step="1" bind:value={start} aria-invalid={errors.start ? 'true' : undefined} aria-describedby={errors.start ? 'f-start-err' : undefined} />
            {#if errors.start}<span id="f-start-err" class="field-error">{errors.start}</span>{/if}
          </p>
          <p class="field">
            <label for="f-days">{t(adv ? 'analysis.page.duration' : 'analysis.page.simpleDays')}</label>
            <input id="f-days" type="number" inputmode="decimal" step="any" bind:value={days} aria-invalid={errors.days ? 'true' : undefined} aria-describedby={errors.days ? 'f-days-err' : undefined} />
            {#if errors.days}<span id="f-days-err" class="field-error">{errors.days}</span>{/if}
          </p>
          {#if adv}
          <p class="field">
            <label for="f-step">{t('analysis.page.step')}</label>
            <input id="f-step" type="number" inputmode="decimal" step="any" bind:value={stepMin} aria-invalid={errors.step ? 'true' : undefined} aria-describedby={errors.step ? 'f-step-err' : undefined} />
            {#if errors.step}<span id="f-step-err" class="field-error">{errors.step}</span>{/if}
          </p>
          {/if}
        </div>

        {#if adv}
        <fieldset class="profile">
          <legend>{t('analysis.page.profile')}</legend>
          <p class="hint">
            {t('analysis.page.profileHelp', { points: status.limits.max_profile_points, size: MAX_PROFILE_BYTES / 1000 })}
          </p>
          <p class="field">
            <label for="f-profile">{t('analysis.page.csvFile')}</label>
            <input id="f-profile" type="file" accept=".csv,.txt,text/csv,text/plain" onchange={onFile} aria-describedby={profileError ? 'f-profile-err' : undefined} aria-invalid={profileError ? 'true' : undefined} />
            {#if profileError}<span id="f-profile-err" class="field-error" role="alert">{profileError}</span>{/if}
          </p>
          <p class="inline">
            <button type="button" onclick={useSynthetic}>{t('analysis.page.useSynthetic')}</button>
            {#if profile}<button type="button" onclick={dropProfile}>{t('analysis.page.removeProfile')}</button>{/if}
          </p>
          {#if profile}
            <p role="status" data-testid="profile-loaded">{t('analysis.page.profileLoaded', { name: profileName, count: profile.distance_m.length, distance: profile.distance_m[profile.distance_m.length - 1] ?? 0 })}</p>
            <label class="check"><input type="checkbox" bind:checked={syntheticMark} /> {t('analysis.page.syntheticProfile')}</label>
            <label class="check"><input id="f-sweep" type="checkbox" bind:checked={sweep} /> {t('analysis.page.useSweep')}</label>
            {#if sweep}
              <div class="grid">
                <p class="field">
                  <label for="f-elStart">{t('analysis.page.elevationStart')}</label>
                  <input id="f-elStart" type="number" step="any" bind:value={elStart} aria-invalid={errors.elStart ? 'true' : undefined} />
                  {#if errors.elStart}<span class="field-error">{errors.elStart}</span>{/if}
                </p>
                <p class="field">
                  <label for="f-elEnd">{t('analysis.page.elevationEnd')}</label>
                  <input id="f-elEnd" type="number" step="any" bind:value={elEnd} aria-invalid={errors.elEnd ? 'true' : undefined} />
                  {#if errors.elEnd}<span class="field-error">{errors.elEnd}</span>{/if}
                </p>
              </div>
              <p class="hint">{t('analysis.page.sweepHelp')}</p>
            {/if}
          {/if}
          {#if errors.profile}<span class="field-error">{errors.profile}</span>{/if}
        </fieldset>
        {/if}

        <fieldset>
          <legend>{t(adv ? 'analysis.page.linkAdvanced' : 'analysis.page.link')}</legend>
          <div class="grid">
            <p class="field">
              <label for="f-station">{t(adv ? 'analysis.page.station' : 'analysis.page.simpleStation')}</label>
              <select id="f-station" bind:value={station}>
                {#each defaults.stations as s (s.key)}<option value={s.key}>{s.name}</option>{/each}
              </select>
            </p>
            <p class="field">
              <label for="f-mount">{t('analysis.mount')}</label>
              <select id="f-mount" bind:value={mount}>
                <option value="tracking">{t('analysis.mountTracking')}</option>
                <option value="fixed">{t('analysis.mountFixed')}</option>
                <option value="gimbal">{t('analysis.mountGimbal')}</option>
              </select>
              {#if mount === 'gimbal'}<span class="hint">{t('analysis.gimbalHint')}</span>{/if}
            </p>
            {#each adv ? ADV_FIELDS : [] as [k, label] (k)}
              {@const r = row(k as string)}
              <p class="field">
                <label for="p-{k}">{t(label)}</label>
                <input id="p-{k}" type="number" step="any" inputmode="decimal" min={r?.min ?? undefined} max={r?.max ?? undefined} bind:value={values[k as string]} aria-invalid={errors[`p-${k}`] ? 'true' : undefined} aria-describedby={errors[`p-${k}`] ? `p-${k}-err` : undefined} />
                {#if errors[`p-${k}`]}<span id="p-{k}-err" class="field-error">{errors[`p-${k}`]}</span>{/if}
              </p>
            {/each}
            <p class="field">
              <label for="f-rate">{t(adv ? 'analysis.page.rate' : 'analysis.page.simpleRate')}</label>
              <select id="f-rate" bind:value={rate}>
                {#each defaults.rates_bps as r (r)}<option value={r}>{rateLabel(r)}</option>{/each}
              </select>
            </p>
            {#if adv}
            <p class="field">
              <label for="f-diameters">{t('analysis.page.diameters')}</label>
              <input id="f-diameters" type="text" bind:value={diameters} aria-invalid={errors.diameters ? 'true' : undefined} aria-describedby={errors.diameters ? 'f-diameters-err' : undefined} />
              {#if errors.diameters}<span id="f-diameters-err" class="field-error">{errors.diameters}</span>{/if}
            </p>
            <p class="field">
              <label for="f-antRates">{t('analysis.page.antennaRates')}</label>
              <input id="f-antRates" type="text" bind:value={antRates} aria-invalid={errors.antRates ? 'true' : undefined} aria-describedby={errors.antRates ? 'f-antRates-err' : undefined} />
              {#if errors.antRates}<span id="f-antRates-err" class="field-error">{errors.antRates}</span>{/if}
            </p>
            {/if}
          </div>
          {#if !adv}
            <p class="hint" data-testid="more-in-advanced">{t('analysis.page.moreInAdvanced')}</p>
            {#if hiddenError}<p class="field-error" role="alert">{t('analysis.page.hiddenError')}</p>{/if}
          {:else}
          <details class="more">
            <summary>{t('analysis.page.extraParams', { count: extras.length })}</summary>
            <div class="grid">
              {#each extras as r (r.key)}
                <p class="field">
                  <label for="p-{r.key}"><code>{r.key}</code> ({r.unit === '-' ? t('analysis.page.dimensionless') : r.unit})</label>
                  <input id="p-{r.key}" type="number" step="any" inputmode="decimal" min={r.min ?? undefined} max={r.max ?? undefined} bind:value={values[r.key]} aria-invalid={errors[`p-${r.key}`] ? 'true' : undefined} aria-describedby={errors[`p-${r.key}`] ? `p-${r.key}-err` : undefined} />
                  {#if errors[`p-${r.key}`]}<span id="p-{r.key}-err" class="field-error">{errors[`p-${r.key}`]}</span>{/if}
                </p>
              {/each}
            </div>
          </details>
          {/if}
        </fieldset>

        <p class="submit">
          <button type="submit" class="btn--primary" aria-disabled={running}>{t(running ? 'analysis.page.running' : 'analysis.page.run')}</button>
        </p>
      </form>

      <div class="results">
        <p class="status" role="status">{message === 'running' ? t('analysis.page.runningDetail') : message === 'complete' && result ? t('analysis.page.completed', { steps: result.window.n_steps }) : ''}</p>
        {#if error}
          <p role="alert" class="notice" data-kind={errorKind}>{errorKind ? t(`analysis.failure.${errorKind}`) : t('analysis.page.invalidForm')}</p>
        {/if}

        {#if result}
          <section class="panel" aria-labelledby="res-h">
            <h2 id="res-h">{t('analysis.page.results')}</h2>
            <p class="muted small">
              {t('analysis.page.resultWindow', { start: result.window.start_utc.replace('T', ' ').replace('Z', ' UTC'), days: result.window.days, step: result.window.step_min, count: result.window.n_steps })}
              {result.site.id ? t('analysis.page.resultSite', { site: result.site.id }) : t('analysis.page.resultSweep')}
              {t('analysis.page.resultLabel', { label: result.label })}
            </p>
            {#if result.flags.terrain.synthetic || usedSynthetic}
              <p class="notice warn" role="note" data-testid="synthetic-banner">{t('analysis.page.syntheticBanner')}</p>
            {/if}
            <dl class="overview" aria-label={t('analysis.summary')} data-testid="analysis-summary">
              <div><dt>{t('analysis.geometry')}</dt><dd data-testid="summary-geometric">{hoursText(result.windows.geometric_hours)}</dd></div>
              <div><dt>{t('analysis.link')}</dt><dd data-testid="summary-link">{hoursText(result.windows.real_hours)}</dd></div>
              <div><dt>{t('analysis.transition')}</dt><dd data-testid="summary-transition">{hoursText(result.windows.transition_hours)}</dd></div>
            </dl>
            {#if !adv}
              <div data-testid="learning-charts">
                <TabTime {result} simple />
                <TabWindows {result} simple />
              </div>
            {:else}
            <div class="tablist" role="tablist" aria-label={t('analysis.page.analysisResults')} tabindex="-1">
              {#each tabs as item (item.id)}
                <button
                  type="button"
                  role="tab"
                  id="tab-{item.id}"
                  aria-selected={shown === item.id}
                  aria-controls="panel-{item.id}"
                  tabindex={shown === item.id ? 0 : -1}
                  onclick={() => (tab = item.id)}
                  onkeydown={onTabKey}>{t(item.label)}</button
                >
              {/each}
            </div>
            {#each tabs as t (t.id)}
              <div role="tabpanel" id="panel-{t.id}" aria-labelledby="tab-{t.id}" hidden={shown !== t.id} tabindex="0" class="tabpanel">
                {#if shown === t.id}
                  {#if t.id === 'time'}<TabTime {result} />
                  {:else if t.id === 'windows'}<TabWindows {result} />
                  {:else if t.id === 'diffraction'}<TabDiffraction {result} {comp} compError={compError ? translateFailure(compError) : ''} />
                  {:else if t.id === 'antenna'}<TabAntenna {result} {report} error={antError ? translateFailure(antError) : ''} />
                  {:else if t.id === 'compensator'}<TabCompensator {result} />
                  {:else}<TabParams {result} userProfile={usedProfile} syntheticMark={usedSynthetic} />{/if}
                {/if}
              </div>
            {/each}
            <p class="muted small">
              {t('analysis.page.exportRequest')}
              <button type="button" class="linkish" onclick={async () => (await import('./grazing')).downloadText('raven-analisi.json', 'application/json', JSON.stringify({ request: lastReq && { ...lastReq, profile: lastReq.profile ? `${lastReq.profile.distance_m.length} punti` : undefined }, result }, null, 2))}>{t('analysis.page.exportJson')}</button>
            </p>
            {/if}
            <p class="muted small disclaimer">{status.disclaimer}</p>
          </section>
        {:else if !error && !running}
          <section class="panel empty" aria-labelledby="empty-h">
            <h2 id="empty-h">{t('analysis.page.results')}</h2>
            <p class="muted">{t('analysis.page.empty')}</p>
          </section>
        {/if}
      </div>
    {/if}
  </div>
</div>

<style>
  .experiment-scope {
    margin: var(--space-4);
    padding: var(--space-3);
    border-left: 3px solid var(--accent);
    color: var(--text-muted);
  }
  .workspace {
    padding-block: var(--space-5) var(--space-7);
  }
  .setup,
  .results {
    margin-top: var(--space-4);
  }
  .results {
    display: grid;
    grid-template-columns: minmax(0, 1fr);
    gap: var(--space-3);
    min-width: 0;
  }
  h2 {
    font-size: var(--fs-h3);
    font-stretch: 100%;
  }
  .grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(13rem, 1fr));
    gap: 0 var(--space-4);
  }
  .field {
    margin-bottom: var(--space-3);
    min-width: 0;
  }
  .field input:not([type='checkbox']),
  .field select {
    width: 100%;
  }
  .hint,
  .small {
    font-size: var(--fs-small);
  }
  .hint {
    display: block;
    color: var(--c-muted);
    margin-top: var(--space-1);
  }
  fieldset {
    margin-top: var(--space-3);
    min-width: 0;
  }
  .inline {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-2);
    margin: 0 0 var(--space-3);
  }
  .check {
    display: flex;
    align-items: flex-start;
    gap: var(--space-2);
    margin: var(--space-2) 0;
  }
  .more summary {
    min-height: var(--target);
    display: flex;
    align-items: center;
    cursor: pointer;
    font-weight: 600;
  }
  .submit {
    margin: var(--space-4) 0 0;
  }
  .status:empty {
    margin: 0;
  }
  .notice {
    border-left: 3px solid var(--c-power);
    padding-left: var(--space-3);
    margin-block: var(--space-3);
  }
  .notice.warn {
    border-left-color: var(--c-danger);
    font-weight: 600;
  }
  .disclaimer {
    color: var(--c-muted);
  }
  .overview {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(min(100%, 12rem), 1fr));
    gap: var(--space-3);
    margin-block: var(--space-4);
  }
  .overview > div {
    border-inline-start: 3px solid var(--c-uplink);
    padding-inline-start: var(--space-3);
  }
  .overview dt {
    color: var(--c-muted);
    font-size: var(--fs-small);
  }
  .overview dd {
    margin: 0;
    font-size: var(--fs-h3);
    font-weight: 600;
    font-variant-numeric: tabular-nums;
  }
  .tablist {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-1);
    border-bottom: 1px solid var(--c-hairline);
    margin: var(--space-3) 0;
  }
  [role='tab'] {
    min-height: var(--target);
    padding: 0 var(--space-3);
    border: 0;
    border-bottom: 3px solid transparent;
    background: transparent;
    color: var(--c-muted);
    font: inherit;
    font-weight: 600;
    cursor: pointer;
    border-radius: var(--radius-xs) var(--radius-xs) 0 0;
  }
  [role='tab'][aria-selected='true'] {
    color: var(--c-text);
    border-bottom-color: var(--c-text);
  }
  .tabpanel {
    min-width: 0;
  }
  /* il testo nascosto (position: absolute) dentro la tabella scorrevole deve restare ritagliato dal contenitore */
  .tabpanel :global(.table-scroll) {
    position: relative;
  }
  .tabpanel[hidden] {
    display: none;
  }
  .linkish {
    min-height: var(--target);
  }
  @media (max-width: 639px) {
    [role='tab'] {
      padding: 0 var(--space-2);
      font-size: var(--fs-small);
    }
  }
</style>
