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
    { id: 'time', label: 'Margine nel tempo' },
    { id: 'windows', label: 'Finestre' },
    { id: 'diffraction', label: 'Diffrazione' },
    { id: 'antenna', label: 'Antenna' },
    { id: 'compensator', label: 'Compensatore' },
    { id: 'params', label: 'Parametri e limiti' },
  ] as const;
  type TabId = (typeof TABS)[number]['id'];

  /**
   * Learning | Avanzato (docs/design/grazinglink-ux.md). Stessa richiesta e stessi numeri in entrambe: Learning mostra
   * solo i campi essenziali (sito, inizio, durata, stazione, velocità) e due grafici; gli altri campi
   * restano ai loro valori e le schede tecniche sono raggiungibili passando ad Avanzato.
   */
  const STR = {
    learn: 'un sito vero del polo Sud per qualche giorno: il grafico dice quanto è forte il segnale verso la Terra e quando si riesce a parlare.',
    introSimple:
      'Dal polo Sud della Luna la Terra è appena sopra l’orizzonte. Scegli un sito e per quanti giorni: RAVEN calcola quando il segnale arriva e con quanto margine.',
    moreInAdvanced: 'Passo, profilo del terreno, antenna e altri parametri sono in Avanzato e mantengono i valori impostati.',
    hiddenError: 'Un parametro visibile solo in Avanzato non è valido: passa ad Avanzato per correggerlo.',
    simple: {
      link: 'Collegamento',
      site: 'Dove (sito al polo Sud)',
      days: 'Per quanti giorni',
      station: 'Antenna sulla Terra',
      rate: 'Quanti dati al secondo',
    },
  } as const;
  const ADV_FIELDS = [
    ['tx_gain_dbi', 'Guadagno antenna rover (dBi)'],
    ['tx_power_dbw', 'Potenza di trasmissione (dBW)'],
    ['compensator_k', 'Margine k del compensatore (σ)'],
  ] as const;
  /** Campi visibili anche in Learning: un errore altrove va segnalato, non nascosto. */
  const LEARN_FIELDS = ['site', 'start', 'days'];
  const hiddenError = $derived.by(() => Object.entries(errors).some(([k, v]) => v && !LEARN_FIELDS.includes(k)));
  const adv = $derived(modeNow.advanced);
  const tabs = TABS;

  let loading = $state(true);
  let loadError = $state('');
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
  let error = $state('');
  let errorKind = $state('');
  let message = $state('');
  let result = $state.raw<AnalysisResult | null>(null);
  let lastReq = $state.raw<AnalyzeRequest | null>(null);
  let usedProfile = $state(false);
  let usedSynthetic = $state(false);
  let comp = $state.raw<Compensation | null>(null);
  let compError = $state('');
  let report = $state.raw<AntennaReport | null>(null);
  let antError = $state('');
  let tab = $state<TabId>('time');
  const shown = $derived(tab);
  let ctrl: AbortController | null = null;

  const rows = $derived(defaults?.parameters ?? []);
  const extras = $derived(extraParams(rows));
  const sites = $derived(status?.sites ?? []);
  const covered = $derived(sites.filter((s) => s.dem_covered));
  const row = (k: string) => rows.find((r) => r.key === k);
  const short = (n: string) => n.replace(/\s*\(.*$/, '');

  async function load() {
    loading = true;
    loadError = '';
    const [s, d] = await Promise.all([fetchStatus(fetch), fetchDefaults(fetch)]);
    if (!s.ok || !d.ok) {
      loadError = (!s.ok ? s.message : !d.ok ? d.message : '') || 'Impossibile caricare siti e parametri.';
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
    error = '';
    errorKind = '';
    message = '';
    errors = validateForm(form(), rows, status);
    const lists = { d: parseNumberList(diameters, 0.01, 100), r: parseNumberList(antRates, 1e2, 1e10) };
    if (!lists.d) errors = { ...errors, diameters: 'Fino a 12 diametri tra 0,01 e 100 m, separati da spazi.' };
    if (!lists.r) errors = { ...errors, antRates: 'Fino a 12 velocità tra 100 bit/s e 10 Gbit/s, separate da spazi.' };
    const keys = Object.keys(errors).filter((k) => errors[k]);
    if (keys.length) {
      error = 'Correggi i campi evidenziati prima di eseguire l’analisi.';
      await tick();
      const k = keys[0] as string;
      document.getElementById(k.startsWith('p-') ? k : `f-${k}`)?.focus();
      return;
    }
    const req = buildRequest(form(), rows);
    running = true;
    message = 'Analisi in corso: efemeridi, profili del terreno e diffrazione possono richiedere alcuni secondi.';
    ctrl?.abort();
    ctrl = new AbortController();
    const signal = ctrl.signal;
    const r = await runAnalysis(fetch, req, signal);
    if (signal.aborted) return;
    running = false;
    if (!r.ok) {
      message = '';
      error = r.message;
      errorKind = r.kind;
      return;
    }
    result = r.data;
    lastReq = req;
    usedProfile = profile !== null;
    usedSynthetic = syntheticMark && profile !== null;
    tab = 'time';
    message = `Analisi completata: ${r.data.window.n_steps} istanti.`;
    report = null;
    antError = '';
    void loadExtras(r.data, signal, lists.r as number[], lists.d as number[]);
  }

  async function loadExtras(res: AnalysisResult, signal: AbortSignal, rates: number[], dia: number[]) {
    if (!comp) {
      const c = await fetchCompensation(fetch);
      if (c.ok) {
        comp = c.data;
        compError = '';
      } else compError = c.message;
    }
    const a = await runAntenna(fetch, antennaRequest(res, station, rates, dia), signal);
    if (signal.aborted) return;
    if (a.ok) report = a.data;
    else antError = a.message;
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

<SubNav title={t('title.analyze')} learn={STR.learn} />
<div class="container container--wide"><AntennaGuide /></div>
<p class="experiment-scope" role="note">{t('grazing.experimentScope')}</p>

<div class="workspace tile tile--alt">
  <div class="container container--wide">
    {#if loading}
      <p role="status">Caricamento di siti e parametri...</p>
    {:else if loadError}
      <p role="alert">{loadError}</p>
      <p><button type="button" class="btn--primary" onclick={load}>Riprova</button></p>
    {:else if defaults && status}
      <Callout title="Collegamento radio con la Terra a 0,5–1,5° dall’orizzonte" id="intro">
        {#if adv}
          <p>
            Dal polo Sud lunare la Terra sta così vicina all’orizzonte che un crinale la nasconde o la sfiora. La geometria dice solo
            «visibile / bloccato»; qui si aggiungono diffrazione, multipath e antenna per calcolare il margine di link nel tempo.
            Risultato: <strong>potenziale nelle ipotesi dichiarate</strong>, non una previsione di missione.
          </p>
        {:else}
          <p>{STR.introSimple}</p>
        {/if}
        <p data-testid="illustrative-note">
          <strong>I parametri radio sono ipotesi illustrative (tag I)</strong>: non c’è alcuna misura radio reale al polo Sud.
          Il terreno viene da LOLA (PDS) o da un profilo fornito da te; mai inventato.
        </p>
      </Callout>

      {#if !status.dem.available}
        <p role="alert" class="notice" data-testid="dem-missing">
          Dati LOLA non disponibili sul server. Per scaricarli esegui «make grazing-dem» (tile in build/lola): finché mancano si può
          analizzare solo con un profilo del terreno caricato da te.
        </p>
      {/if}

      <form class="panel setup" onsubmit={run} novalidate aria-labelledby="setup-h">
        <h2 id="setup-h">Scenario</h2>
        <div class="grid">
          <p class="field">
            <label for="f-site">{adv ? 'Sito' : STR.simple.site}</label>
            <select id="f-site" bind:value={siteId} disabled={sweep} aria-invalid={errors.site ? 'true' : undefined} aria-describedby="f-site-hint{errors.site ? ' f-site-err' : ''}">
              {#each sites as s (s.id)}
                <option value={s.id} disabled={!s.dem_covered && !profile}>
                  {short(s.name)} ({s.lat_deg.toFixed(1)}°){s.dem_covered ? '' : ' - fuori copertura DEM'}
                </option>
              {/each}
            </select>
            <span id="f-site-hint" class="hint">
              {covered.length} di {sites.length} siti sono coperti dal DEM ({status.dem.product.coverage}); gli altri servono un profilo tuo.
            </span>
            {#if errors.site}<span id="f-site-err" class="field-error">{errors.site}</span>{/if}
          </p>
          <p class="field">
            <label for="f-start">{adv ? 'Inizio (UTC)' : t('analysis.start')}</label>
            <input id="f-start" type="datetime-local" step="1" bind:value={start} aria-invalid={errors.start ? 'true' : undefined} aria-describedby={errors.start ? 'f-start-err' : undefined} />
            {#if errors.start}<span id="f-start-err" class="field-error">{errors.start}</span>{/if}
          </p>
          <p class="field">
            <label for="f-days">{adv ? 'Durata (giorni)' : STR.simple.days}</label>
            <input id="f-days" type="number" inputmode="decimal" step="any" bind:value={days} aria-invalid={errors.days ? 'true' : undefined} aria-describedby={errors.days ? 'f-days-err' : undefined} />
            {#if errors.days}<span id="f-days-err" class="field-error">{errors.days}</span>{/if}
          </p>
          {#if adv}
          <p class="field">
            <label for="f-step">Passo (minuti)</label>
            <input id="f-step" type="number" inputmode="decimal" step="any" bind:value={stepMin} aria-invalid={errors.step ? 'true' : undefined} aria-describedby={errors.step ? 'f-step-err' : undefined} />
            {#if errors.step}<span id="f-step-err" class="field-error">{errors.step}</span>{/if}
          </p>
          {/if}
        </div>

        {#if adv}
        <fieldset class="profile">
          <legend>Profilo del terreno (facoltativo)</legend>
          <p class="hint">
            CSV con due colonne, distanza (m, da 0, crescente) e quota (m), al massimo {status.limits.max_profile_points} punti e
            {MAX_PROFILE_BYTES / 1000} kB. Se manca si usa il DEM LOLA del sito.
          </p>
          <p class="field">
            <label for="f-profile">File CSV</label>
            <input id="f-profile" type="file" accept=".csv,.txt,text/csv,text/plain" onchange={onFile} aria-describedby={profileError ? 'f-profile-err' : undefined} aria-invalid={profileError ? 'true' : undefined} />
            {#if profileError}<span id="f-profile-err" class="field-error" role="alert">{profileError}</span>{/if}
          </p>
          <p class="inline">
            <button type="button" onclick={useSynthetic}>Usa un crinale sintetico di prova</button>
            {#if profile}<button type="button" onclick={dropProfile}>Rimuovi il profilo</button>{/if}
          </p>
          {#if profile}
            <p role="status" data-testid="profile-loaded">Profilo caricato: {profileName}, {profile.distance_m.length} punti, fino a {profile.distance_m[profile.distance_m.length - 1]} m.</p>
            <label class="check"><input type="checkbox" bind:checked={syntheticMark} /> Questo profilo è sintetico, di prova (non è un dato lunare)</label>
            <label class="check"><input id="f-sweep" type="checkbox" bind:checked={sweep} /> Usa uno spazzolamento dell’elevazione della Terra al posto delle efemeridi del sito</label>
            {#if sweep}
              <div class="grid">
                <p class="field">
                  <label for="f-elStart">Elevazione iniziale (°)</label>
                  <input id="f-elStart" type="number" step="any" bind:value={elStart} aria-invalid={errors.elStart ? 'true' : undefined} />
                  {#if errors.elStart}<span class="field-error">{errors.elStart}</span>{/if}
                </p>
                <p class="field">
                  <label for="f-elEnd">Elevazione finale (°)</label>
                  <input id="f-elEnd" type="number" step="any" bind:value={elEnd} aria-invalid={errors.elEnd ? 'true' : undefined} />
                  {#if errors.elEnd}<span class="field-error">{errors.elEnd}</span>{/if}
                </p>
              </div>
              <p class="hint">Lo spazzolamento è lineare nel tempo e NON usa le efemeridi: serve a esplorare il crinale, non descrive la librazione reale.</p>
            {/if}
          {/if}
          {#if errors.profile}<span class="field-error">{errors.profile}</span>{/if}
        </fieldset>
        {/if}

        <fieldset>
          <legend>{adv ? 'Collegamento (ipotesi illustrative, tag I)' : STR.simple.link}</legend>
          <div class="grid">
            <p class="field">
              <label for="f-station">{adv ? 'Stazione di terra' : STR.simple.station}</label>
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
                <label for="p-{k}">{label}</label>
                <input id="p-{k}" type="number" step="any" inputmode="decimal" min={r?.min ?? undefined} max={r?.max ?? undefined} bind:value={values[k as string]} aria-invalid={errors[`p-${k}`] ? 'true' : undefined} aria-describedby={errors[`p-${k}`] ? `p-${k}-err` : undefined} />
                {#if errors[`p-${k}`]}<span id="p-{k}-err" class="field-error">{errors[`p-${k}`]}</span>{/if}
              </p>
            {/each}
            <p class="field">
              <label for="f-rate">{adv ? 'Velocità per la finestra' : STR.simple.rate}</label>
              <select id="f-rate" bind:value={rate}>
                {#each defaults.rates_bps as r (r)}<option value={r}>{rateLabel(r)}</option>{/each}
              </select>
            </p>
            {#if adv}
            <p class="field">
              <label for="f-diameters">Diametri per la scheda Antenna (m)</label>
              <input id="f-diameters" type="text" bind:value={diameters} aria-invalid={errors.diameters ? 'true' : undefined} aria-describedby={errors.diameters ? 'f-diameters-err' : undefined} />
              {#if errors.diameters}<span id="f-diameters-err" class="field-error">{errors.diameters}</span>{/if}
            </p>
            <p class="field">
              <label for="f-antRates">Elenco di velocità per la scheda Antenna (bit/s)</label>
              <input id="f-antRates" type="text" bind:value={antRates} aria-invalid={errors.antRates ? 'true' : undefined} aria-describedby={errors.antRates ? 'f-antRates-err' : undefined} />
              {#if errors.antRates}<span id="f-antRates-err" class="field-error">{errors.antRates}</span>{/if}
            </p>
            {/if}
          </div>
          {#if !adv}
            <p class="hint" data-testid="more-in-advanced">{STR.moreInAdvanced}</p>
            {#if hiddenError}<p class="field-error" role="alert">{STR.hiddenError}</p>{/if}
          {:else}
          <details class="more">
            <summary>Altri parametri illustrativi ({extras.length})</summary>
            <div class="grid">
              {#each extras as r (r.key)}
                <p class="field">
                  <label for="p-{r.key}"><code>{r.key}</code> ({r.unit === '-' ? 'adim.' : r.unit})</label>
                  <input id="p-{r.key}" type="number" step="any" inputmode="decimal" min={r.min ?? undefined} max={r.max ?? undefined} bind:value={values[r.key]} aria-invalid={errors[`p-${r.key}`] ? 'true' : undefined} aria-describedby={errors[`p-${r.key}`] ? `p-${r.key}-err` : undefined} />
                  {#if errors[`p-${r.key}`]}<span id="p-{r.key}-err" class="field-error">{errors[`p-${r.key}`]}</span>{/if}
                </p>
              {/each}
            </div>
          </details>
          {/if}
        </fieldset>

        <p class="submit">
          <button type="submit" class="btn--primary" aria-disabled={running}>{running ? 'Analisi in corso...' : 'Esegui analisi'}</button>
        </p>
      </form>

      <div class="results">
        <p class="status" role="status">{message}</p>
        {#if error}
          <p role="alert" class="notice" data-kind={errorKind}>{error}</p>
        {/if}

        {#if result}
          <section class="panel" aria-labelledby="res-h">
            <h2 id="res-h">Risultati</h2>
            <p class="muted small">
              {result.window.start_utc.replace('T', ' ').replace('Z', ' UTC')}, {result.window.days} giorni, passo {result.window.step_min} min
              ({result.window.n_steps} istanti). {result.site.id ? `Sito: ${result.site.id}.` : 'Nessun sito: spazzolamento della Terra.'} Etichetta: {result.label}.
            </p>
            {#if result.flags.terrain.synthetic || usedSynthetic}
              <p class="notice warn" role="note" data-testid="synthetic-banner">Profilo sintetico di prova: il terreno non è lunare, i numeri servono solo a provare la pagina.</p>
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
            <div class="tablist" role="tablist" aria-label="Risultati dell’analisi" tabindex="-1">
              {#each tabs as t (t.id)}
                <button
                  type="button"
                  role="tab"
                  id="tab-{t.id}"
                  aria-selected={shown === t.id}
                  aria-controls="panel-{t.id}"
                  tabindex={shown === t.id ? 0 : -1}
                  onclick={() => (tab = t.id)}
                  onkeydown={onTabKey}>{t.label}</button
                >
              {/each}
            </div>
            {#each tabs as t (t.id)}
              <div role="tabpanel" id="panel-{t.id}" aria-labelledby="tab-{t.id}" hidden={shown !== t.id} tabindex="0" class="tabpanel">
                {#if shown === t.id}
                  {#if t.id === 'time'}<TabTime {result} />
                  {:else if t.id === 'windows'}<TabWindows {result} />
                  {:else if t.id === 'diffraction'}<TabDiffraction {result} {comp} {compError} />
                  {:else if t.id === 'antenna'}<TabAntenna {result} {report} error={antError} />
                  {:else if t.id === 'compensator'}<TabCompensator {result} />
                  {:else}<TabParams {result} userProfile={usedProfile} syntheticMark={usedSynthetic} />{/if}
                {/if}
              </div>
            {/each}
            <p class="muted small">
              Esporta la richiesta completa:
              <button type="button" class="linkish" onclick={async () => (await import('./grazing')).downloadText('raven-analisi.json', 'application/json', JSON.stringify({ request: lastReq && { ...lastReq, profile: lastReq.profile ? `${lastReq.profile.distance_m.length} punti` : undefined }, result }, null, 2))}>Scarica JSON dell’analisi</button>
            </p>
            {/if}
            <p class="muted small disclaimer">{status.disclaimer}</p>
          </section>
        {:else if !error && !running}
          <section class="panel empty" aria-labelledby="empty-h">
            <h2 id="empty-h">Risultati</h2>
            <p class="muted">Scegli un sito e una finestra e premi «Esegui analisi»: margine nel tempo, finestre, diffrazione, antenna e compensatore compaiono qui.</p>
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
