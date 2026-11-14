<!-- SPDX-License-Identifier: Apache-2.0 -->
<script lang="ts">
  import { onMount, onDestroy, tick } from 'svelte';
  import { untrack } from 'svelte';
  import { lang, t, formatNumber, type MessageKey } from '../../i18n/i18n.svelte';
  import { BASE } from '../../registry';
  import { withBase } from '../../shell/router';
  import { scenarioStore } from '../../shell/scenario';
  import { customSites, encodeCustom, parseCustom, makeId, MAX_CUSTOM_SITES, validateForm, type CustomSiteDef } from '../../shell/customSites';
  import { raven, type RavenEconomics, type RavenEvaluation, type RavenFailure, type RavenSiteInfo, type RavenParameter, type RavenValidation } from '../../shell/ravenApi';
  import { generateEstimates, mergeEstimates, sameEstimates } from './estimates';
  import { DEFAULT_MISSION_CLASS } from './estimates/missionClass';
  import { downloadText, toStartUtc, type ParamRow } from '../compare/lunar';
  import { loadCatalog, usedParameter } from './ravenAdapter';
  import { compatibleStep, readSavedPlanner, plannerDateBounds, type EphemerisRange } from './timeline';
  import { panelDefaults, readPanel } from './panel';
  import { readObjectives } from './objectives';
  import { readLibrary, restoreMission, writeLibrary, LIBRARY_LIMIT, type LibraryEntry } from './library';
  import { archiveRun } from './history';
  import { RADIO_PRESETS, identifyRadioPreset, type RadioPresetId } from './setup';
  import { DRAFT_KEY, RUN_KEY, JOURNEY_STEPS, earthVisibility, fraction, journeyIssue, journeyRequests,
    newDraft, radioValid, readDraft, readRun, requestKey, validEvaluations, type JourneyDraft, type JourneyRun } from './journey';
  import ParameterControl from './ParameterControl.svelte';
  import CustomSiteControl from '../../shell/CustomSiteControl.svelte';
  import { fetchHorizon, type HorizonResult } from './horizon';
  import HorizonProfile from './HorizonProfile.svelte';
  import JourneyPreview from './JourneyPreview.svelte';
  import SitesLibrary from './SitesLibrary.svelte';
  import SiteFinder from '../../shell/finder/SiteFinder.svelte';
  import type { Brief, Proposal } from '../../shell/finder/finderApi';
  import SitePolarMap from './SitePolarMap.svelte';
  import JourneyResults from './JourneyResults.svelte';
  import LifecycleReport from './LifecycleReport.svelte';
  import { rt } from './reportText';
  import './reportPrint.css';
  import { reportToc, type TocEntry } from './reportToc';
  import { missionLifecycleReport } from './report';
  import ReportDossier from './ReportDossier.svelte';
  import { budgetInput, budgetReady, isBudgetEstimate, isSiNarrative, newReportPlanning, planningContext,
    readReportPlanning, reportPost, type BudgetEstimate } from './reportPlanning';
  import { carbonInput, isCarbonEstimate, type CarbonEstimate, type DocumentPages } from './reportPlanning';
  import { utcMinute, bitRate, sharedParameters } from './reportFormat';
  import { reportLayout, simulatedCertificate, type SimulatedCertificate } from './reportPresentation';
  import { missionContext, reportScenarioKey } from './reportCompletion';
  import ReportSectionPicker from './ReportSectionPicker.svelte';
  import { fetchStatus } from '../chat/assistant';
  import { newReportSections, sectionsForMode, type ReportMode } from './reportSections';
  import { modeNow } from '../../shell/modeState.svelte';
  import ReportModeSwitch from './ReportModeSwitch.svelte';
  import { dossierProgress, effectiveReportMode } from './reportMode';
  import ReliabilityInputs from './ReliabilityInputs.svelte';
  import ReliabilityResults from './ReliabilityResults.svelte';
  import { reliabilityReady, reliabilityRequest, isReliabilityResult, type ReliabilityResult } from './reliability';

  const store = scenarioStore();
  const initial = store.reload();
  let draft = $state<JourneyDraft | null>(null);
  let catalog = $state<RavenSiteInfo[]>([]);
  let customs = $state<readonly CustomSiteDef[]>(customSites.get());
  let parameters = $state<ParamRow[]>([]);
  let parameterRegistry = $state<readonly RavenParameter[]>([]);
  let registry = $state('');
  let modelVersion = $state('');
  let ephemerisRange = $state<EphemerisRange | null>(null);
  let step = $state(0);
  let ready = $state(false);
  let error = $state<MessageKey | null>(null);
  let errorStatus = $state<number | null>(null);
  // cost band and CO2e of the chosen mission class, computed by the RAVEN core (re-read only when the class changes)
  let economics = $state<RavenEconomics | null>(null);
  $effect(() => {
    const cls = draft?.planning?.missionClass ?? DEFAULT_MISSION_CLASS;
    const c = new AbortController();
    void raven.reportEstimate(cls, { signal: c.signal }).then((r) => { if (!c.signal.aborted) economics = r.ok ? r.data : null; });
    return () => c.abort();
  });
  let storageError = $state(false);
  let restoreWarning = $state(false);
  let running = $state(false);
  let run = $state.raw<JourneyRun | null>(null);
  let scenario = $state(0);
  let index = $state(0);
  let playing = $state(false);
  let speed = $state(1000);
  let previewScene = $state(false);
  // the 3D scene is mounted a moment after the results are shown (its WebGL start-up blocks the page): results first, scene next
  let sceneReady = $state(false);
  // progress of the calculation: scenarios answered out of scenarios asked
  let calcDone = $state(0);
  let calcTotal = $state(0);
  let customScene = $state(false);
  let waveOpen = $state(false);
  let preview = $state.raw<RavenEvaluation[] | null>(null);
  let previewKey = $state('');
  let previewBusy = $state(false);
  let previewError = $state<MessageKey | null>(null);
  let previewAttemptKey = $state('');
  let library = $state<LibraryEntry[]>([]);
  let libraryMessage = $state<MessageKey | null>(null);
  let historyMessage = $state<MessageKey | null>(null);
  let search = $state('');
  let selectFor = $state<'A' | 'B'>('A');
  let mapView = $state<'globe' | 'polar'>('globe');
  let picked = $state<{ lat: number; lon: number } | null>(null);
  let customName = $state('');
  let customError = $state<MessageKey | null>(null);
  let horizon = $state.raw<HorizonResult | null>(null);
  let horizonBusy = $state(false);
  let horizonError = $state<MessageKey | null>(null);
  let horizonKey = $state('');
  let horizonController: AbortController | null = null;
  let previewController: AbortController | null = null;
  let controller: AbortController | null = null;
  let alive = true;
  let heading: HTMLHeadingElement | undefined = $state();
  let budget = $state.raw<BudgetEstimate | null>(null);
  let budgetKey = $state('');
  let budgetBusy = $state(false);
  let tocEntries = $state<TocEntry[]>([]);
  let reportEl = $state<HTMLElement | null>(null);
  let pdfBusy = $state(false);
  let pdfNote = $state<'pdfUnavailable' | 'pdfFailed' | null>(null);
  let budgetError = $state<MessageKey | null>(null);
  let siBusy = $state(false);
  let siError = $state<MessageKey | null>(null);
  let siController: AbortController | null = null;
  let carbon = $state.raw<CarbonEstimate | null>(null);
  let pages = $state<DocumentPages>({ compact: null, reference: null });
  let certificate = $state.raw<SimulatedCertificate | null>(null);
  let certificateError = $state(false);
  let validation = $state.raw<RavenValidation | null>(null);
  const plan = $derived(draft?.planning ?? null);
  // Report mode: the first time the Dossier or the Report is opened it takes the default from the site mode
  // (Learning -> Learn, Advanced -> Expert); afterwards only the user changes it, without touching the site mode.
  const reportMode = $derived<ReportMode>(effectiveReportMode(plan ?? undefined, modeNow.current));
  $effect(() => {
    if (step < 7 || !draft?.planning || draft.planning.reportMode) return;
    const mode = effectiveReportMode(undefined, modeNow.current);
    untrack(() => { if (draft?.planning) { draft.planning.reportMode = mode; draft.planning.sections = sectionsForMode(mode); } });
  });
  function setReportMode(mode: ReportMode) {
    if (!draft?.planning) return;
    draft.planning.reportMode = mode;
    draft.planning.sections = sectionsForMode(mode);
  }
  // RAVEN estimates follow the calculation: regenerated deterministically, the user's accept/dismiss decision is kept
  // while the digest of an estimate is unchanged. They never touch a value the user typed.
  $effect(() => {
    if (!run || stale || !draft?.planning) return;
    const fresh = generateEstimates({ evaluations: run.evaluations, objectives: $state.snapshot(draft.objectives), validation,
      massDefaults: $state.snapshot(draft.planning.massDefaults), missionClass: draft.planning.missionClass, producedAt: run.createdAt });
    const previous = untrack(() => $state.snapshot(draft?.planning?.estimates) ?? []);
    const off = draft.planning.estimatesOff === true;
    // no per-estimate review: with the estimates on every new one is accepted, with them off every one is dismissed
    const merged = mergeEstimates(previous, fresh).map((e) => off ? (e.status === 'dismissed' ? e : { ...e, status: 'dismissed' as const })
      : (e.status === 'proposed' ? { ...e, status: 'accepted' as const } : e));
    if (!sameEstimates(merged, previous)) untrack(() => { if (draft?.planning) draft.planning.estimates = merged; });
  });
  const reportSections = $derived(plan?.sections ?? newReportSections());
  const sectionKey = $derived(JSON.stringify(reportSections));
  const costKey = $derived(plan ? JSON.stringify([budgetInput(plan), carbonInput(plan, pages)]) : '');
  const shownBudget = $derived(budgetKey === costKey ? budget : null);
  const shownCarbon = $derived(budgetKey === costKey ? carbon : null);
  let reliability = $state.raw<ReliabilityResult | null>(null);
  let reliabilityKey = $state('');
  let reliabilityBusy = $state(false);
  let reliabilityError = $state(false);
  let reliabilityRetry = $state(0);
  let reportAllowExternal = $state(false);
  let reportCloudAvailable = $state(false);
  let reportCloudStatusError = $state(false);
  $effect(() => {
    if (step !== 7) return;
    const abort = new AbortController();
    reportCloudStatusError = false;
    void fetchStatus(fetch, abort.signal).then((status) => {
      if (abort.signal.aborted) return;
      reportCloudAvailable = status.cloudAvailable;
      if (!reportCloudAvailable) reportAllowExternal = false;
    }, () => {
      if (!abort.signal.aborted) { reportCloudStatusError = true; reportCloudAvailable = false; reportAllowExternal = false; }
    });
    return () => abort.abort();
  });
  const narrativeKey = $derived(plan && run && draft ? planningContext(plan, reportScenarioKey(run.evaluations), draft.name, draft.decision, 'en', draft.objectives) : '');
  const dossierIssue = $derived(plan && (!readReportPlanning(plan) || !budgetReady(plan)) ? 'dossier.invalid' : null);

  const stepTitles: MessageKey[] = ['journey.mission', 'journey.sites', 'journey.period', 'journey.energy', 'journey.reliability', 'journey.radio', 'journey.compare', 'dossier.title', 'journey.report'];
  const stepDescriptions: MessageKey[] = ['journey.missionIntro', 'journey.sitesIntro', 'journey.periodIntro', 'journey.energyIntro', 'journey.reliabilityIntro', 'journey.radioIntro', 'journey.compareIntro', 'dossier.intro', 'journey.reportIntro'];
  const priorityLabels: Record<string, MessageKey> = {
    sun: 'planner.objectiveSun', earth: 'planner.objectiveEarth', radio: 'planner.objectiveRadio', balanced: 'planner.objectiveBalanced',
  };
  const presetLabels: Record<RadioPresetId, MessageKey> = {
    baseline: 'planner.presetBaseline', lowRate: 'planner.presetLowRate', highRate: 'planner.presetHighRate',
  };
  const apiErrors: Record<RavenFailure, MessageKey> = {
    network: 'planner.errorNetwork', invalid: 'planner.errorInvalid', unavailable: 'planner.errorUnavailable',
    server: 'planner.errorServer', response: 'planner.errorResponse', aborted: 'planner.errorNetwork',
  };
  const allSites = $derived([...catalog, ...customs.map((c) => ({
    ...c, verified: false, dem_covered: false, source_url: '', coordinate_basis: 'point',
  }))]);
  const ids = $derived(allSites.map((s) => s.id));
  const requests = $derived.by(() => {
    void customs;
    return draft ? journeyRequests(draft, parameters, customs, ephemerisRange) : null;
  });
  const dateBounds = $derived(plannerDateBounds(ephemerisRange, draft?.input.days ?? null));
  const signature = $derived(requests ? requestKey(requests) : '');
  const stale = $derived(!!run && signature !== run.key);
  const active = $derived(run?.evaluations[scenario] ?? null);
  const activeId = $derived((step === 6 || step === 7) && active ? active.site.id : draft ? (selectFor === 'B' && draft.input.mode === 'sites' ? draft.input.siteB : draft.input.siteA) : '');
  const activeSite = $derived(allSites.find((s) => s.id === activeId));
  const activeCustom = $derived(customs.find((s) => s.id === activeId));
  const sceneMs = $derived(step === 6 && active?.steps ? active.steps.time_unix[index]! * 1000 : draft ? Date.parse(toStartUtc(draft.input.start) ?? '') : NaN);
  const activeHorizonKey = $derived(draft ? JSON.stringify([activeId, draft.radio.mast, activeCustom ?? null]) : '');
  const shownHorizon = $derived(horizonKey === activeHorizonKey ? horizon : null);
  const firstIssue = $derived.by(() => {
    if (!draft) return 0;
    for (let i = 0; i < 6; i++) if (journeyIssue(draft, i, ids, parameters, customs, ephemerisRange)) return i;
    return 6;
  });
  const currentIssue = $derived(draft ? journeyIssue(draft, step, ids, parameters, customs, ephemerisRange) : null);
  const preset = $derived(draft && draft.radio.rate !== null ? identifyRadioPreset({ ...draft.radio, rate: draft.radio.rate }) : 'custom');
  const count = $derived(draft?.input.days != null && draft.input.stepMin != null
    ? Math.max(1, Math.floor(draft.input.days * 1440 / draft.input.stepMin + 1e-9)) : null);
  let autoStepNote = $state<{ days: number; step: number } | null>(null);
  /** A long period is admitted only with a step that keeps it inside the sample caps: raised here and explained. */
  function autoStep() {
    if (!draft || draft.input.days === null || draft.input.stepMin === null) return;
    const next = compatibleStep(draft.input.days, draft.input.stepMin, draft.input.mode === 'sites' ? 2 : 1);
    if (next !== null && next !== draft.input.stepMin) {
      draft.input.stepMin = next;
      autoStepNote = { days: draft.input.days, step: next };
    } else autoStepNote = null;
  }
  const selectedCoords = $derived(picked ?? (activeSite ? { lat: activeSite.lat_deg, lon: activeSite.lon_deg_east } : null));
  const shownPreview = $derived(previewKey === signature ? preview : null);
  const reliabilityBody = $derived(plan?.reliability?.enabled && run && !stale
    ? reliabilityRequest(plan.reliability, run.evaluations) : null);
  const reliabilityRequestKey = $derived(reliabilityBody ? JSON.stringify(reliabilityBody) : '');
  const shownReliability = $derived(reliabilityKey === reliabilityRequestKey ? reliability : null);
  const reliabilityIssue = $derived(plan?.reliability?.enabled && !reliabilityReady(plan.reliability));
  const reliabilityBlocked = $derived(!!plan?.reliability?.enabled && (reliabilityIssue || reliabilityError || !shownReliability));

  function readStep() {
    const name = new URLSearchParams(location.search).get('mp_step');
    const n = JOURNEY_STEPS.findIndex((s) => s === name);
    return n < 0 ? 0 : n;
  }
  async function go(next: number, push = true) {
    if (!draft || running) return;
    const allowed = next < 6 ? next <= firstIssue : firstIssue === 6 && (next === 6 || (!!run && !stale));
    if (!allowed) {
      error = journeyIssue(draft, firstIssue, ids, parameters, customs, ephemerisRange) ?? 'journey.calculateFirst';
      return;
    }
    playing = false;
    previewScene = next === 5 || next === 6;
    customScene = false;
    waveOpen = false;
    error = null; errorStatus = null;
    previewError = null;
    step = next;
    const url = new URL(location.href);
    url.searchParams.set('mp_step', JOURNEY_STEPS[next]!);
    if (push) history.pushState(history.state, '', url);
    else history.replaceState(history.state, '', url);
    await tick();
    heading?.focus();
    heading?.scrollIntoView?.({ block: 'start', behavior: 'instant' });
  }
  function restoreStep() {
    if (!ready) return;
    if (running) { controller?.abort(); running = false; }
    const requested = readStep();
    const max = firstIssue < 6 ? firstIssue : run && !stale ? 8 : 6;
    void go(Math.min(requested, max), false);
  }
  function changeSite(id: string) {
    if (!draft) return;
    if (selectFor === 'B' && draft.input.mode === 'sites') draft.input.siteB = id;
    else draft.input.siteA = id;
    picked = null;
  }
  function addPickedSite() {
    if (!draft || !picked) return;
    if (customs.length >= MAX_CUSTOM_SITES) { customError = 'custom.limit'; return; }
    const checked = validateForm({ name: customName, lat: picked.lat, lon: picked.lon });
    if (!checked.ok) { customError = 'journey.customInvalid'; return; }
    const site = { id: makeId(checked.value.name, new Set(customs.map((s) => s.id))), ...checked.value };
    store.set({ customSites: [...customs, site] });
    store.flush();
    changeSite(site.id);
    customError = null;
    customName = '';
  }
  // Sites found by the automatic search become A and/or B in place: a catalogue site is used as it is, any other becomes a custom site; the
  // period of the search replaces the planner's period when it is inside the ephemeris range.
  let finderMounted = $state(false);
  let overlaysDone = $state(true); // the map overlays of part 2 are drawn (the PDF carries them as images)
  let verdictDone = $state(true); // the comparison of the two sites at the end of the report is written (a local model may need up to a minute)
  function useFound(picks: { p: Proposal; target: 'A' | 'B' }[], b: Partial<Brief>) {
    if (!draft) return;
    let list = [...customSites.get()];
    let added = false;
    for (const { p, target } of picks) {
      // the same place as a site already listed (same coordinates to 0.01 degree): use that one instead of adding a copy
      const hit = allSites.find((x) => Math.abs(x.lat_deg - p.lat_deg) < 0.01 && Math.abs(x.lon_deg_east - p.lon_deg_east) < 0.01);
      let id = hit?.id;
      if (!id) {
        if (list.length >= MAX_CUSTOM_SITES) { customError = 'custom.limit'; return; }
        const name = (p.name ?? `Found ${p.rank}`).slice(0, 40);
        id = makeId(name, new Set(list.map((x) => x.id)));
        list = [...list, { id, name, lat_deg: Number(p.lat_deg.toFixed(4)), lon_deg_east: Number(p.lon_deg_east.toFixed(4)) }];
        added = true;
      }
      if (target === 'B' && draft.input.mode === 'sites') draft.input.siteB = id; else draft.input.siteA = id;
    }
    if (added) { store.set({ customSites: list }); store.flush(); }
    picked = null; customError = null;
    const start = b.start_utc ? b.start_utc.slice(0, 16) : null;
    if (start && (!dateBounds || (start >= dateBounds.min && start <= dateBounds.max))) draft.input.start = start;
    if (b.days && b.days > 0 && b.days <= 366) { draft.input.days = b.days; autoStep(); }
  }
  function applyPreset(id: RadioPresetId) {
    if (draft) draft.radio = { ...RADIO_PRESETS[id] };
  }
  function example() {
    if (!draft) return;
    draft.input.mode = 'sites';
    draft.input.siteA = ids.includes('malapert-massif') ? 'malapert-massif' : ids[0] ?? '';
    draft.input.siteB = ids.includes('haworth') ? 'haworth' : ids.find((s) => s !== draft?.input.siteA) ?? '';
    draft.input.start = '2027-04-16T00:00';
    draft.input.days = 3;
    draft.input.stepMin = 60;
    void go(1);
  }
  function saveMission() {
    if (!draft || firstIssue < 6) { libraryMessage = 'journey.calculateFirst'; return; }
    const config = {
      planner: { ...$state.snapshot(draft.input), panel: $state.snapshot(draft.panel), mast: draft.radio.mast,
        objectives: $state.snapshot(draft.objectives), decision: draft.decision, lesson: 0, siteView: 'A', quiz: '',
        setup: { name: draft.name, kind: 'site-study', path: 'guided' } },
      radio: $state.snapshot(draft.radio), selectedTime: null, customSites: encodeCustom(customs),
      reportPlanning: $state.snapshot(draft.planning ?? newReportPlanning()),
    };
    const entry = { id: String(Date.now()), name: draft.name, savedAt: new Date().toISOString(), config };
    const entries = [entry, ...library.filter((e) => e.id !== entry.id)].slice(0, LIBRARY_LIMIT);
    if (!writeLibrary(localStorage, entries)) { libraryMessage = 'planner.libraryWriteError'; return; }
    library = entries;
    libraryMessage = 'journey.librarySaved';
  }
  function openMission(entry: LibraryEntry) {
    if (!draft) return;
    const config = entry.config as Record<string, unknown>;
    const encoded = config.customSites;
    const savedCustoms = typeof encoded === 'string' ? parseCustom(encoded) : [];
    if (encoded !== undefined && (typeof encoded !== 'string' || encodeCustom(savedCustoms) !== encoded)) {
      libraryMessage = 'journey.restoreWarning'; return;
    }
    const merged = [...customs.filter((c) => !savedCustoms.some((s) => s.id === c.id)), ...savedCustoms];
    if (merged.length > MAX_CUSTOM_SITES) { libraryMessage = 'custom.limit'; return; }
    const restored = restoreMission(entry.config, [...catalog.map((s) => s.id), ...merged.map((s) => s.id)], parameters, merged);
    if (!restored) { libraryMessage = 'journey.restoreWarning'; return; }
    const panel = readPanel(restored.planner.panel, parameters);
    const objectives = readObjectives(restored.planner.objectives);
    if (!panel || !objectives) { libraryMessage = 'journey.restoreWarning'; return; }
    const planning = config.reportPlanning === undefined ? newReportPlanning() : readReportPlanning(config.reportPlanning);
    if (!planning) { libraryMessage = 'journey.restoreWarning'; return; }
    store.set({ customSites: merged });
    store.flush();
    draft = { name: entry.name, input: restored.planner.input, panel, radio: restored.radio, objectives, decision: restored.planner.decision, planning };
    libraryMessage = null;
  }

  onMount(() => {
    const unsubscribe = customSites.subscribe((list) => { customs = list; });
    void raven.validation().then((v) => { if (v.ok && alive) validation = v.data; }, () => undefined);
    void (async () => {
      const cat = await loadCatalog();
      if (!alive) return;
      if (!cat.ok) { error = apiErrors[cat.kind]; return; }
      parameters = cat.data.defaults.parameters;
      parameterRegistry = cat.data.parameterRegistry;
      registry = cat.data.registry_sha256;
      modelVersion = cat.data.model_version;
      ephemerisRange = cat.data.status.ephemeris.supported_range ?? null;
      catalog = cat.data.sites.map((s) => ({
        ...s, source_accessed: '', source_note: '', dem_coverage: cat.data.status.sites.find((x) => x.id === s.id)?.dem_covered ?? null,
        dem_covered: cat.data.status.sites.some((x) => x.id === s.id && x.dem_covered),
      }));
      const availableIds = [...catalog.map((s) => s.id), ...customs.map((s) => s.id)];
      const covered = catalog.filter((s) => s.dem_covered).map((s) => s.id);
      draft = newDraft(parameters, availableIds, initial.site ?? covered[0], initial.t);
      if (!draft) { error = 'planner.panelInvalid'; return; }
      if (covered.length > 1) draft.input.siteB = covered.find((s) => s !== draft?.input.siteA) ?? draft.input.siteB;
      try {
        const savedLibrary = readLibrary(localStorage);
        if (savedLibrary.ok) library = savedLibrary.entries;
        else libraryMessage = 'planner.libraryReadError';
        const raw = sessionStorage.getItem(DRAFT_KEY);
        const saved = readDraft(raw, parameters, availableIds);
        if (saved) draft = saved;
        else if (raw) restoreWarning = true;
        else {
          const legacy = readSavedPlanner(sessionStorage.getItem('hb.mission-planner'), availableIds);
          if (legacy) {
            draft.input = legacy.input;
            draft.name = typeof legacy.setup === 'object' && legacy.setup && 'name' in legacy.setup && typeof legacy.setup.name === 'string' ? legacy.setup.name : '';
            draft.decision = legacy.decision;
            draft.panel = readPanel(legacy.panel, parameters) ?? draft.panel;
            draft.objectives = readObjectives(legacy.objectives) ?? draft.objectives;
            draft.radio.mast = legacy.mast;
          }
        }
        const savedRun = sessionStorage.getItem(RUN_KEY);
        run = readRun(savedRun, parameters, availableIds, registry, modelVersion);
        if (savedRun && !run) restoreWarning = true;
      } catch {
        storageError = true;
      }
      const query = new URLSearchParams(location.search);
      if (!query.has('mp_step')) {
        if (query.has('site') && initial.site && availableIds.includes(initial.site)) draft.input.siteA = initial.site;
        if (query.has('t') && initial.t) draft.input.start = initial.t.slice(0, 16);
        if (query.has('gain') && initial.gain !== null) draft.radio.gain = initial.gain;
        if (query.has('rate') && initial.bitrate !== null) draft.radio.rate = initial.bitrate;
        if (query.has('antenna_h') && initial.mast !== null) draft.radio.mast = initial.mast;
        if (query.has('k') && initial.k !== null) draft.radio.k = initial.k;
        if (query.has('station')) draft.radio.station = initial.station;
      }
      ready = true;
      await tick();
      const requested = readStep();
      const max = firstIssue < 6 ? firstIssue : run && !stale ? 8 : 6;
      void go(Math.min(requested, max), false);
    })();
    return unsubscribe;
  });
  onDestroy(() => {
    alive = false;
    controller?.abort();
    horizonController?.abort();
    previewController?.abort();
    siController?.abort();
  });
  $effect(() => {
    if (!ready || !draft) return;
    const raw = JSON.stringify(draft);
    try { sessionStorage.setItem(DRAFT_KEY, raw); }
    catch { storageError = true; }
  });
  $effect(() => {
    const key = costKey;
    if (!ready || !plan || step < 7) return;
    if (dossierIssue) { budgetBusy = false; budgetError = dossierIssue; return; }
    const body = budgetInput(plan);
    const environment = carbonInput(plan, pages);
    const abort = new AbortController();
    let cancelled = false;
    budgetBusy = true; budgetError = null;
    const timeout = setTimeout(() => abort.abort(), 15000);
    const timer = setTimeout(async () => {
      try {
        const [data, footprint] = await Promise.all([
          reportPost('budget', body, abort.signal), reportPost('carbon', environment, abort.signal),
        ]);
        if (!isBudgetEstimate(data) || !isCarbonEstimate(footprint)) throw new Error('dossier.requestFailed');
        if (!abort.signal.aborted && costKey === key) { budget = data; carbon = footprint; budgetKey = key; }
      } catch {
        if (!cancelled && costKey === key) budgetError = 'dossier.requestFailed';
      } finally {
        clearTimeout(timeout);
        if (!cancelled && costKey === key) budgetBusy = false;
      }
    }, 300);
    return () => { cancelled = true; clearTimeout(timer); clearTimeout(timeout); abort.abort(); };
  });
  $effect(() => {
    const body = reliabilityBody;
    const key = reliabilityRequestKey;
    void reliabilityRetry;
    if (!body || step < 4 || !reliabilityReady(body.profile)) { reliabilityBusy = false; reliabilityError = false; return; }
    if (untrack(() => reliabilityKey === key && !!reliability)) { reliabilityBusy = false; reliabilityError = false; return; }
    const abort = new AbortController();
    let cancelled = false;
    reliabilityBusy = true; reliabilityError = false;
    const timeout = setTimeout(() => abort.abort(), 15000);
    const timer = setTimeout(async () => {
      try {
        const data = await reportPost('reliability', body, abort.signal);
        if (!isReliabilityResult(data)) throw new Error('rel.error');
        if (!cancelled && reliabilityRequestKey === key) { reliability = data; reliabilityKey = key; }
      } catch {
        if (!cancelled && reliabilityRequestKey === key) reliabilityError = true;
      } finally {
        clearTimeout(timeout);
        if (!cancelled && reliabilityRequestKey === key) reliabilityBusy = false;
      }
    }, 300);
    return () => { cancelled = true; abort.abort(); clearTimeout(timer); clearTimeout(timeout); };
  });
  $effect(() => {
    void sectionKey;
    pages = { compact: null, reference: null };
  });
  $effect(() => {
    certificate = null; certificateError = false;
    if (!draft || !run || stale || step !== 8 || !shownBudget || !shownCarbon || !reportSections.seal || reliabilityBlocked) return;
    const payload = {
      format: 'raven-report-evidence-v1', calculation_created_at: run.createdAt,
      config: $state.snapshot(draft), requests: run.requests, evaluations: run.evaluations,
      lifecycle: missionLifecycleReport($state.snapshot(draft), rt('disclaimer'), {
        model_version: run.evaluations[0]!.model_version, registry_sha256: run.evaluations[0]!.registry_sha256,
      }, run.evaluations, shownBudget, shownCarbon, null, shownReliability),
    };
    let cancelled = false;
    const timer = setTimeout(() => {
      void simulatedCertificate(payload).then((value) => {
        if (!cancelled) certificate = value;
      }, () => { if (!cancelled) certificateError = true; });
    }, 100);
    return () => { cancelled = true; clearTimeout(timer); };
  });
  function updatePages(next: DocumentPages) {
    if (pages.compact !== next.compact || pages.reference !== next.reference) pages = next;
  }
  async function generateNarrative() {
    if (!draft?.planning || !run || stale || siBusy || dossierIssue || budgetBusy) return;
    const key = narrativeKey;
    const language = 'en' as const; // the report is English only
    const context = missionContext(draft.planning, draft, run.evaluations, shownBudget);
    siController?.abort();
    const abort = new AbortController();
    siController = abort;
    const timeout = setTimeout(() => abort.abort(), 70000);
    siBusy = true; siError = null;
    try {
      const data = await reportPost('narrative', { lang: language, context, allow_external: reportAllowExternal }, abort.signal);
      if (!isSiNarrative(data)) throw new Error('dossier.requestFailed');
      if (key !== narrativeKey) { siError = 'dossier.siStale'; return; }
      draft.planning.si = { inputKey: key, result: data };
    } catch (e) {
      const code = e instanceof Error ? e.message : '';
      siError = code === 'si.rateLimited' ? 'si.rateLimited' : code === 'dossier.siUnavailable' ? 'dossier.siUnavailable' : 'dossier.requestFailed';
    } finally { clearTimeout(timeout); siBusy = false; }
  }
  $effect(() => {
    if (!playing || !active?.steps || step !== 6 || stale) { playing = false; return; }
    if (index >= active.steps.time_unix.length - 1) { playing = false; return; }
    const timer = setTimeout(() => { index += 1; }, speed);
    return () => clearTimeout(timer);
  });
  $effect(() => {
    if (running && signature !== pendingKey) { controller?.abort(); running = false; }
  });
  $effect(() => {
    const key = signature;
    if (!ready || (step !== 2 && step !== 3) || !key || shownPreview || previewBusy ||
        (previewError && previewAttemptKey === key) ||
        !requests?.every((q) => catalog.some((s) => s.id === q.site_id && s.dem_covered))) return;
    const timer = setTimeout(() => untrack(() => void loadPreview()), 300);
    return () => clearTimeout(timer);
  });
  $effect(() => {
    if (!ready || step !== 5) return;
    const key = activeHorizonKey;
    const covered = !!activeSite; // any catalogue site: outside the 20 m product its terrain comes after the download consent
    const timer = setTimeout(() => {
      untrack(() => { if (covered && key === activeHorizonKey && !shownHorizon) void loadHorizon(); });
    }, 300);
    return () => { clearTimeout(timer); horizonController?.abort(); horizonBusy = false; };
  });
  $effect(() => {
    if (step === 6 && run && !stale) {
      const id = setTimeout(() => { sceneReady = true; }, 400);
      return () => clearTimeout(id);
    }
    sceneReady = false;
  });
  let pendingKey = '';
  async function calculate() {
    if (!draft || !requests || firstIssue < 6 || running) { error = 'journey.calculateFirst'; return; }
    controller?.abort();
    const c = new AbortController();
    controller = c;
    const submitted = structuredClone($state.snapshot(draft));
    const submittedRequests = structuredClone(requests);
    const key = requestKey(submittedRequests);
    pendingKey = key;
    running = true;
    error = null; errorStatus = null;
    const results = [];
    calcDone = 0; calcTotal = submittedRequests.length;
    // Sequential custom requests share the same explicit terrain-download consent.
    for (const q of submittedRequests) {
      const response = await raven.evaluate(q, { signal: c.signal });
      if (!alive || c.signal.aborted) return;
      if (!response.ok) {
        running = false;
        errorStatus = response.status ?? null;
        error = response.detail === 'needs_download' ? 'journey.downloadDeclined' :
          response.detail === 'too_large' ? 'journey.terrainCap' : apiErrors[response.kind];
        return;
      }
      results.push(response.data);
      calcDone = results.length;
    }
    running = false;
    if (key !== signature) return;
    if (!validEvaluations(results, submittedRequests) || results.some((e) => e.registry_sha256 !== registry || e.model_version !== modelVersion)) {
      error = 'planner.errorResponse'; return;
    }
    run = { key, config: submitted, requests: submittedRequests, evaluations: results, createdAt: new Date().toISOString() };
    scenario = 0; index = 0;
    try { sessionStorage.setItem(RUN_KEY, JSON.stringify(run)); }
    catch { storageError = true; }
    try {
      const archived = archiveRun(localStorage, run, parameters, ids, registry, modelVersion);
      historyMessage = archived.ok ? 'history.saved' : archived.error;
    } catch { historyMessage = 'history.writeError'; }
  }
  async function loadHorizon() {
    if (!draft || !activeId || draft.radio.mast === null) return;
    horizonController?.abort();
    const c = new AbortController();
    horizonController = c;
    const key = activeHorizonKey;
    horizonBusy = true; horizonError = null;
    const res = await fetchHorizon(raven, activeId, draft.radio.mast, c.signal);
    if (!alive || c.signal.aborted) return;
    horizonBusy = false;
    if (key !== activeHorizonKey) return;
    if (res.ok) { horizon = res.data; horizonKey = key; }
    else horizonError = apiErrors[res.kind];
  }
  async function loadPreview() {
    if (!draft || !requests || previewBusy) return;
    previewController?.abort();
    const c = new AbortController();
    previewController = c;
    const key = signature;
    previewAttemptKey = key;
    const qs = requests.map((q) => ({ ...q, include_windows: false }));
    previewBusy = true; previewError = null;
    const values: RavenEvaluation[] = [];
    for (const q of qs) {
      const res = await raven.evaluate(q, { signal: c.signal });
      if (!alive || c.signal.aborted) return;
      if (key !== signature || (step !== 2 && step !== 3)) { previewBusy = false; return; }
      if (!res.ok) {
        previewBusy = false;
        previewError = res.detail === 'needs_download' ? 'journey.downloadDeclined' : apiErrors[res.kind];
        return;
      }
      values.push(res.data);
    }
    previewBusy = false;
    if (key !== signature) return;
    if (!validEvaluations(values, qs) || values.some((e) => e.registry_sha256 !== registry)) { previewError = 'planner.errorResponse'; return; }
    preview = values; previewKey = key;
  }
  function exportReport() {
    if (!run || stale || !draft || budgetBusy || dossierIssue || budgetError || reliabilityBlocked || (reportSections.seal && !certificate) || !pages.compact) return;
    downloadText('raven-mission-report.json', 'application/json', JSON.stringify({
      schema_version: 4, generated_at: new Date().toISOString(), calculation_created_at: run.createdAt,
      lifecycle: missionLifecycleReport($state.snapshot(draft), rt('disclaimer'), {
        model_version: run.evaluations[0]!.model_version, registry_sha256: run.evaluations[0]!.registry_sha256,
      }, run.evaluations, shownBudget, shownCarbon, certificate, shownReliability),
      config: $state.snapshot(draft), requests: run.requests, evaluations: run.evaluations,
      parameter_registry: { registry_sha256: registry, parameters: $state.snapshot(parameters), source_parameters: $state.snapshot(parameterRegistry) },
      objectives: run.evaluations.map((e) => ({
        site_id: e.site.id, sun_fraction: fraction(e.steps!.lit), earth_fraction: fraction(earthVisibility(e)),
        rf_fraction: fraction(e.steps!.rf_closes), min_sun_percent: draft!.objectives.minSunPercent,
        min_rf_percent: draft!.objectives.minRfPercent,
      })),
    }, null, 2));
  }
  async function downloadPdf() {
    if (!reportEl || !run || pdfBusy) return;
    pdfBusy = true; pdfNote = null;
    try {
      const { fetchReportPdf, saveBlob, PdfUnavailable } = await import('./reportPdf');
      try {
        const blob = await fetchReportPdf({
          root: reportEl, title: rt('pdf.title'), subtitle: draft?.name || rt('pdf.unnamed'),
          lang: 'en', created: run.createdAt, filename: 'raven-mission-report-en',
        });
        saveBlob('raven-mission-report-en.pdf', blob);
      } catch (e) {
        if (e instanceof PdfUnavailable && ['503', '404', 'network', 'type'].includes(e.message)) { pdfNote = 'pdfUnavailable'; window.print(); }
        else pdfNote = 'pdfFailed';
      }
    } finally { pdfBusy = false; }
  }
  const siteName = (id: string) => allSites.find((s) => s.id === id)?.name ?? id;
  const param = (key: string) => parameters.find((p) => p.key === key && p.group === 'energy');
