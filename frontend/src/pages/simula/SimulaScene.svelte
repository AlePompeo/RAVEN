<!-- SPDX-License-Identifier: Apache-2.0 -->
<!--
  Simula, scheda "Scena": l'esperienza interattiva principale (docs/design/grazinglink-ux.md). Scena 3D della Scena lander
  (o la sezione laterale in Canvas 2D senza WebGL) guidata dai controlli, indicatore grande del margine con la frase e
  l'indicatore di validità, grafico margine-elevazione, mappa di validità; tutto calcolato nel browser (linkModel.ts)
  mentre si muovono i controlli. Scenario manuale = crinale sintetico su terreno piano ("Scenario didattico"); con
  "Usa un sito reale" la scena e il margine vengono da /api/raven/scene (LOLA) e i controlli regolano solo antenna,
  dati al secondo e tempo. Learning e Avanzato: stessi numeri, cambia cosa si vede (e cosa va nell'URL).
-->
<script lang="ts">
  import ModelStamp from '../../shell/ModelStamp.svelte';
  import { onDestroy, onMount, untrack } from 'svelte';
  import { formatNumber, t, type MessageKey } from '../../i18n/i18n.svelte';
  import SubNav from '../../components/ui/SubNav.svelte';
  import SceneSettings from '../../components/ui/SceneSettings.svelte';
  import Badge from '../grazinglink/Badge.svelte';
  import { downloadText, fetchDefaults, type Defaults, type Site } from '../grazinglink/grazing';
  import { FALLBACK_SUN, SceneClient, type LanderScene, type SceneError } from '../lander/model';
  import { buildTerrain, clampCam, orbit, PRESETS as VIEWS, presetCamera, zoomBy, type LanderViewState, type Preset } from '../lander/view';
  import { landerViewportFactory } from '../lander/landerViewport';
  import { mountViewport, type ViewportHandle } from '../../viewports/port';
  import { detectQuality } from '../../viewports/quality';
  import type { ViewportMode } from '../../viewports/select';
  import { modeNow } from '../../shell/modeState.svelte';
  import { announce } from '../../shell/a11y';
  import { msToT, scenarioStore, tToMs } from '../../shell/scenario';
  import { customSites as customStore, isCustomId, type CustomSiteDef } from '../../shell/customSites';
  import { customAsSiteInfo, raven } from '../../shell/ravenApi';
  import CustomSiteControl from '../../shell/CustomSiteControl.svelte';
  import { clearPageContext, setPageContext } from '../../shell/pageContext.svelte';
  import { sanitizeParams } from '../chat/assistant';
  import Gauge from './Gauge.svelte';
  import NumSlider from './NumSlider.svelte';
  import MarginChart from './MarginChart.svelte';
  import ValidityMap from './ValidityMap.svelte';
  import { setWaveHandoff } from './handoff';
  import {
    computeLink,
    DEFAULT_INPUT,
    marginChart,
    parseCompTable,
    RANGES,
    RATES_BPS,
    sanitizeInput,
    validityHeat,
    variants,
    type CompTable,
    type LinkInput,
    type LinkOutput,
  } from './linkModel';
  import { inputFromScene, syntheticScene } from './simScene';
  import { advanceMission, exportCsv, exportJson, fmt, newMission, parseSimQuery, PRESETS, sentence, STR as S_BASE, writeSimQuery, type PresetId } from './simState';

  let { hideReal = false, embedded = false, forceReal = false, hideRealToggle = false }: {
    hideReal?: boolean; embedded?: boolean; forceReal?: boolean; hideRealToggle?: boolean;
  } = $props();

  const STR = $derived({
    title: t('sim.ui.title'),
    learn: t('sim.ui.learn'),
    didactic: t('sim.ui.didactic'),
    realSite: (site: string) => t('sim.ui.realSite', { site }),
    useReal: t('sim.ui.useReal'),
    useRealHint: t('sim.ui.useRealHint'),
    site: t('sim.ui.site'),
    time: t('sim.ui.time'),
    timeText: (date: string) => date,
    controls: t('sim.ui.controls'),
    presets: t('sim.ui.presets'),
    el: t('sim.ui.el'),
    elAdv: t('sim.ui.elAdv'),
    ridge: t('sim.ui.ridge'),
    ridgeAdv: t('sim.ui.ridgeAdv'),
    radius: t('sim.ui.radius'),
    radiusAdv: t('sim.ui.radiusAdv'),
    dia: t('sim.ui.dia'),
    diaAdv: t('sim.ui.diaAdv'),
    rate: t('sim.ui.rate'),
    rateAdv: t('sim.ui.rateAdv'),
    tips: {
      el: t('sim.ui.tip.el'),
      ridge: t('sim.ui.tip.ridge'),
      radius: t('sim.ui.tip.radius'),
      dia: t('sim.ui.tip.dia'),
      rate: t('sim.ui.tip.rate'),
      margin: t('sim.ui.tip.margin'),
      fresnel: t('sim.ui.tip.fresnel'),
    },
    adv: {
      freq: t('sim.ui.adv.freq'),
      d1: t('sim.ui.adv.d1'),
      mast: t('sim.ui.adv.mast'),
      perr: t('sim.ui.adv.perr'),
      ptx: t('sim.ui.adv.ptx'),
      tsys: t('sim.ui.adv.tsys'),
      ebn0: t('sim.ui.adv.ebn0'),
      loss: t('sim.ui.adv.loss'),
      eta: t('sim.ui.adv.eta'),
      dist: t('sim.ui.adv.dist'),
      station: t('sim.ui.adv.station'),
      corr: t('sim.ui.adv.corr'),
      mp: t('sim.ui.adv.mp'),
      eps: t('sim.ui.adv.eps'),
      epsi: t('sim.ui.adv.epsi'),
      sig: t('sim.ui.adv.sig'),
      vex: t('sim.ui.adv.vex'),
      realOnly: t('sim.ui.adv.realOnly'),
    },
    params: t('sim.ui.params'),
    variants: t('sim.ui.variants'),
    variantName: {
      knife: t('sim.ui.variant.knife'),
      rounded: t('sim.ui.variant.rounded'),
      rounded_splitstep: t('sim.ui.variant.roundedSplitstep'),
      multipath: t('sim.ui.variant.multipath'),
      antenna_script: t('sim.ui.variant.antennaScript'),
      antenna_corrected: t('sim.ui.variant.antennaCorrected'),
    },
    uncertainty: t('sim.ui.uncertainty'),
    unc: {
      corr: (value: string) => t('sim.ui.unc.correction', { value }),
      dist: (min: string, max: string) => t('sim.ui.unc.distance', { min, max }),
      sigma: (value: string) => t('sim.ui.unc.sigma', { value }),
    },
    numbers: t('sim.ui.numbers'),
    export: t('sim.ui.export'),
    json: t('sim.ui.json'),
    csv: t('sim.ui.csv'),
    flags: t('sim.ui.flags'),
    view: t('sim.ui.view'),
    modeLabel: {
      webgl: t('sim.ui.mode.webgl'),
      canvas2d: t('sim.ui.mode.canvas'),
      none: t('sim.ui.mode.none'),
    } as Record<string, string>,
    stageAria: t('sim.ui.stageAria'),
    stageAria2d: t('sim.ui.stageAria2d'),
    viewError: t('sim.ui.viewError'),
    loading: t('sim.ui.loading'),
    sitesError: t('sim.ui.sitesError'),
    tableMissing: t('sim.ui.tableMissing'),
    realChartNote: t('sim.ui.realChartNote'),
    realMapNote: t('sim.ui.realMapNote'),
    restart: t('sim.ui.restart'),
    expect: t('sim.ui.expect'),
    exag: (factor: number) => t('sim.ui.exag', { factor }),
    glossary: t('sim.ui.glossary'),
    stepDone: (step: number) => t('sim.ui.stepDone', { step }),
    applied: t('sim.ui.applied'),
  });
  const S = $derived({
    ...S_BASE,
    rate: (bps: number, format = (value: number, digits = 0) => formatNumber(value, { maximumFractionDigits: digits })) =>
      bps >= 1e6 ? `${format(bps / 1e6)} Mbps` : `${format(bps / 1e3)} kbps`,
    sentence: {
      below: t('sim.state.sentence.below'),
      open: (margin: string, rate: string) => t('sim.state.sentence.open', { margin, rate }),
      transition: (margin: string, rate: string) => t('sim.state.sentence.transition', { margin, rate }),
      blockedSome: (margin: string, rate: string, maximum: string) => t('sim.state.sentence.blockedSome', { margin, rate, maximum }),
      blockedNone: (margin: string) => t('sim.state.sentence.blockedNone', { margin }),
    },
    state: {
      open: { ...S_BASE.state.open, word: t('sim.state.open') },
      transition: { ...S_BASE.state.transition, word: t('sim.state.transition') },
      blocked: { ...S_BASE.state.blocked, word: t('sim.state.blocked') },
    },
    validity: {
      reliable: { ...S_BASE.validity.reliable, word: t('sim.state.validity.reliable'), hint: t('sim.state.validity.reliableHint') },
      uncertain: { ...S_BASE.validity.uncertain, word: t('sim.state.validity.uncertain'), hint: t('sim.state.validity.uncertainHint') },
      outside: { ...S_BASE.validity.outside, word: t('sim.state.validity.outside'), hint: t('sim.state.validity.outsideHint') },
    },
    flag: {
      invalid_input: t('sim.state.flag.invalidInput'),
      earth_below_horizon: t('sim.state.flag.earthBelowHorizon'),
      paraxial: t('sim.state.flag.paraxial'),
      nu_outside_table: t('sim.state.flag.nuOutsideTable'),
      fresnel_oscillation: t('sim.state.flag.fresnelOscillation'),
      d1_outside_table: t('sim.state.flag.d1OutsideTable'),
      radius_unresolved: t('sim.state.flag.radiusUnresolved'),
      reflection_beyond_ridge: t('sim.state.flag.reflectionBeyondRidge'),
      correction_unavailable: t('sim.state.flag.correctionUnavailable'),
    },
    flagOk: t('sim.state.flagOk'),
    flagNa: t('sim.state.flagNa'),
    honesty: t('sim.state.honesty'),
    presets: {
      high: t('sim.state.preset.high'),
      grazing: t('sim.state.preset.grazing'),
      blocking: t('sim.state.preset.blocking'),
      small: t('sim.state.preset.small'),
    },
    mission: {
      ...S_BASE.mission,
      title: t('sim.state.mission.title'),
      done: t('sim.state.mission.done'),
      todo: t('sim.state.mission.todo'),
      all: t('sim.state.mission.all'),
      steps: S_BASE.mission.steps.map((step) => ({
        ...step,
        task: t(`sim.state.mission.${step.id}.task` as MessageKey),
        expect: t(`sim.state.mission.${step.id}.expect` as MessageKey),
      })),
    },
  });

  const quality = detectQuality();
  const store = scenarioStore();
  const scen = store.get();
  const q = parseSimQuery(location.search);
  const T0 = tToMs(scen.t) ?? Date.UTC(2027, 3, 7);
  const adv = $derived(modeNow.advanced);

  /** Nello scenario manuale la quota del crinale e il diametro sono sempre presenti (mai angolo o guadagno). */
  type UiInput = LinkInput & { ridgeHeightM: number; diameterM: number };
  let inp = $state<UiInput>(
    untrack(() => sanitizeInput({
      ...DEFAULT_INPUT,
      station: scen.station,
      ...(scen.bitrate ? { rateBps: scen.bitrate } : {}),
      ...(scen.mast !== null ? { mastM: scen.mast } : {}),
      ...q.input,
    }).input as UiInput),
  );
  const inheritedAntenna = untrack(() => ({ diameter: inp.diameterM, frequency: inp.frequencyGhz, efficiency: inp.eta }));
  let rateIdx = $state(Math.max(0, RATES_BPS.indexOf(untrack(() => inp.rateBps))));
  $effect(() => {
    inp.rateBps = RATES_BPS[rateIdx] ?? 1e5;
  });

  let table = $state.raw<CompTable | null>(null);
  let tableFailed = $state(false);
  let defaults = $state.raw<Defaults | null>(null);
  let real = $state(untrack(() => forceReal || q.real));
  let catalogSites = $state.raw<Site[]>([]);
  let customList = $state.raw<readonly CustomSiteDef[]>(customStore.get());
  $effect(() => customStore.subscribe((l) => { customList = l; }));
  // i siti personalizzati compaiono accanto a quelli del catalogo (stesso elenco, stesso modo di scena)
  const sites = $derived<Site[]>([...catalogSites, ...customList.map((c) => customAsSiteInfo(c) as unknown as Site)]);
  let siteId = $state(q.site ?? scen.site ?? '');
  const customSel = $derived(isCustomId(siteId) ? customList.find((c) => c.id === siteId) : undefined);
  let hours = $state(0);
  let realScene = $state.raw<LanderScene | null>(null);
  let realErr = $state('');
  let realBusy = $state(false);
  let sitesErr = $state('');
  let client: SceneClient | null = null;
  let vExag = $state(3); // solo disegno: a scala vera un crinale di 30 m a 2 km quasi non si vede

  const out = $derived(computeLink($state.snapshot(inp) as LinkInput, table));
  const sceneGain = $derived(real && scen.gain !== null && inp.diameterM === inheritedAntenna.diameter &&
    inp.frequencyGhz === inheritedAntenna.frequency && inp.eta === inheritedAntenna.efficiency ? scen.gain : out.gainDbi);
  const realOut = $derived(real && realScene ? computeLink(inputFromScene(realScene, $state.snapshot(inp) as LinkInput), table) : null);
  /** Quello che si mostra: il modello, oppure (sito reale) il margine e lo stato del motore sugli altri numeri del modello. */
  const shown = $derived.by<LinkOutput>(() => {
    if (!real || !realScene || !realOut || realScene.link.margin === null || realScene.link.state === 'unknown') return out;
    const m = realScene.link.margin;
    const byRate = RATES_BPS.map((r) => m - 10 * Math.log10(r / realScene!.link.rateBps));
    let max = 0;
    byRate.forEach((v, i) => v >= 0 && (max = Math.max(max, RATES_BPS[i]!)));
    return { ...realOut, marginDb: m, state: realScene.link.state, marginByRateDb: byRate, maxRateBps: max, input: { ...realOut.input, rateBps: realScene.link.rateBps } };
  });
  const said = $derived(sentence(shown, S.sentence, (value, digits) =>
    formatNumber(value, { minimumFractionDigits: digits, maximumFractionDigits: digits })));
  const reasons = $derived(shown.validity.reasons.map((c) => S.flag[c]));
  const modelInput = $derived(realOut ? realOut.input : out.input);
  const chart = $derived(marginChart(modelInput, table));
  const heat = $derived.by(() => {
    const t0 = performance.now();
    const { earthElDeg: _e, ridgeHeightM: _r, ...rest } = out.input;
    const h = validityHeat(rest, table);
    return { h, ms: performance.now() - t0 };
  });
  const vars = $derived(adv ? variants(modelInput, table) : []);
  const distRange = $derived(adv ? [computeLink({ ...modelInput, earthDistanceKm: 405_500 }, table).marginDb, computeLink({ ...modelInput, earthDistanceKm: 363_300 }, table).marginDb] : [0, 0]);

  /* ------------------------------------------------ missione ------------------------------------------------ */

  let mission = $state.raw(newMission(untrack(() => out.input)));
  $effect(() => {
    const o = out;
    if (real) return;
    untrack(() => {
      const m = advanceMission(mission, o);
      if (m !== mission) {
        mission = m;
        say(m.done >= S.mission.steps.length ? S.mission.all : STR.stepDone(m.done));
      }
    });
  });

  function applyPreset(id: PresetId) {
    const p = PRESETS[id];
    if (p.earthElDeg !== undefined) inp.earthElDeg = p.earthElDeg;
    if (p.ridgeHeightM !== undefined) inp.ridgeHeightM = p.ridgeHeightM;
    if (p.diameterM !== undefined) inp.diameterM = p.diameterM;
    if (p.rateBps !== undefined) rateIdx = RATES_BPS.indexOf(p.rateBps);
    say(`${STR.applied}: ${S.presets[id]}.`);
  }

  /* ---------------------------------------------- dati dal server ---------------------------------------------- */

  onMount(() => {
    const stage = host;
    const onSkyError = () => (skyError = true);
    stage?.addEventListener('lander-sky-error', onSkyError);
    void fetch('/api/raven/compensation')
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
      .then((j: unknown) => {
        table = parseCompTable(j);
        tableFailed = table === null;
      })
      .catch(() => (tableFailed = true));
    client = new SceneClient({
      onScene: (s) => {
        realScene = s;
        realErr = s.link.margin === null ? t('lander.rfOutsideModel') : '';
      },
      onError: (e: SceneError) => (realErr = e.kind === 'outside_model' ? t('lander.rfOutsideModel') : e.message),
      onBusy: (b) => (realBusy = b),
    });
    if (host) {
      handle = mountViewport(landerViewportFactory((m) => (vmode = m)), host, () => (viewError = STR.viewError));
      handle.update(vs);
    }
    return () => stage?.removeEventListener('lander-sky-error', onSkyError);
  });
  onDestroy(() => {
    client?.dispose();
    handle?.dispose();
    handle = null;
    clearTimeout(urlTimer);
    clearTimeout(sayTimer);
    clearPageContext();
  });

  let defaultsAsked = false;
  $effect(() => {
    if (!adv || defaultsAsked) return;
    defaultsAsked = true;
    void fetchDefaults(fetch).then((r) => {
      if (r.ok) defaults = r.data;
    });
  });
  let sitesAsked = false;
  $effect(() => {
    if (!real || sitesAsked) return;
    sitesAsked = true;
    void raven.sites().then((r) => {
      if (!r.ok) {
        sitesErr = STR.sitesError;
        return;
      }
      catalogSites = r.data.sites.filter((s) => s.dem_covered);
      if (!sites.some((s) => s.id === siteId)) siteId = (sites.find((s) => s.id === 'de-gerlache') ?? sites[0])?.id ?? '';
    });
  });
  $effect(() => {
    if (!real || !siteId || !sites.some((s) => s.id === siteId)) return;
    const p = {
      site: siteId,
      ...(customSel ? { customSite: customSel } : {}),
      ms: T0 + hours * 3_600_000,
      station: inp.station,
      gain: Math.round(Math.min(45, Math.max(-10, sceneGain)) * 100) / 100,
      rate: inp.rateBps,
      mast: Math.min(100, Math.max(0.1, inp.mastM)),
    };
    untrack(() => client?.request(p));
  });

  /* ------------------------------------------------ tag V/D/I ------------------------------------------------ */

  const REG: Record<string, string> = {
    freq: 'frequency_ghz',
    ridge: 'ridge_height_angle_deg',
    d1: 'ridge_distance_m',
    mast: 'antenna_height_m',
    perr: 'tracking_error_deg',
    ptx: 'tx_power_dbw',
    tsys: 'tsys_k',
    ebn0: 'ebn0_db',
    loss: 'misc_loss_db',
    eta: 'antenna_eta',
    dist: 'earth_distance_km_mean',
    eps: 'regolith_eps_real',
    epsi: 'regolith_eps_imag',
    sig: 'roughness_rms_m',
    rate: 'rate_bps',
    dia: 'tx_gain_dbi',
  };
  const LOCAL: Record<string, { status: string; source: string }> = {
    el: { status: 'I', source: 'scelta nello scenario didattico; con un sito reale dalle effemeridi (D)' },
    radius: { status: 'I', source: 'bozza §3.B: raggi 0–400 m, non misurati; correzione T(m,n) di ITU-R P.526-9, banda dalla tabella split-step' },
  };
  function tag(k: string): { status: string; source: string } {
    if (LOCAL[k]) return LOCAL[k]!;
    const row = defaults?.parameters.find((p) => p.key === REG[k]);
    return row ? { status: row.status, source: row.source } : { status: '', source: '' };
  }
  const st = $derived(defaults?.stations.find((s) => s.key === inp.station));
  const sigma = $derived(Number(defaults?.parameters.find((p) => p.key === 'compensator_sigma_db')?.value ?? 1.5));

  /* ------------------------------------------------ URL, onda, assistente ------------------------------------------------ */

  let urlTimer: ReturnType<typeof setTimeout> | undefined;
  $effect(() => {
    const snap = $state.snapshot(inp) as LinkInput;
    const r = real;
    const s = siteId;
    const a = adv;
    clearTimeout(urlTimer);
    urlTimer = setTimeout(() => {
      try {
        const next = writeSimQuery(location.search, sanitizeInput(snap).input, r, s || null, a);
        if (next !== location.search) history.replaceState(history.state, '', `${location.pathname}${next}${location.hash}`);
      } catch {
        /* ambiente senza History API */
      }
    }, 250);
  });
  $effect(() => {
    const i = modelInput;
    setWaveHandoff({ frequencyGhz: i.frequencyGhz, radiusM: i.ridgeRadiusM, distanceM: i.ridgeDistanceM });
  });
  $effect(() => {
    const time = msToT(T0 + hours * 3_600_000);
    store.set({
      station: inp.station,
      bitrate: inp.rateBps === 1e5 ? null : inp.rateBps,
      ...(real ? { mast: inp.mastM, gain: sceneGain } : {}),
      ...(real && siteId ? { site: siteId, ...(time ? { t: time } : {}) } : {}),
    });
  });
  $effect(() => {
    const o = !real || (realScene && !realErr) ? shown : null;
    untrack(() =>
      setPageContext({
        params: sanitizeParams({
          scenario: real ? 'sito reale' : 'didattico',
          sito: real ? siteId : undefined,
          elevazione_terra_deg: o?.input.earthElDeg,
          quota_crinale_m: o?.input.ridgeHeightM,
          diametro_antenna_m: inp.diameterM,
          bitrate_bps: inp.rateBps,
          margine_db: o?.marginDb,
          stato: o?.state ?? 'unknown',
          validita: o?.validity.level ?? 'unknown',
        }),
      }),
    );
  });

  let liveEl: HTMLElement | undefined = $state();
  let sayTimer: ReturnType<typeof setTimeout> | undefined;
  function say(msg: string) {
    clearTimeout(sayTimer);
    sayTimer = setTimeout(() => announce(msg, liveEl ?? null), 300);
  }
  let lastState = '';
  $effect(() => {
    if (real && (!realScene || realErr)) {
      clearTimeout(sayTimer);
      if (liveEl) liveEl.textContent = '';
      lastState = '';
      return;
    }
    const k = `${shown.state}|${shown.validity.level}`;
    const msg = said;
    if (k !== lastState) {
      lastState = k;
      untrack(() => say(msg));
    }
  });

  /* ------------------------------------------------ scena 3D ------------------------------------------------ */

  let host: HTMLElement | undefined = $state();
  let handle: ViewportHandle | null = null;
  let vmode = $state<ViewportMode | null>(null);
  let viewError = $state('');
  let skyError = $state(false);
  let cinematic = $state(false);
  let view = $state<Preset>('side');
  let gen = $state(0);
  const vs: LanderViewState = {
    scene: null,
    sceneGen: 0,
    terrain: null,
    terrainGen: 0,
    cam: presetCamera('side', null),
    vExag: 1,
    tubeScale: 20,
    errorDeg: 0,
    showOverlays: true,
    sun: FALLBACK_SUN,
    tier: quality.tier,
  };
  let lastPatch: unknown = null;
  let first = true;
  const sectionMode = $derived(vmode === 'canvas2d');
  $effect(() => {
    const s = real ? realScene : syntheticScene(out, STR.didactic);
    const v = vExag;
    const err = inp.pointingErrorDeg;
    untrack(() => {
      vs.scene = s;
      vs.errorDeg = err;
      const vChanged = v !== vs.vExag;
      vs.vExag = v;
      if (s && (s.terrain.patch !== lastPatch || vChanged)) {
        lastPatch = s.terrain.patch;
        vs.terrain = buildTerrain(s, v, FALLBACK_SUN);
        vs.terrainGen++;
      }
      if (s && first) {
        first = false;
        vs.cam = presetCamera(view, s, v);
      }
      vs.sceneGen++;
      gen = vs.sceneGen;
      handle?.update(vs);
    });
  });
  const STEP = 8 * (Math.PI / 180);
  function useView(p: Preset) {
    view = p;
    vs.cam = presetCamera(p, vs.scene, vs.vExag);
    clampCam(vs.cam);
    handle?.update(vs);
  }
  function toggleCinematic() {
    cinematic = !cinematic;
    vs.showOverlays = !cinematic;
    handle?.update(vs);
  }
  const rotate = (dy: number, dp: number) => (orbit(vs.cam, dy, dp), handle?.update(vs));
  const zoom = (f: number) => (zoomBy(vs.cam, f), handle?.update(vs));
  function onStageKey(e: KeyboardEvent) {
    const k = e.key;
    if (k === 'ArrowLeft') rotate(-STEP, 0);
    else if (k === 'ArrowRight') rotate(STEP, 0);
    else if (k === 'ArrowUp') rotate(0, STEP);
    else if (k === 'ArrowDown') rotate(0, -STEP);
    else if (k === '+' || k === '=') zoom(1.2);
    else if (k === '-' || k === '_') zoom(1 / 1.2);
    else if (k === '1') useView('lander');
    else if (k === '2') useView('side');
    else if (k === '3') useView('top');
    else if (k === '0' || k === 'Home') useView(view);
    else return;
    e.preventDefault();
    e.stopPropagation();
  }
  const pts = new Map<number, { x: number; y: number; mouse: boolean }>();
  function onDown(e: PointerEvent) {
    if (e.pointerType === 'mouse' && e.button !== 0) return;
    pts.set(e.pointerId, { x: e.clientX, y: e.clientY, mouse: e.pointerType === 'mouse' });
    (e.currentTarget as HTMLElement).setPointerCapture?.(e.pointerId);
  }
  function onMove(e: PointerEvent) {
    const p = pts.get(e.pointerId);
    if (!p) return;
    const dx = e.clientX - p.x;
    const dy = e.clientY - p.y;
    p.x = e.clientX;
    p.y = e.clientY;
    orbit(vs.cam, dx * 0.006, p.mouse ? -dy * 0.006 : 0);
    handle?.update(vs);
  }
  const onUp = (e: PointerEvent) => void pts.delete(e.pointerId);

  /* ------------------------------------------------ varie ------------------------------------------------ */

  const rateText = $derived(S.rate(RATES_BPS[rateIdx] ?? 1e5));
  const siteName = $derived(sites.find((s) => s.id === siteId)?.name ?? siteId);
  const timeText = $derived(new Date(T0 + hours * 3_600_000).toISOString().slice(0, 16).replace('T', ' ') + ' UTC');
  function exportAll(kind: 'json' | 'csv') {
    const extra = { mode: adv ? 'avanzato' : 'learning', scenario: real ? { site: siteId, t: new Date(T0 + hours * 3_600_000).toISOString(), engine_scene: realScene?.raw ?? null } : 'didattico', table_version: table?.version ?? null, honesty: S.honesty };
    if (kind === 'json') downloadText(`simula-${real ? siteId : 'didattico'}.json`, 'application/json', exportJson(shown, extra));
    else downloadText(`simula-${real ? siteId : 'didattico'}.csv`, 'text/csv', exportCsv(shown));
  }
  const f2 = (v: number) => fmt(v, 2);
  const flagText = (code: keyof typeof S.flag, level: string) => (level === 'na' ? S.flagNa : level === 'ok' ? S.flagOk : S.flag[code]);
</script>

{#if !embedded}<SubNav title={STR.title} learn={STR.learn} />{/if}

<div class="sim workspace" data-testid="simula" data-real={real ? '1' : '0'}>
  <div class="container container--wide">
    <div class="grid scene-layout">
      <section class="figure tone-dark" class:cinematic={cinematic && !sectionMode} aria-labelledby="sim-fig-h">
        <h2 id="sim-fig-h" class="visually-hidden">{sectionMode ? t('sim.ui.figureSection') : t('sim.ui.figureScene')}</h2>
        <div class="stage-frame">
        <!-- svelte-ignore a11y_no_noninteractive_tabindex, a11y_no_noninteractive_element_interactions -->
        <div
          class="stage"
          bind:this={host}
          role="group"
          tabindex="0"
          aria-roledescription={sectionMode ? 'sezione' : 'grafico 3D'}
          aria-label={sectionMode ? STR.stageAria2d : STR.stageAria}
          data-spatial-skip
          data-testid="sim-stage"
          data-state={shown.state}
          data-el={shown.input.earthElDeg.toFixed(2)}
          data-gen={gen}
          data-mode={vmode ?? ''}
          aria-busy={real && realBusy}
          onkeydown={onStageKey}
          onpointerdown={onDown}
          onpointermove={onMove}
          onpointerup={onUp}
          onpointercancel={onUp}
        ></div>
        <div class="hud">
          {#if !sectionMode}
            <div class="views" role="group" aria-label={STR.view}>
              {#each VIEWS as p (p.id)}<button type="button" aria-pressed={view === p.id} onclick={() => useView(p.id)}>{p.label}</button>{/each}
              <button type="button" aria-pressed={cinematic} onclick={toggleCinematic}>{t('lander.cinematic')}</button>
              <button type="button" aria-label={t('sim.ui.rotateLeft')} onclick={() => rotate(-STEP, 0)}>◀</button>
              <button type="button" aria-label={t('sim.ui.rotateRight')} onclick={() => rotate(STEP, 0)}>▶</button>
              <button type="button" aria-label={t('sim.ui.zoomIn')} onclick={() => zoom(1.25)}>+</button>
              <button type="button" aria-label={t('sim.ui.zoomOut')} onclick={() => zoom(1 / 1.25)}>−</button>
            </div>
          {/if}
        </div>
        </div>
        <p class="scen-label" data-testid="scenario-label">{real ? STR.realSite(siteName || '…') : STR.didactic}</p>
        <span class="vmode" role="status" data-testid="sim-mode" data-mode={vmode ?? ''}>{vmode ? (STR.modeLabel[vmode] ?? '') : ''}</span>
        {#if vExag > 1 && !sectionMode}<span class="vmode">{STR.exag(vExag)}</span>{/if}
        {#if viewError}<p role="alert">{viewError}</p>{/if}
        {#if vmode === 'webgl'}
          <div class="visual-notes">
            <p class="small muted" data-testid="sim-visual-credit">{t('lander.visualCredit')} {t(real && realScene?.sky ? 'lander.skyOriented' : 'lander.skyIllustrative')} {t('lander.terrainVisual')}</p>
            {#if cinematic}<p class="small muted">{t('lander.overlaysHidden')}</p>{/if}
            {#if skyError}<p class="small" role="status">{t('lander.skyUnavailable')}</p>{/if}
          </div>
        {/if}
      </section>

      <SceneSettings>
        <div class="side-content">
        <div class="gauge-box">
          {#if !real || (realScene && !realErr)}
            <Gauge margin={shown.marginDb} state={shown.state} validity={shown.validity.level} {reasons} sentence={said} />
          {:else}
            <p role="status" data-testid="sim-rf-unknown">{realErr || STR.loading}</p>
          {/if}
          <details class="gl">
            <summary>{STR.glossary}</summary>
            <p>{STR.tips.margin}</p>
            <p>{STR.tips.fresnel}</p>
          </details>
        </div>

        {#if !real}
          <div class="presets" role="group" aria-label={STR.presets}>
            <p class="ph">{STR.presets}</p>
            {#each Object.keys(PRESETS) as id (id)}
              <button type="button" onclick={() => applyPreset(id as PresetId)} data-testid="preset-{id}">{S.presets[id as PresetId]}</button>
            {/each}
          </div>
        {/if}

        <form class="controls" onsubmit={(e) => e.preventDefault()} aria-label={STR.controls}>
          {#if !real}
            <NumSlider id="sim-el" label={adv ? STR.elAdv : STR.el} bind:value={inp.earthElDeg} min={adv ? RANGES.earthElDeg[0] : 0} max={10} step={0.05} unit="°" tip={STR.tips.el} tag={adv ? tag('el').status : ''} source={adv ? tag('el').source : ''} testid="ctl-el" />
            <NumSlider id="sim-ridge" label={adv ? STR.ridgeAdv : STR.ridge} bind:value={inp.ridgeHeightM} min={0} max={150} step={0.5} unit="m" digits={1} tip={STR.tips.ridge} tag={adv ? tag('ridge').status : ''} source={adv ? tag('ridge').source : ''} testid="ctl-ridge" />
            <NumSlider id="sim-radius" label={adv ? STR.radiusAdv : STR.radius} bind:value={inp.ridgeRadiusM} min={0} max={adv ? 1000 : 400} step={5} unit="m" digits={0} tip={STR.tips.radius} tag={adv ? tag('radius').status : ''} source={adv ? tag('radius').source : ''} testid="ctl-radius" />
          {/if}
          <NumSlider id="sim-dia" label={adv ? STR.diaAdv : STR.dia} bind:value={inp.diameterM} min={0.02} max={adv ? 3 : 1} step={0.005} unit="m" digits={3} tip={STR.tips.dia} tag={adv ? tag('dia').status : ''} source={adv ? t('sim.ui.sourceGain', { gain: f2(shown.gainDbi), efficiency: fmt(inp.eta, 2), source: tag('dia').source }) : ''} testid="ctl-dia" />
          {#if real && scen.gain !== null && sceneGain === scen.gain}<p>{t('planner.inheritedGain', { gain: scen.gain })}</p>{/if}
          <NumSlider id="sim-rate" label={adv ? STR.rateAdv : STR.rate} bind:value={rateIdx} min={0} max={RATES_BPS.length - 1} step={1} text={rateText} tip={STR.tips.rate} tag={adv ? tag('rate').status : ''} source={adv ? tag('rate').source : ''} testid="ctl-rate" />

          {#if adv}
            <h3>{STR.params}</h3>
            {#if real}<p class="small muted">{STR.adv.realOnly}</p>{/if}
            {#if !real}
              <NumSlider id="sim-freq" label={STR.adv.freq} bind:value={inp.frequencyGhz} min={RANGES.frequencyGhz[0]} max={RANGES.frequencyGhz[1]} step={0.1} unit="GHz" digits={1} tag={tag('freq').status} source={tag('freq').source} testid="ctl-freq" />
              <NumSlider id="sim-d1" label={STR.adv.d1} bind:value={inp.ridgeDistanceM} min={RANGES.ridgeDistanceM[0]} max={RANGES.ridgeDistanceM[1]} step={50} unit="m" digits={0} tag={tag('d1').status} source={tag('d1').source} testid="ctl-d1" />
            {/if}
            <NumSlider id="sim-mast" label={STR.adv.mast} bind:value={inp.mastM} min={RANGES.mastM[0]} max={RANGES.mastM[1]} step={0.1} unit="m" digits={1} tag={tag('mast').status} source={tag('mast').source} testid="ctl-mast" />
            {#if !real}
              <NumSlider id="sim-perr" label={STR.adv.perr} bind:value={inp.pointingErrorDeg} min={0} max={30} step={0.1} unit="°" digits={1} tag={tag('perr').status} source="{tag('perr').source}; HPBW {f2(shown.hpbwScriptDeg)}° (70 λ/D)" testid="ctl-perr" />
              <NumSlider id="sim-ptx" label={STR.adv.ptx} bind:value={inp.txPowerDbw} min={RANGES.txPowerDbw[0]} max={RANGES.txPowerDbw[1]} step={0.5} unit="dBW" digits={1} tag={tag('ptx').status} source={tag('ptx').source} testid="ctl-ptx" />
              <NumSlider id="sim-tsys" label={STR.adv.tsys} bind:value={inp.tsysK} min={RANGES.tsysK[0]} max={RANGES.tsysK[1]} step={1} unit="K" digits={0} tag={tag('tsys').status} source={tag('tsys').source} testid="ctl-tsys" />
              <NumSlider id="sim-ebn0" label={STR.adv.ebn0} bind:value={inp.ebn0Db} min={RANGES.ebn0Db[0]} max={RANGES.ebn0Db[1]} step={0.1} unit="dB" digits={1} tag={tag('ebn0').status} source={tag('ebn0').source} testid="ctl-ebn0" />
              <NumSlider id="sim-loss" label={STR.adv.loss} bind:value={inp.miscLossDb} min={RANGES.miscLossDb[0]} max={RANGES.miscLossDb[1]} step={0.1} unit="dB" digits={1} tag={tag('loss').status} source={tag('loss').source} testid="ctl-loss" />
              <NumSlider id="sim-eta" label={STR.adv.eta} bind:value={inp.eta} min={RANGES.eta[0]} max={RANGES.eta[1]} step={0.01} digits={2} tag={tag('eta').status} source={tag('eta').source} testid="ctl-eta" />
              <NumSlider id="sim-dist" label={STR.adv.dist} bind:value={inp.earthDistanceKm} min={RANGES.earthDistanceKm[0]} max={RANGES.earthDistanceKm[1]} step={100} unit="km" digits={0} tag={tag('dist').status} source={tag('dist').source} testid="ctl-dist" />
            {/if}
            <p class="field">
              <label for="sim-station">{STR.adv.station} {#if st}<Badge status={st.gain_tag} />{/if}</label>
              <select id="sim-station" bind:value={inp.station} data-testid="ctl-station">
                <option value="dsn34">DSN 34 m (68 dBi)</option>
                <option value="dsn18">{t('sim.ui.station18')}</option>
              </select>
              {#if st}<span class="src">{st.gain_source}</span>{/if}
            </p>
            {#if !real}
              <p class="check"><label><input type="checkbox" bind:checked={inp.applyCorrection} data-testid="ctl-corr" /> {STR.adv.corr}</label></p>
              <p class="check"><label><input type="checkbox" bind:checked={inp.multipath.enabled} data-testid="ctl-mp" /> {STR.adv.mp} <Badge status="D" /></label></p>
              {#if inp.multipath.enabled}
                <NumSlider id="sim-eps" label={STR.adv.eps} bind:value={inp.multipath.epsReal} min={RANGES.epsReal[0]} max={RANGES.epsReal[1]} step={0.1} digits={1} tag={tag('eps').status} source={tag('eps').source} testid="ctl-eps" />
                <NumSlider id="sim-epsi" label={STR.adv.epsi} bind:value={inp.multipath.epsImag} min={RANGES.epsImag[0]} max={RANGES.epsImag[1]} step={0.01} digits={2} tag={tag('epsi').status} source={tag('epsi').source} testid="ctl-epsi" />
                <NumSlider id="sim-sig" label={STR.adv.sig} bind:value={inp.multipath.roughnessM} min={RANGES.roughnessM[0]} max={RANGES.roughnessM[1]} step={0.01} unit="m" digits={2} tag={tag('sig').status} source={tag('sig').source} testid="ctl-sig" />
              {/if}
            {/if}
            <p class="field">
              <label for="sim-vex">{STR.adv.vex}</label>
              <select id="sim-vex" bind:value={vExag}><option value={1}>×1</option><option value={3}>×3</option><option value={5}>×5</option></select>
            </p>
          {/if}
        </form>
        {#if !hideReal}<div class="realbox">
          {#if !hideRealToggle}<button type="button" class="toggle" aria-pressed={real} onclick={() => (real = !real)} data-testid="use-real">{STR.useReal}</button>{/if}
          <p class="small muted">{STR.useRealHint}</p>
          {#if real}
            {#if sitesErr}<p role="alert">{sitesErr}</p>{/if}
            <p class="field">
              <label for="sim-site">{STR.site}</label>
              <select id="sim-site" bind:value={siteId} disabled={sites.length === 0} data-testid="sim-site">
                {#each catalogSites as s (s.id)}<option value={s.id}>{s.name}</option>{/each}
                {#if customList.length}<optgroup label={t('custom.group')}>{#each customList as c (c.id)}<option value={c.id}>{c.name}</option>{/each}</optgroup>{/if}
              </select>
            </p>
            <CustomSiteControl onadd={(id) => { siteId = id; }} />
            <NumSlider id="sim-hours" label={STR.time} bind:value={hours} min={0} max={720} step={1} text={timeText} testid="ctl-hours" />
            <p class="small" role="status" data-testid="real-status">{realErr ? '' : realBusy || !realScene ? STR.loading : realScene.link.margin === null ? t('lander.rfOutsideModel') : t('sim.ui.realMargin', { time: realScene.tUtc.replace('T', ' ').replace('Z', ' UTC'), margin: f2(realScene.link.margin) })}</p>
            {#if realErr}<p role="alert" data-testid="real-error">{realErr}</p>{/if}
          {/if}
        </div>{/if}

        </div>
      </SceneSettings>
    </div>

    <p class="honesty" data-testid="honesty">{S.honesty}</p>
    {#if tableFailed}<p class="small" role="status" data-testid="table-missing">{STR.tableMissing}</p>{/if}

    {#if !real || (realScene && !realErr)}
    <div class="lower">
      <MarginChart data={chart} note={real ? STR.realChartNote : ''} />
      {#if !real}
        <ValidityMap heat={heat.h} el={inp.earthElDeg} ridge={inp.ridgeHeightM} ms={heat.ms} onpick={(e, r) => ((inp.earthElDeg = e), (inp.ridgeHeightM = r))} />
      {:else}
        <p class="small muted">{STR.realMapNote}</p>
      {/if}
    </div>
    {/if}

    {#if !adv && !real}
      <section class="mission" aria-labelledby="mission-h" data-testid="mission" data-done={mission.done}>
        <h2 id="mission-h">{S.mission.title}</h2>
        <ol>
          {#each S.mission.steps as step, i (step.id)}
            <li data-step={step.id} data-done={i < mission.done ? '1' : '0'} aria-current={i === mission.done ? 'step' : undefined}>
              <span class="mark" aria-hidden="true">{i < mission.done ? '✓' : i === mission.done ? '→' : '○'}</span>
              <span><strong>{step.task}</strong> <span class="visually-hidden">({i < mission.done ? S.mission.done : S.mission.todo})</span><br /><span class="small">{STR.expect}: {step.expect}</span></span>
            </li>
          {/each}
        </ol>
        {#if mission.done >= S.mission.steps.length}<p role="status">{S.mission.all}</p>{/if}
        <button type="button" onclick={() => (mission = newMission(out.input))}>{STR.restart}</button>
      </section>
    {/if}

    {#if adv && (!real || (realScene && !realErr))}
      <div class="advanced">
        <section aria-labelledby="flags-h">
          <h2 id="flags-h">{STR.flags}</h2>
          <ul class="flags" data-testid="flags">
            {#each shown.validity.flags as fl (fl.code)}
              <li data-level={fl.level}><code>{fl.code}</code>: {flagText(fl.code, fl.level)}</li>
            {/each}
          </ul>
        </section>
        <section aria-labelledby="var-h">
          <h2 id="var-h">{STR.variants}</h2>
          <div class="tw">
            <table data-testid="variants">
              <thead><tr><th scope="col">{t('sim.ui.table.variant')}</th><th scope="col">{t('sim.ui.table.margin')}</th><th scope="col">{t('sim.ui.table.state')}</th></tr></thead>
              <tbody>
                {#each vars as v (v.id)}
                  <tr><th scope="row">{STR.variantName[v.id]}</th><td dir="ltr">{f2(v.marginDb)}{v.uncertaintyDb !== undefined && v.uncertaintyDb > 0 ? ` ± ${f2(v.uncertaintyDb)}` : ''}</td><td>{S.state[v.state].symbol} {S.state[v.state].word}</td></tr>
                {/each}
              </tbody>
            </table>
          </div>
        </section>
        <section aria-labelledby="unc-h">
          <h2 id="unc-h">{STR.uncertainty}</h2>
          <ul data-testid="uncertainty">
            <li>{STR.unc.corr(f2(shown.correctionUncertaintyDb))}</li>
            <li>{STR.unc.dist(f2(distRange[0]!), f2(distRange[1]!))}</li>
            <li>{STR.unc.sigma(fmt(sigma, 1))}</li>
          </ul>
        </section>
        <section aria-labelledby="num-h">
          <h2 id="num-h">{STR.numbers}</h2>
          <div class="tw">
            <table class="nums" data-testid="numbers">
              <thead><tr><th scope="col">{t('sim.ui.table.quantity')}</th><th scope="col">{t('sim.ui.table.value')}</th><th scope="col">{t('sim.ui.table.tag')}</th></tr></thead>
              <tbody>
                <tr><th scope="row">λ</th><td dir="ltr">{fmt(shown.wavelengthM * 100, 3)} cm</td><td><Badge status="D" /></td></tr>
                <tr><th scope="row">{t('sim.ui.quantity.crestElevation')}</th><td dir="ltr">{f2(shown.tipElevationDeg)}° ({f2(shown.angleAboveLosDeg)}° {t('sim.ui.quantity.aboveLineOfSight')})</td><td><Badge status="D" /></td></tr>
                <tr><th scope="row">{t('sim.ui.quantity.heightAboveLineOfSight')}</th><td dir="ltr">{f2(shown.hAboveLosM)} m</td><td><Badge status="D" /></td></tr>
                <tr><th scope="row">{t('sim.ui.quantity.ridgeDistanceLineOfSight')}</th><td dir="ltr">{fmt(shown.d1LosM, 0)} m</td><td><Badge status="D" /></td></tr>
                <tr><th scope="row">{t('sim.ui.quantity.fresnelRadius')}</th><td dir="ltr">{f2(shown.fresnelR1M)} m</td><td><Badge status="V" /></td></tr>
                <tr><th scope="row">ν</th><td dir="ltr" data-testid="num-nu">{fmt(shown.nu, 3)}</td><td><Badge status="V" /></td></tr>
                <tr><th scope="row">{t('sim.ui.quantity.knifeEdge')}</th><td dir="ltr">{f2(shown.knifeEdgeDb)} dB</td><td><Badge status="V" /></td></tr>
                <tr><th scope="row">{t('sim.ui.quantity.ituApproximation')}</th><td dir="ltr">{f2(shown.ituDb)} dB</td><td><Badge status="I" /></td></tr>
                <tr><th scope="row">{t('sim.ui.quantity.crestCorrection')}</th><td dir="ltr">{shown.correctionStatus === 'off' ? t('sim.ui.off') : `${f2(shown.correctionDb)} ± ${f2(shown.correctionUncertaintyDb)} dB (ITU)${shown.correctionStatus === 'itu' ? `; split-step ${f2(shown.correctionSplitStepDb)} dB${shown.correctionClamped ? ` (${t('sim.ui.clamped')})` : ''}` : `; ${t('sim.ui.comparisonUnavailable')}`}`}</td><td><Badge status="I" /></td></tr>
                <tr><th scope="row">{t('sim.ui.quantity.freeSpace')}</th><td dir="ltr">{f2(shown.fsplDb)} dB</td><td><Badge status="V" /></td></tr>
                <tr><th scope="row">{t('sim.ui.quantity.roverGain')}</th><td dir="ltr">{f2(shown.gainDbi)} dBi ({t('sim.ui.crude')}: 30000/HPBW²: {f2(shown.gainCrudeDbi)})</td><td><Badge status="V" /></td></tr>
                <tr><th scope="row">HPBW</th><td dir="ltr">{f2(shown.hpbwScriptDeg)}° (70 λ/D) / {f2(shown.hpbwUniformDeg)}° (uniforme)</td><td><Badge status="I" /></td></tr>
                <tr><th scope="row">{t('sim.ui.quantity.pointingLoss')}</th><td dir="ltr">{fmt(shown.pointingLossDb, 3)} dB ({t('sim.ui.script')} {fmt(shown.pointingScriptDb, 3)}, Airy {fmt(shown.pointingAiryDb, 3)})</td><td><Badge status="D" /></td></tr>
                <tr><th scope="row">Multipath</th><td dir="ltr">{shown.multipathApplicable ? `${f2(shown.multipathGainDb)} dB` : t('sim.ui.notApplied')}</td><td><Badge status="D" /></td></tr>
                <tr><th scope="row">{t('sim.ui.adv.station')}</th><td dir="ltr">{fmt(shown.stationGainDbi, 1)} dBi</td><td><Badge status="I" /></td></tr>
                <tr><th scope="row">N0</th><td dir="ltr">{f2(shown.n0Dbw)} dBW/Hz</td><td><Badge status="D" /></td></tr>
                <tr><th scope="row">C/N0</th><td dir="ltr">{f2(shown.cn0DbHz)} dB-Hz</td><td><Badge status="D" /></td></tr>
                <tr><th scope="row">{t('sim.ui.quantity.margin')}</th><td dir="ltr" data-testid="num-margin">{f2(shown.marginDb)} dB</td><td><Badge status="D" /></td></tr>
                <tr><th scope="row">{t('sim.ui.quantity.maxSustainableRate')}</th><td dir="ltr">{shown.maxRateBps > 0 ? S.rate(shown.maxRateBps) : t('sim.ui.none')}</td><td><Badge status="D" /></td></tr>
              </tbody>
            </table>
          </div>
        </section>
        <section aria-labelledby="exp-h">
          <h2 id="exp-h">{STR.export}</h2>
          <div class="row">
            <button type="button" onclick={() => exportAll('json')} data-testid="export-json">{STR.json}</button>
            <button type="button" onclick={() => exportAll('csv')} data-testid="export-csv">{STR.csv}</button>
          </div>
        </section>
      </div>
    {/if}
    <ModelStamp />
    {#if adv}<p class="muted small" data-testid="mirror-note">{t('simula.mirrorNote')}</p>{/if}
    <div class="visually-hidden" aria-live="polite" bind:this={liveEl}></div>
  </div>
</div>

<style>
  .sim {
    padding-block: var(--space-4) var(--space-6);
  }
  .sim > .container {
    max-width: none;
  }
  .visual-notes {
    padding: var(--space-2) var(--space-3);
  }
  .figure {
    position: relative;
    border-radius: var(--radius-md);
    overflow: hidden;
    background: #05070b;
    color: var(--c-text);
  }
  .stage-frame {
    position: relative;
  }
  .stage {
    block-size: var(--scene-stage-height);
    inline-size: 100%;
    touch-action: pan-y;
    cursor: grab;
    outline-offset: -3px;
  }
  .figure.cinematic .stage {
    block-size: max(320px, calc(100svh - var(--nav-h) - var(--space-4)));
  }
  .scen-label {
    margin: var(--space-2) var(--space-3) 0;
    padding: var(--space-1) var(--space-2);
    border-radius: var(--radius-xs);
    background: rgb(0 0 0 / 0.6);
    font-weight: 600;
    pointer-events: none;
  }
  .hud {
    position: absolute;
    inset-inline: var(--space-2);
    inset-block-end: var(--space-2);
    display: flex;
    overflow-x: auto;
    gap: var(--space-2);
    align-items: center;
    justify-content: space-between;
    padding: var(--space-1);
  }
  .views {
    display: flex;
    flex-wrap: nowrap;
    gap: var(--space-1);
    pointer-events: auto;
  }
  .views button,
  .presets button,
  .toggle,
  .mission button,
  .row button {
    min-block-size: 44px;
    min-inline-size: 44px;
    padding-inline: var(--space-3);
    border-radius: var(--radius-pill);
    border: 1px solid var(--c-hairline);
    background: var(--c-bg-alt);
    color: var(--c-text);
    font: inherit;
    cursor: pointer;
  }
  .views button {
    white-space: nowrap;
    background: rgb(0 0 0 / 0.72);
    color: #fff;
    border-color: rgb(255 255 255 / 0.45);
  }
  .views button[aria-pressed='true'],
  .toggle[aria-pressed='true'] {
    background: var(--c-action);
    color: var(--c-on-action);
    border-color: var(--c-action);
  }
  .vmode {
    font-size: var(--fs-micro);
    color: #fff;
    background: rgb(0 0 0 / 0.6);
    padding: var(--space-1) var(--space-2);
    border-radius: var(--radius-xs);
  }
  .side-content {
    display: grid;
    gap: var(--space-4);
  }
  .gauge-box :global(svg) {
    max-inline-size: 10rem;
  }
  .gauge-box :global(.big) {
    font-size: 1.8rem;
  }
  .gauge-box :global(.sentence) {
    font-size: var(--fs-small);
  }
  .gauge-box,
  .realbox,
  .controls,
  .presets {
    display: grid;
    gap: var(--space-3);
  }
  .presets {
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: var(--space-2);
  }
  .presets .ph {
    grid-column: 1 / -1;
    margin: 0;
    font-weight: 600;
  }
  .gl summary {
    min-block-size: 44px;
    display: flex;
    align-items: center;
    cursor: pointer;
  }
  .field {
    display: grid;
    gap: var(--space-1);
    margin: 0;
  }
  .field select {
    min-block-size: 44px;
  }
  .check {
    margin: 0;
  }
  .check label {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    min-block-size: 44px;
  }
  .check input {
    inline-size: 22px;
    block-size: 22px;
  }
  .src {
    color: var(--c-muted);
    font-size: var(--fs-micro);
  }
  h3 {
    margin: var(--space-3) 0 0;
  }
  .honesty {
    margin-block: var(--space-4) var(--space-2);
    padding: var(--space-2) var(--space-3);
    border-inline-start: 4px solid var(--c-muted);
    background: var(--c-bg-alt);
    font-size: var(--fs-small);
  }
  .lower > :global(*),
  .grid > *,
  .advanced > * {
    min-inline-size: 0;
  }
  .lower {
    display: grid;
    gap: var(--space-5);
    margin-block-start: var(--space-4);
  }
  @media (min-width: 1024px) {
    .lower {
      grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
    }
  }
  .mission,
  .advanced {
    margin-block-start: var(--space-5);
  }
  .mission ol {
    list-style: none;
    padding: 0;
    display: grid;
    gap: var(--space-2);
  }
  .mission li {
    display: flex;
    gap: var(--space-2);
    align-items: flex-start;
  }
  .mission li[data-done='1'] .mark {
    color: var(--c-success);
  }
  .mission li[aria-current='step'] {
    font-weight: 500;
  }
  .mark {
    font-weight: 700;
    min-inline-size: 1.5rem;
  }
  .advanced {
    display: grid;
    gap: var(--space-5);
  }
  .flags {
    padding-inline-start: var(--space-4);
  }
  .flags li[data-level='uncertain']::marker {
    content: '? ';
  }
  .flags li[data-level='outside']::marker {
    content: '⊘ ';
  }
  .tw {
    overflow-x: auto;
  }
  table {
    border-collapse: collapse;
    inline-size: 100%;
    font-size: var(--fs-small);
  }
  th,
  td {
    text-align: start;
    padding: var(--space-1) var(--space-2);
    border-block-end: 1px solid var(--c-hairline);
    vertical-align: top;
  }
  td[dir='ltr'] {
    font-variant-numeric: tabular-nums;
  }
  .row {
    display: flex;
    gap: var(--space-2);
    flex-wrap: wrap;
  }
  .muted {
    color: var(--c-muted);
  }
</style>