</script>

<svelte:window onpopstate={restoreStep} />

<div class="journey container container--wide" data-testid="mission-journey">
  <header class="journey-header">
    <div><p class="eyebrow">RAVEN / MISSION PLANNER</p><h1>{t('journey.title')}</h1></div>
    <span class="save-state" role="status">{t(storageError ? 'journey.storageError' : ready ? 'journey.saved' : 'planner.loadingSites')}</span>
    {#if historyMessage}
      <p role={historyMessage === 'history.saved' ? 'status' : 'alert'}>{t(historyMessage)} <a href={withBase('/dashboard', BASE)}>{t('history.open')}</a></p>
    {/if}
  </header>
  {#if restoreWarning}<p role="status" class="warning">{t('journey.restoreWarning')}</p>{/if}
  {#if !ready}
    {#if error}<p role="alert">{t(error)}</p><button type="button" onclick={() => location.reload()}>{t('journey.retry')}</button>
    {:else}<p role="status">{t('planner.loadingSites')}</p>{/if}
  {:else if draft}
    <nav class="stepper" aria-label={t('journey.progress')}>
      <ol>{#each JOURNEY_STEPS as id, i}
        <li><button type="button" aria-current={step === i ? 'step' : undefined}
          disabled={running || (i < 6 ? i > firstIssue : firstIssue < 6 || (i >= 7 && (!run || stale)))}
          onclick={() => go(i)}><span class="step-number">{String(i + 1).padStart(2, '0')}</span><span>{t(stepTitles[i]!)}</span></button></li>
      {/each}</ol>
    </nav>
    <div class="workspace">
      <section class="step-body" aria-busy={running} aria-labelledby="journey-step-heading">
        <header class="step-heading"><p class="eyebrow">{t('journey.stepOf', { step: step + 1, total: JOURNEY_STEPS.length })}</p>
          <h2 id="journey-step-heading" tabindex="-1" bind:this={heading}>{t(stepTitles[step]!)}</h2><p>{t(stepDescriptions[step]!)}</p></header>
        {#if step === 2 || step === 3}
          <section class="visual-stage" aria-label={t('journey.graphs')}>
            <h3>{t(step === 2 ? 'journey.periodVisual' : 'journey.energyVisual')}</h3>
            {#if shownPreview}<JourneyPreview evaluations={shownPreview} energy={step === 3} />
            {:else}<p role="status">{t(previewBusy ? 'planner.calculating' : 'journey.previewPending')}</p>{/if}
            <button type="button" disabled={previewBusy || !requests} onclick={loadPreview}>{t(previewBusy ? 'planner.calculating' : 'journey.previewButton')}</button>
            {#if previewError}<p role="alert">{t(previewError)}</p>{/if}
          </section>
        {:else if step === 5 || (step === 6 && !run)}
          <section class="visual-stage" aria-label={t('journey.openScene')}>
            {#if draft.input.mode === 'sites'}<div class="choices"><button type="button" aria-pressed={selectFor === 'A'} onclick={() => selectFor = 'A'}>A</button><button type="button" aria-pressed={selectFor === 'B'} onclick={() => selectFor = 'B'}>B</button></div>{/if}
            <button type="button" aria-expanded={previewScene} onclick={() => previewScene = !previewScene}>{t('journey.openScene')}</button>
            {#if previewScene && radioValid(draft.radio) && Number.isFinite(sceneMs) && activeId}
              {#if !activeCustom || customScene}
                {#await import('../lander/Lander.svelte') then m}<m.default embedded compact plannerSite={activeId} plannerMs={sceneMs}
                  plannerCustomSite={activeCustom}
                  plannerRadio={{ station: draft.radio.station, gain: draft.radio.gain!, rate: draft.radio.rate!, mast: draft.radio.mast! }} />{:catch}<p role="alert">{t('journey.visualFailed')}</p>{/await}
                <p class="note">{t('journey.sceneNote')}</p>
              {:else}<p class="note">{t('journey.previewPending')}</p><button type="button" onclick={() => customScene = true}>{t('journey.openScene')}</button>{/if}
            {/if}
            {#if step === 5}<button type="button" disabled={horizonBusy} onclick={loadHorizon}>{t('journey.openHorizon')}</button>
            {#if horizonBusy}<p role="status">{t('planner.calculating')}</p>{/if}
            {#if horizonError}<p role="alert">{t(horizonError)}</p>{/if}
            {#if shownHorizon}<HorizonProfile result={shownHorizon} labels={{
              chart: t('planner.horizonChart'), table: t('planner.horizonTable'), azimuth: t('planner.azimuth'), elevation: t('planner.horizonElevation'),
              distance: t('planner.distance'), status: t('planner.status'), ok: t('planner.available'), missing_dem: t('planner.solarMissing'), outside_coverage: t('planner.solarOutside'),
            }} />{/if}{/if}
          </section>
        {/if}
        {#if step === 0}
          <label for="journey-name">{t('planner.missionName')}</label><input id="journey-name" maxlength="80" bind:value={draft.name} placeholder={t('journey.namePlaceholder')} />
          <fieldset><legend>{t('planner.comparisonType')}</legend><div class="choices">
            {#each ['sites', 'dates'] as mode}<button type="button" class="choice" aria-pressed={draft.input.mode === mode}
              onclick={() => { draft!.input.mode = mode === 'sites' ? 'sites' : 'dates'; selectFor = 'A'; }}>{t(mode === 'sites' ? 'planner.twoSites' : 'planner.twoDates')}</button>{/each}
          </div></fieldset>
          <fieldset><legend>{t('planner.objectivePriority')}</legend><div class="choices">
            {#each ['sun', 'earth', 'radio', 'balanced'] as priority}
              <button type="button" class="choice" aria-pressed={draft.objectives.priority === priority}
                onclick={() => { if (priority === 'sun' || priority === 'earth' || priority === 'radio' || priority === 'balanced') draft!.objectives.priority = priority; }}>{t(priorityLabels[priority]!)}</button>
            {/each}
          </div></fieldset>
          <details><summary>{t('planner.objectivesTitle')}</summary><p>{t('planner.objectivesNote')}</p>
            <label class="check"><input type="checkbox" checked={draft.objectives.minSunPercent !== null} onchange={(e) => draft!.objectives.minSunPercent = e.currentTarget.checked ? 50 : null} />{t('planner.minimumSun')}</label>
            {#if draft.objectives.minSunPercent !== null}<ParameterControl id="journey-min-sun" label={t('planner.minimumSun')} bind:value={draft.objectives.minSunPercent} min={0} max={100} unit="%" />{/if}
            <label class="check"><input type="checkbox" checked={draft.objectives.minRfPercent !== null} onchange={(e) => draft!.objectives.minRfPercent = e.currentTarget.checked ? 50 : null} />{t('planner.minimumRf')}</label>
            {#if draft.objectives.minRfPercent !== null}<ParameterControl id="journey-min-rf" label={t('planner.minimumRf')} bind:value={draft.objectives.minRfPercent} min={0} max={100} unit="%" />{/if}
          </details>
          <div class="example"><h3>{t('journey.example')}</h3><p>{t('journey.exampleText')}</p><button type="button" onclick={example}>{t('journey.useExample')}</button></div>
          <details><summary>{t('planner.libraryTitle')}</summary>
            <button type="button" onclick={saveMission}>{t('planner.librarySave')}</button>
            {#each library as entry (entry.id)}<div class="library-entry"><span>{entry.name || t('planner.libraryUnnamed')}</span><button type="button" onclick={() => openMission(entry)}>{t('planner.libraryOpen')}</button>
              <button type="button" onclick={() => {
                const entries = library.filter((e) => e.id !== entry.id);
                if (writeLibrary(localStorage, entries)) library = entries;
                else libraryMessage = 'planner.libraryWriteError';
              }}>{t('planner.libraryDelete')}</button></div>
            {:else}<p>{t('planner.libraryEmpty')}</p>{/each}
            {#if libraryMessage}<p role="status">{t(libraryMessage)}</p>{/if}
          </details>
        {:else if step === 1}
          <div class="choices" role="group" aria-label={t('journey.assignSite')}>
            <button type="button" aria-pressed={selectFor === 'A'} onclick={() => { selectFor = 'A'; picked = null; }}>{t('planner.siteA')}</button>
            {#if draft.input.mode === 'sites'}<button type="button" aria-pressed={selectFor === 'B'} onclick={() => { selectFor = 'B'; picked = null; }}>{t('planner.siteB')}</button>{/if}
          </div>
          <div class="site-workspace">
            <div class="globe-panel">
              <div class="choices" role="group" aria-label={t('map.view')}>
                <button type="button" aria-pressed={mapView === 'globe'} onclick={() => { mapView = 'globe'; }}>{t('map.globe')}</button>
                <button type="button" aria-pressed={mapView === 'polar'} onclick={() => { mapView = 'polar'; }}>{t('map.polar')}</button>
              </div>
              {#if mapView === 'polar'}
                <SitePolarMap sites={allSites.map((x) => ({ id: x.id, name: x.name, lat: x.lat_deg, lon: x.lon_deg_east }))}
                  assigned={{ A: draft.input.siteA, ...(draft.input.mode === 'sites' ? { B: draft.input.siteB } : {}) }} {picked}
                  onmarker={changeSite} onpick={(lat, lon) => { picked = { lat, lon }; }} />
              {:else}
              {#await import('../../shell/GlobePicker.svelte') then m}
                <m.default lat={selectedCoords?.lat ?? null} lon={selectedCoords?.lon ?? null}
                  markers={allSites.map((s) => ({ id: s.id, name: s.name, lat: s.lat_deg, lon: s.lon_deg_east }))} onmarker={changeSite}
                  onpick={(lat, lon) => { picked = { lat, lon }; }} />
              {:catch}<p role="alert">{t('custom.globeFailed')}</p>{/await}
              {/if}
              {#if picked}
                <label for="journey-custom-name">{t('custom.name')}</label><input id="journey-custom-name" maxlength="40" bind:value={customName} />
                <button type="button" onclick={addPickedSite}>{t('journey.usePoint', { scenario: selectFor })}</button>
                {#if customError}<p role="alert">{t(customError)}</p>{/if}
              {/if}
            </div>
            <div>
              <label for="journey-site-search">{t('journey.searchSites')}</label><input id="journey-site-search" type="search" bind:value={search} />
              <div class="site-list" role="group" aria-label={t('journey.siteCatalog')}>
                {#each allSites.filter((s) => s.name.toLowerCase().includes(search.toLowerCase())) as s (s.id)}
                  <button type="button" class="site-card" aria-pressed={(selectFor === 'A' ? draft.input.siteA : draft.input.siteB) === s.id} onclick={() => changeSite(s.id)}>
                    <strong>{s.name}</strong><span>{s.lat_deg.toFixed(4)}°, {s.lon_deg_east.toFixed(4)}° E</span>
                    <small>{t(s.verified ? 'journey.catalogSource' : 'journey.userCoordinates')} · {t(s.dem_covered ? 'journey.terrainAvailable' : 'journey.terrainCheck')}</small>
                  </button>
                {:else}<p>{t('journey.noSites')}</p>{/each}
              </div>
            </div>
          </div>
          <details class="auto-sites" data-testid="auto-sites" ontoggle={(e) => { if ((e.currentTarget as HTMLDetailsElement).open) finderMounted = true; }}>
            <summary>{t('planner.autoSites.title')}</summary>
            <p class="note">{t('planner.autoSites.intro')}</p>
            {#if finderMounted}<SiteFinder defaults={{ start: draft.input.start, days: draft.input.days }} onusesites={useFound} canB={draft.input.mode === 'sites'} />{/if}
          </details>
          <details><summary>{t('journey.customCoordinates')}</summary><CustomSiteControl onadd={changeSite} /></details>
          <SitesLibrary sites={catalog} />
          <p class="note">{t('journey.terrainNote')}</p>
        {:else if step === 2}
          <div class="field-grid">
            <div><label for="journey-start">{t(draft.input.mode === 'dates' ? 'planner.startA' : 'planner.start')} (UTC)</label><input id="journey-start" type="datetime-local" min={dateBounds?.min} max={dateBounds?.max} bind:value={draft.input.start} /></div>
            {#if draft.input.mode === 'dates'}<div><label for="journey-start-b">{t('planner.startB')} (UTC)</label><input id="journey-start-b" type="datetime-local" min={dateBounds?.min} max={dateBounds?.max} bind:value={draft.input.startB} /></div>{/if}
            {#if ephemerisRange}<p>{t('planner.ephemerisRange', { start: ephemerisRange.start_utc.replace('T', ' ').replace('Z', ''), end: ephemerisRange.end_utc.replace('T', ' ').replace('Z', '') })}</p>{/if}
          </div>
          <fieldset><legend>{t('planner.duration')}</legend><div class="choices">{#each [1, 3, 7] as days}<button type="button" aria-pressed={draft.input.days === days} onclick={() => draft!.input.days = days}>{t('journey.days', { days })}</button>{/each}</div></fieldset>
          <div class="field-grid">
            <div><label for="journey-days">{t('journey.customDuration')}</label><input id="journey-days" type="number" min=".01" max="366" step=".01" bind:value={draft.input.days} onchange={autoStep} /></div>
            <div><label for="journey-resolution">{t('journey.resolution')}</label><select id="journey-resolution" bind:value={draft.input.stepMin}>{#each [10, 30, 60, 180, 360, 1440] as minutes}<option value={minutes}>{minutes} min</option>{/each}</select></div>
          </div>
          <p class="note">{t('journey.sampleCount', { count: count ?? '—', max: 1500 })}</p>
          {#if autoStepNote}<p class="note" role="status" data-testid="auto-step">{t('journey.stepAuto', autoStepNote)}</p>{/if}
          <p>{t('journey.periodNote')}</p>
        {:else if step === 3}
          <fieldset><legend>{t('planner.panelOrientation')}</legend><div class="choices">
            {#each [{ id: 'horizontal', label: 'planner.panelHorizontal', symbol: '▰' }, { id: 'tilted', label: 'planner.panelTilted', symbol: '◩' }, { id: 'tracking', label: 'planner.panelTracking', symbol: '☀' }] as orientation}
              <button type="button" class="choice" aria-pressed={draft.panel.orientation === orientation.id} onclick={() => draft!.panel.orientation = orientation.id}><span class="orientation-icon" aria-hidden="true">{orientation.symbol}</span>{t(orientation.label as MessageKey)}</button>
            {/each}
          </div></fieldset>
          <div class="panel-illustration" aria-hidden="true"><span>☀</span><div class="solar-panel" style:transform={`rotate(${draft.panel.orientation === 'horizontal' ? 0 : -(draft.panel.tilt_deg ?? 30)}deg)`}></div></div>
          <p class="note">{t('journey.panelIllustration')}</p>
          <ParameterControl id="journey-area" label={t('planner.panelArea')} bind:value={draft.panel.array_area_m2} min={param('array_area_m2')!.min!} max={param('array_area_m2')!.max!} step={.01} unit="m²" tag={param('array_area_m2')!.status} source={param('array_area_m2')!.source} />
          <ParameterControl id="journey-efficiency" label={t('planner.panelEfficiency')} bind:value={draft.panel.cell_efficiency} min={param('cell_efficiency')!.min!} max={param('cell_efficiency')!.max!} step={.005} hint={t('journey.efficiencyHint')} tag={param('cell_efficiency')!.status} source={param('cell_efficiency')!.source} />
          {#if draft.panel.orientation === 'tilted'}
            <ParameterControl id="journey-tilt" label={t('planner.panelTilt')} bind:value={draft.panel.tilt_deg} min={param('tilt_deg')!.min!} max={param('tilt_deg')!.max!} unit="°" tag={param('tilt_deg')!.status} source={param('tilt_deg')!.source} />
            <ParameterControl id="journey-azimuth" label={t('planner.panelAzimuth')} bind:value={draft.panel.tilt_azimuth_deg} min={param('tilt_azimuth_deg')!.min!} max={param('tilt_azimuth_deg')!.max!} unit="°" tag={param('tilt_azimuth_deg')!.status} source={param('tilt_azimuth_deg')!.source} />
          {/if}
          <button type="button" onclick={() => { const p = panelDefaults(parameters); if (p) draft!.panel = p; }}>{t('journey.resetPanel')}</button>
          <p class="note">{t('journey.energyDefaultNote')}</p>
          {#if draft.planning?.reliability?.enabled}<p class="note pointer">{t('journey.reliabilityPointer')} <button type="button" onclick={() => go(4)}>{t('journey.openReliability')}</button></p>{/if}
        {:else if step === 4}
          {#if draft.planning?.reliability}<ReliabilityInputs bind:profile={draft.planning.reliability} />{/if}
          {#if draft.planning?.reliability?.enabled}
            {#if run && !stale && shownReliability}<ReliabilityResults result={shownReliability} />
            {:else if !reliabilityIssue && !reliabilityBusy && !reliabilityError}<p class="note" role="status">{t('journey.reliabilityPending')}</p>{/if}
          {/if}
        {:else if step === 5}
          <fieldset><legend>{t('planner.radioPreset')}</legend><div class="choices">{#each Object.keys(RADIO_PRESETS) as id}
            <button type="button" class="choice" aria-pressed={preset === id} onclick={() => applyPreset(id as RadioPresetId)}>{t(presetLabels[id as RadioPresetId])}</button>
          {/each}</div></fieldset>
          <p class="note">{t('planner.presetNote')}</p>
          <div class="control-grid">
            <ParameterControl id="journey-mast" label={t('planner.mast')} bind:value={draft.radio.mast} min={.1} max={100} step={.1} unit="m" />
            <ParameterControl id="journey-gain" label={t('planner.radioGain')} bind:value={draft.radio.gain} min={-10} max={45} step={.5} unit="dBi" />
          </div>
          <div class="field-grid">
            <div><label for="journey-rate">{t('planner.radioRate')}</label><select id="journey-rate" bind:value={draft.radio.rate}>{#each [10000, 30000, 100000, 300000, 1000000, 3000000] as rate}<option value={rate}>{rate < 1000000 ? `${rate / 1000} kbit/s` : `${rate / 1000000} Mbit/s`}</option>{/each}</select></div>
            <div><label for="journey-station">{t('planner.station')}</label><select id="journey-station" bind:value={draft.radio.station}><option value="dsn34">DSN 34 m</option><option value="dsn18">DSN 18 m</option></select></div>
          </div>
          <p>{t('journey.bitrateHint')}</p>
          <details><summary>{t('journey.advanced')}</summary><ParameterControl id="journey-k" label={t('planner.radioK')} bind:value={draft.radio.k} min={0} max={6} step={.01} /> <p>{t('planner.radioSettingsNote')}</p></details>
          <details open={waveOpen} ontoggle={(e) => waveOpen = e.currentTarget.open}><summary>{t('journey.waveTitle')}</summary>
            <p class="warning">{t('journey.waveNote')}</p>
            {#if waveOpen}{#await import('../wave/Wave.svelte') then m}<m.default embedded />{:catch}<p role="alert">{t('journey.visualFailed')}</p>{/await}{/if}
          </details>
        {:else if step === 6}
          <button class="primary" type="button" disabled={running || firstIssue < 6} onclick={calculate}>{t(running ? 'planner.calculating' : 'journey.simulate')}</button>
          {#if running}<p role="status">{t('journey.computing')}</p><progress max={calcTotal} value={calcDone} aria-label={t('journey.calcProgress', { done: calcDone, total: calcTotal })}></progress> <span class="note">{t('journey.calcProgress', { done: calcDone, total: calcTotal })}</span><button type="button" onclick={() => { controller?.abort(); running = false; error = 'journey.cancelled'; }}>{t('journey.cancel')}</button>{/if}
          {#if run}
            {#if stale}<p class="warning" role="status">{t('journey.stale')}</p>{/if}
            {#if !stale}
              <div class="replay">
                <button type="button" onclick={() => { if (!playing && index >= (active?.steps?.time_unix.length ?? 1) - 1) index = 0; playing = !playing; }}>{t(playing ? 'planner.replayPause' : 'planner.replayPlay')}</button>
                <label for="journey-speed">{t('planner.replaySpeed')}</label><select id="journey-speed" bind:value={speed}><option value={2000}>{t('planner.replaySlow')}</option><option value={1000}>{t('planner.replayNormal')}</option><option value={500}>{t('planner.replayFast')}</option></select>
              </div>
              <p class="note">{t('journey.replayNote')}</p>
              <button type="button" aria-expanded={previewScene} onclick={() => previewScene = !previewScene}>{t('journey.openScene')}</button>
              {#if previewScene && !sceneReady}<p class="note" role="status">{t('journey.scenePreparing')}</p>{/if}
              {#if previewScene && sceneReady && activeId && Number.isFinite(sceneMs)}
                {#await import('../lander/Lander.svelte') then m}<m.default embedded compact plannerSite={activeId} plannerMs={sceneMs} plannerCustomSite={activeCustom}
                  plannerRadio={{ station: draft.radio.station, gain: draft.radio.gain!, rate: draft.radio.rate!, mast: draft.radio.mast! }} />{:catch}<p role="alert">{t('journey.visualFailed')}</p>{/await}
                <p class="note">{t('journey.sceneNote')}</p>
              {/if}
            {/if}
            <div class:previous={stale}>
              <JourneyResults {run} objectives={stale ? run.config.objectives : draft.objectives} bind:scenario bind:index />
            </div>
            {#if !stale && plan?.reliability?.enabled}<p class="note pointer">{t('journey.reliabilityPointer')} <button type="button" onclick={() => go(4)}>{t('journey.openReliability')}</button></p>{/if}
          {/if}
        {:else if step === 7 && run && !stale && draft.planning}
          {#if draft.planning.reliability?.enabled}<p class="note pointer">{t('journey.reliabilityPointer')} <button type="button" onclick={() => go(4)}>{t('journey.openReliability')}</button></p>{/if}
          <ReportDossier bind:planning={draft.planning} budget={shownBudget} carbon={shownCarbon} busy={budgetBusy}
            bind:allowExternal={reportAllowExternal} cloudAvailable={reportCloudAvailable}
            mode={reportMode} setMode={setReportMode} objectives={draft.objectives} editMission={() => go(0)}
            progress={dossierProgress(draft, run.evaluations, shownBudget, shownCarbon)}
            canOpenReport={!(budgetBusy || dossierIssue || budgetError || reliabilityBlocked)} openReport={() => go(8)}
            error={budgetError ? t(budgetError) : null} {siBusy} siError={siError ? t(siError) : null}
            generate={generateNarrative} clearSi={() => { if (draft?.planning) delete draft.planning.si; }} />
          <div class="decision-field"><label for="journey-decision">{t('planner.decisionPrompt')}</label><textarea id="journey-decision" maxlength="2000" rows="3" bind:value={draft.decision}></textarea></div>
          {#if reportCloudStatusError}<p role="alert">{t('si.unreachable')}</p>{/if}
        {:else if step === 8 && run && !stale}
          {@const reportRun = run}
          {@const reportDraft = draft}
          <div class="report-bar" data-testid="report-bar">
            <ReportModeSwitch compact mode={reportMode} onchange={setReportMode} name="report-mode-report" />
            <button class="primary" type="button" data-testid="download-pdf" disabled={!verdictDone || !overlaysDone || pdfBusy || budgetBusy || !!dossierIssue || !!budgetError || reliabilityBlocked || (reportSections.seal && !certificate) || !pages.compact} onclick={downloadPdf}>{t(pdfBusy ? 'journey.pdfBusy' : 'journey.downloadPdf')}</button>
            <details class="more-menu" data-testid="report-more"><summary>{t('report.more')}</summary>
              <div class="more-items"><button type="button" disabled={budgetBusy || !!dossierIssue || !!budgetError || reliabilityBlocked || (reportSections.seal && !certificate) || !pages.compact} onclick={() => window.print()}>{t('journey.printPdf')}</button>
                <button type="button" disabled={budgetBusy || !!dossierIssue || !!budgetError || reliabilityBlocked || (reportSections.seal && !certificate) || !pages.compact} onclick={exportReport}>{t('journey.downloadJson')}</button>
                <button type="button" onclick={() => go(7)}>{t('dossier.edit')}</button></div>
            </details>
          </div>
          <p class="note">{t('report.englishOnly')}</p>
          {#if reportMode === 'expert' && draft.planning?.sections}<details class="report-options" data-testid="report-customise"><summary>{t('report.customise')}</summary><ReportSectionPicker bind:selection={draft.planning.sections} pages={pages.compact} /></details>{/if}
          {#if !verdictDone || !overlaysDone}<p role="status" class="note" data-testid="pdf-wait">{t('journey.pdfWaitVerdict')}</p>{/if}
          {#if pdfNote}<p role="status" data-testid="pdf-note">{t(pdfNote === 'pdfUnavailable' ? 'journey.pdfUnavailable' : 'journey.pdfFailed')}</p>{/if}
          {#if dossierIssue || budgetError}<p role="alert">{t(dossierIssue ?? budgetError!)}</p>{/if}
          <article class="report-preview compact-report" bind:this={reportEl} use:reportToc={(e) => tocEntries = e} use:reportLayout={{ ready: (!reportSections.seal || !!certificate) && !!shownCarbon && !reliabilityBlocked, onpages: updatePages }}>
            <LifecycleReport onverdict={(d) => { verdictDone = d; }} onoverlays={(d) => { overlaysDone = d; }} draft={reportDraft} {economics} evaluations={reportRun.evaluations} budget={shownBudget} carbon={shownCarbon} reliability={shownReliability} {certificate} {certificateError}
              {validation} registry={parameterRegistry} expert={reportMode === 'expert'} created={reportRun.createdAt} toc={tocEntries}
              identity={{ model_version: reportRun.evaluations[0]!.model_version, registry_sha256: reportRun.evaluations[0]!.registry_sha256 }} />
          </article>
        {:else if step >= 7}
          <p role="status" class="warning">{t('journey.stale')}</p><button type="button" onclick={() => go(6)}>{t('journey.compare')}</button>
        {/if}
        {#if currentIssue}<p class="warning" role="alert">{t(currentIssue)}</p>{/if}
        {#if error}<p class="warning" role="alert">{t(error)}{errorStatus && error === 'planner.errorServer' ? ` (HTTP ${errorStatus})` : ''}</p>{/if}
        {#if step >= 4 && plan?.reliability?.enabled}
          {#if reliabilityIssue}<p class="warning" role="alert">{t('rel.invalid')}</p>{/if}
          {#if reliabilityBusy}<p role="status">{t('rel.busy')}</p>{/if}
          {#if reliabilityError}<p class="warning" role="alert">{t('rel.error')}</p><button type="button" onclick={() => reliabilityRetry++}>{t('rel.retry')}</button>{/if}
        {/if}
        <footer class="step-actions">
          <button type="button" disabled={step === 0 || running} onclick={() => go(step - 1)}>{t('planner.back')}</button>
          {#if step < 8}<button class="primary" type="button" disabled={running || !!currentIssue || (step === 6 && (!run || stale)) || (step === 7 && (budgetBusy || !!dossierIssue || !!budgetError || reliabilityBlocked))} onclick={() => go(step + 1)}>{t(step === 6 || step === 7 ? 'journey.prepareReport' : 'journey.continue')}</button>{/if}
        </footer>
      </section>
    </div>
  {/if}
</div>

<style>
  .journey { padding-block: 2rem 5rem; }
  .journey-header { display: flex; justify-content: space-between; align-items: start; gap: 1rem; margin-bottom: 2rem; }
  h1, h2 { font-family: Orbitron, var(--font-sans); letter-spacing: -.025em; } h1 { font-size: clamp(1.6rem, 3vw, 2.5rem); margin: .4rem 0; }
  .eyebrow { color: #a4dfff; font-size: .73rem; letter-spacing: .14em; text-transform: uppercase; }
  .save-state, .note { color: var(--c-muted); font-size: .85rem; } .save-state { max-width: 20rem; }
  .stepper ol { list-style: none; display: grid; grid-template-columns: repeat(8, 1fr); gap: .35rem; padding: 0; margin-bottom: 2rem; }
  .stepper button { width: 100%; display: grid; gap: .5rem; text-align: start; background: transparent; border: 0; border-top: 2px solid #6f87934d; border-radius: 0; padding: .8rem .35rem; font-size: .8rem; }
  .stepper button[aria-current='step'] { border-color: #9bdfff; color: #c9efff; background: linear-gradient(#9bdfff15, transparent); }
  .step-number { font: 500 .75rem Orbitron, sans-serif; color: #9bdfff; }
  .workspace { display: block; }
  .step-body { min-width: 0; border: 1px solid #7499b64d; border-radius: 1.4rem; padding: clamp(1rem, 3vw, 2rem); background: linear-gradient(140deg, #10243be6, #080f1de6); box-shadow: 0 15px 70px #00000028; }
  .step-heading { margin-bottom: 2rem; } .step-heading p:last-child { color: var(--c-muted); max-width: 60ch; line-height: 1.6; }
  .step-heading h2 { scroll-margin-top: 7rem; }
  label { display: block; font-weight: 600; margin-bottom: .5rem; }
  input:not([type='checkbox']):not([type='range']), select, textarea { width: 100%; min-width: 0; box-sizing: border-box; min-height: 46px; background: #081426; color: #e4effa; border: 1px solid #7b9cb36e; border-radius: .65rem; padding: .7rem; }
  input[type='checkbox'] { min-width: 1.2rem; min-height: 1.2rem; accent-color: #9bdfff; } .check { display: flex; gap: .6rem; align-items: center; margin-block: 1rem; }
  button { min-height: 44px; padding: .7rem 1rem; border: 1px solid #7693aa69; border-radius: .65rem; background: #11263c; color: #e8f4ff; cursor: pointer; }
  button:disabled { opacity: .45; cursor: not-allowed; } button[aria-pressed='true'] { border-color: #9bdfff; background: #20425b; }
  button:focus-visible, input:focus-visible, select:focus-visible, summary:focus-visible, textarea:focus-visible { outline: 2px solid #b1e6ff; outline-offset: 3px; }
  .primary { background: #b5e5fb; color: #081322; font-weight: 700; border-color: transparent; }
  fieldset { border: 0; padding: 0; margin: 1.5rem 0; } legend { margin-bottom: .8rem; font-weight: 600; }
  .choices { display: flex; gap: .7rem; flex-wrap: wrap; margin-block: .75rem; } .choice { flex: 1; min-width: 9rem; text-align: start; }
  .orientation-icon { display: block; font-size: 2rem; margin-bottom: .5rem; color: #b4e9ff; }
  .field-grid, .control-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 1.5rem; margin-block: 1.5rem; }
  .step-body :global(.parameter) { margin-block: 1.5rem; }
  .example, details { margin-block: 1.5rem; border-top: 1px solid #7499b64d; padding-top: 1rem; }
  .site-workspace { display: grid; grid-template-columns: minmax(0, .85fr) minmax(0, 1fr); gap: 1.3rem; margin-top: 1.5rem; }
  .globe-panel { min-width: 0; } .site-list { max-height: 32rem; overflow-y: auto; display: grid; gap: .6rem; margin-top: .75rem; }
  .site-card { text-align: start; display: grid; gap: .4rem; width: 100%; } .site-card span, .site-card small { color: var(--c-muted); }
  .panel-illustration { display: flex; justify-content: center; align-items: center; gap: 4rem; min-height: 10rem; background: radial-gradient(ellipse at 30% 20%, #8bbde52b, transparent); border-radius: 1rem; }
  .panel-illustration > span { font-size: 3rem; color: #ffe1a0; }
  .solar-panel { width: 8rem; height: 3rem; background: repeating-linear-gradient(90deg, transparent 0 1.85rem, #8cd6ff 1.85rem 2rem), repeating-linear-gradient(0deg, #18395b 0 .85rem, #8cd6ff .85rem 1rem); border: 2px solid #9bdfff; }
  .warning { padding: .85rem; background: #e8ab3c12; border-inline-start: 3px solid #d6ba7c; line-height: 1.5; }
  .step-actions { display: flex; justify-content: space-between; gap: 1rem; margin-top: 2.5rem; padding-top: 1.5rem; border-top: 1px solid #7499b64d; }
  .more-menu summary { min-height: 44px; display: inline-flex; align-items: center; cursor: pointer; padding-inline: .5rem; } .more-items { display: flex; flex-wrap: wrap; gap: .5rem; margin-block: .5rem; }
  .decision-field { margin-block: 1rem; display: grid; gap: .4rem; } .report-options { margin-block: .5rem; }
  .report-bar, .replay { display: flex; gap: .75rem; align-items: center; flex-wrap: wrap; margin-block: 1rem; } .replay select { width: auto; }
  .report-preview { --c-muted: #526170; margin-top: 2rem; padding: clamp(1rem, 3vw, 2rem); color: #172a3a; background: #fff; color-scheme: light; border: 1px solid #dce4ea; border-radius: .25rem; box-shadow: 0 12px 40px #00000020; overflow-wrap: anywhere; } .previous { opacity: .7; }
  .visual-stage { border: 1px solid #7499b64d; border-radius: 1rem; padding: 1rem; margin-bottom: 2rem; background: #071524; min-width: 0; }
  .library-entry { display: flex; justify-content: space-between; gap: 1rem; align-items: center; margin-block: .75rem; }
  .compact-report { font: 9.5pt/1.25 Arial, sans-serif; }
  .compact-report :global(p) { max-inline-size: none; line-height: 1.25; margin-block: 1.2mm; }
  .compact-report :global(h2) { font: 700 15pt/1.2 Arial, sans-serif; margin-block: 2mm; }
  .compact-report :global(h3) { font: 700 11pt/1.2 Arial, sans-serif; margin-block: 2.5mm 1.5mm; }
  .compact-report :global(h4) { font: 700 10pt/1.2 Arial, sans-serif; margin-block: 2mm 1mm; }
  .compact-report :global(h5), .compact-report :global(h6) { font-size: 9pt; margin-block: 1.5mm 1mm; }
  .compact-report :global(.phase) { padding-block: 2mm; border-color: #b6c8d1; }
  .compact-report :global(.phase > h3) { border-inline-start: 1mm solid #173c4a; padding-inline-start: 2mm; color: #173c4a; }
  .compact-report :global(.pending) { gap: 1mm 4mm; margin-block: 1.5mm; }
  .compact-report :global(.pending > div) { border-top: 1px solid #e1e7eb; padding-top: .5mm; }
  .compact-report :global(dl div) { margin-block: .6mm; }
  .compact-report :global(dt) { font-size: 9pt; }
  .compact-report :global(dd) { margin-block: .5mm; }
  .compact-report :global(ul) { padding-inline-start: 4mm; margin-block: 1.5mm; }
  .compact-report :global(li) { margin-block: .5mm; }
  .compact-report :global(.scope), .compact-report :global(.status) { padding: 1mm 2mm; border-color: #b89152; background: #faf7f0; }
  .compact-report :global(.status) { font-size: 8pt; padding-block: .7mm; }
  .compact-report :global(a) { color: #23546a; text-underline-offset: .12em; }
  .compact-report :global(.results) { gap: 2mm; }
  .compact-report :global(.candidate) { border: 1px solid #b6c8d1; border-top: 2px solid #173c4a; border-radius: 0; padding: 2mm; background: #f5f8fa; }
  .compact-report :global(.candidate .eyebrow) { color: #173c4a; font-family: Arial, sans-serif; }
  .compact-report :global(.candidate dl) { gap: 1mm; }
  .compact-report :global(.candidate p), .compact-report :global(.note) { font-size: 8.5pt; }
  .compact-report :global(.graphs) { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 2mm 4mm; }
  .compact-report :global(.graphs > h3) { grid-column: 1 / -1; }
  .compact-report :global(.chart) { margin: 0; break-inside: avoid; }
  .compact-report :global(.chart p) { font-size: 8pt; }
  .compact-report :global(.chart svg) { height: 25mm; }
  .compact-report :global(.composition-chart svg) { width: 30mm; height: 30mm; }
  .compact-report :global(.chart .axis) { font-size: 7pt; gap: 2mm; }
  .compact-report :global(.chart .y-axis) { font-size: 7.5pt; padding-block: 1mm; }
  .compact-report :global(.chart .plot) { grid-template-columns: 9mm minmax(0, 1fr); gap: 1mm; }
  .compact-report :global(table) { border-collapse: collapse; line-height: 1.2; font-size: 8pt; }
  .compact-report :global(th), .compact-report :global(td) { padding: .8mm 1mm; vertical-align: top; }
  .compact-report :global(thead th) { background: #eaf0f4; border-block: 1px solid #b6c8d1; color: #173c4a; }
  .compact-report :global(tbody th), .compact-report :global(tbody td) { border-bottom: 1px solid #e1e7eb; }
  .compact-report :global(tbody tr:nth-child(even)) { background: #f5f8fa; }
  .compact-report :global(td) { font-variant-numeric: tabular-nums; }
  .compact-report :global(.signature) { display: grid; grid-template-columns: 32mm minmax(0, 1fr); column-gap: 4mm; margin-block-start: 3mm; padding-block-start: 2mm; border-color: #b6c8d1; }
  .compact-report :global(.signature > h3), .compact-report :global(.blockchain) { grid-column: 1 / -1; }
  .compact-report :global(.signature > .seal) { grid-column: 1; grid-row: 2 / span 3; align-self: center; }
  .compact-report :global(.signature > p) { grid-column: 2; }
  .compact-report :global(.blockchain) { border-top: 1px solid #e1e7eb; margin-top: 2mm; }
  .compact-report :global(.seal) { width: 30mm; min-height: 30mm; gap: 1mm; border-width: 2px; }
  .compact-report :global(.seal img) { width: 20mm; height: auto; }
  .compact-report :global(.seal strong) { font-size: 10pt; }
  .compact-report :global(.seal span) { font-size: 6.5pt; max-width: 25mm; }
  .compact-report :global(.registry) { font: 7.5pt/1.3 ui-monospace, monospace; color: #526170; }
  .compact-report :global(.evidence) { font-size: 7.5pt; color: #526170; }
  .compact-report :global(.si-proposal) { padding: 2mm; }
  .compact-report :global(.document-environment) { margin-block-start: 3mm; padding: 2mm 3mm; border: 1px solid #bdcfc4; background: #f3f8f4; }
  :global(.report-measure .pending), :global(.report-measure .comparison) { grid-template-columns: 1fr 1fr; }
  @media (max-width: 1050px) { .site-workspace { grid-template-columns: 1fr 1fr; } }
  @media (max-width: 650px) { .journey { padding-top: 1rem; } .journey-header { flex-direction: column; } .stepper { overflow-x: auto; } .stepper ol { min-width: 43rem; } .site-workspace, .field-grid, .control-grid { grid-template-columns: 1fr; } .globe-panel { display: grid; justify-items: center; } .step-actions { position: sticky; bottom: 0; background: #0c192b; padding: 1rem .5rem; z-index: 20; } .step-body { padding-bottom: 0; } .compact-report:not(.report-measure) :global(.graphs) { grid-template-columns: 1fr; } }
  @media print {
    :global(body *) { visibility: hidden; }
    .report-preview, .report-preview :global(*) { visibility: visible; }
    :global(.global-nav), :global(.site-footer), :global(.skip-link),
    .journey-header, .stepper, .step-body > :not(.report-preview) { display: none; }
    .journey { page: raven-mission; padding: 0; }
    .workspace { display: block; }
    .step-body { border: 0; padding: 0; box-shadow: none; background: white; }
    .report-preview { margin: 0; border: 0; border-radius: 0; box-shadow: none; color: #172a3a; background: white; print-color-adjust: exact; -webkit-print-color-adjust: exact; }
    .report-preview { box-sizing: border-box; width: 210mm; max-width: 100%; padding: 10mm 10mm 15mm; box-decoration-break: clone; -webkit-box-decoration-break: clone; }
    .report-preview :global(a) { color: inherit; text-decoration-color: #9cabb4; }
    .report-preview :global(p), .report-preview :global(li), .report-preview :global(dd) { orphans: 2; widows: 2; }
    .report-preview :global(tr) { break-inside: avoid; }
    .report-preview :global(.parameter-table) { overflow: visible; }
    .compact-report:not(.report-measure) :global(.graphs) { grid-template-columns: 1fr 1fr; }
    .report-preview :global(.graphs), .report-preview :global(.windows) { break-inside: auto; }
    .report-preview :global(.pending) { grid-template-columns: 1fr 1fr; }
    .report-preview :global(.chart), .report-preview :global(.candidate), .report-preview :global(.signature), .report-preview :global(.document-environment) { break-inside: avoid; }
    .report-preview :global(h2), .report-preview :global(h3), .report-preview :global(h4), .report-preview :global(h5), .report-preview :global(h6) { break-after: avoid; }
  }
  @page raven-mission { size: A4; margin: 0; }
</style>
