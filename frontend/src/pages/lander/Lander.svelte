<!-- SPDX-License-Identifier: Apache-2.0 -->
<!--
  Scena lander: terreno LOLA con luce radente, rover con antenna X-band, cono del fascio con l'HPBW vero, prima zona di
  Fresnel come tubo colorato dal margine di link reale (API /api/raven/scene), Terra al suo diametro angolare e alla sua
  elevazione. WebGL con ripiego Canvas 2D (sezione laterale, mostrata anche come scheda in modalita' WebGL).
-->
<script lang="ts">
  import ModelStamp from '../../shell/ModelStamp.svelte';
  import { onMount, onDestroy, tick, untrack, type Snippet } from 'svelte';
  import SubNav from '../../components/ui/SubNav.svelte';
  import SceneSettings from '../../components/ui/SceneSettings.svelte';
  import Callout from '../../components/ui/Callout.svelte';
  import Badge from '../grazinglink/Badge.svelte';
  import { downloadText, type Site } from '../grazinglink/grazing';
  import { raven } from '../../shell/ravenApi';
  import SkyTime from '../viewer/SkyTime.svelte';
  import type { Light } from '../viewer/skyLight';
  import { BITRATES, msToT, scenarioStore, tToMs } from '../../shell/scenario';
  import { chooseDefaultInstant, type DefaultInstant } from './grazingLight';
  import { setPageContext, clearPageContext } from '../../shell/pageContext.svelte';
  import { announce } from '../../shell/a11y';
  import { sanitizeParams } from '../chat/assistant';
  import { mountViewport, type ViewportHandle } from '../../viewports/port';
  import { detectQuality } from '../../viewports/quality';
  import type { ViewportMode } from '../../viewports/select';
  import { landerViewportFactory, sectionViewportFactory } from './landerViewport';
  import {
    DEFAULT_GAIN,
    DEFAULT_MAST,
    FALLBACK_SUN,
    MAST_RANGE,
    pointing,
    ridgeObstruction,
    sceneJson,
    SceneClient,
    STATE_INFO,
    sunLocal,
    textAlternative,
    type LanderScene,
    SceneError,
    type SceneParams,
    type SunLocal,
  } from './model';
  import { buildTerrain, clampCam, orbit, PRESETS, presetCamera, zoomBy, type LanderViewState, type Preset } from './view';
  import { modeNow } from '../../shell/modeState.svelte';
  import { formatNumber, t } from '../../i18n/i18n.svelte';
  import { customSites as customStore, isCustomId, type CustomSiteDef } from '../../shell/customSites';
  import CustomSiteControl from '../../shell/CustomSiteControl.svelte';

  let {
    embedded = false,
    compact = false,
    plannerSite = null,
    plannerCustomSite,
    plannerMs = null,
    plannerRadio,
    plannerSettings,
    plannerSceneState,
  }: {
    embedded?: boolean;
    compact?: boolean;
    plannerSite?: string | null;
    plannerCustomSite?: CustomSiteDef;
    plannerMs?: number | null;
    plannerRadio?: { station: 'dsn34' | 'dsn18'; gain: number; rate: number; mast: number };
    plannerSettings?: Snippet;
    plannerSceneState?: (params: SceneParams | null, ready: boolean) => void;
  } = $props();
  const controlled = $derived(plannerSite !== null && plannerMs !== null);

  const TABS = [
    { id: 'numbers', label: t('lander.tab.numbers') },
    { id: 'section', label: t('lander.tab.section') },
    { id: 'text', label: t('lander.tab.text') },
    { id: 'limits', label: t('lander.tab.limits') },
  ] as const;
  type TabId = (typeof TABS)[number]['id'];
  const STEP = 8 * (Math.PI / 180);
  const DRAG = 0.006;
  const quality = detectQuality();
  const store = scenarioStore();
  const init = store.get();

  let sites = $state<Site[]>([]);
  let siteId = $state<string>(untrack(() => plannerSite) ?? init.site ?? '');
  let customList = $state<readonly CustomSiteDef[]>(customStore.get());
  onMount(() => customStore.subscribe((l) => { customList = l; }));
  // il sito personalizzato selezionato: dal Planner (incorporato) o dall'elenco condiviso (pagina autonoma)
  const customSel = $derived(plannerCustomSite?.id === siteId ? plannerCustomSite : isCustomId(siteId) ? customList.find((c) => c.id === siteId) : undefined);
  let station = $state<'dsn34' | 'dsn18'>(init.station);
  let gain = $state<number>(init.gain ?? DEFAULT_GAIN);
  let rate = $state<number>(init.bitrate ?? 1e5);
  let mast = $state<number>(init.mast ?? DEFAULT_MAST);
  let errorDeg = $state(0);
  let vExag = $state(1);
  let tubeScale = $state(20);
  let simMs = $state<number | null>(null);
  // istante iniziale: quello dello scenario, oppure (senza t esplicito) il primo con Sole radente nel mese successivo
  let startMs = $state<number | null>(untrack(() => plannerMs) ?? tToMs(init.t));
  let pick = $state.raw<DefaultInstant | null>(null);
  let light = $state.raw<Light | null>(null);
  let hasRealLight = $state(false);
  let data = $state.raw<LanderScene | null>(null);
  let readySceneParams = $state.raw<SceneParams | null>(null);
  let loading = $state(true);
  let busy = $state(false);
  let problem = $state<SceneError | null>(null);
  let listError = $state('');
  let tab = $state<TabId>('numbers');
  let mode = $state<ViewportMode | null>(null);
  let viewError = $state('');
  let skyError = $state(false);
  let cinematic = $state(false);
  let drawn = $state(false);
  let preset = $state<Preset>('lander');
  let host: HTMLElement | undefined = $state();
  let secHost: HTMLElement | undefined = $state();
  let liveEl: HTMLElement | undefined = $state();
  let handle: ViewportHandle | null = null;
  let secHandle: ViewportHandle | null = null;
  let client = $state.raw<SceneClient | null>(null);
  let announceTimer: ReturnType<typeof setTimeout> | undefined;
  let customKey = '';

  const vs: LanderViewState = {
    scene: null,
    sceneGen: 0,
    terrain: null,
    terrainGen: 0,
    cam: presetCamera('lander', null),
    vExag: 1,
    tubeScale: 20,
    errorDeg: 0,
    showOverlays: true,
    sun: FALLBACK_SUN,
    tier: quality.tier,
  };

  const covered = $derived(sites.filter((s) => s.dem_covered));
  // Both APIs use whole UTC seconds; the playback clock also contains fractional milliseconds.
  const sunReal = $derived(!!data && light?.body === 'moon' && Math.floor(light.ms / 1000) * 1000 === tToMs(data.tUtc));
  const sun = $derived.by<SunLocal>(() => {
    // Keep the last illumination until the scene and ephemerides refer to the same instant.
    if (!sunReal || !data || !light) return vs.sun;
    return sunLocal(data.site.lat, data.site.lon, light.dir, data.earth.azDeg);
  });
  const pt = $derived(data ? pointing(data, errorDeg) : null);
  const info = $derived(data ? STATE_INFO[data.link.state] : null);
  const ptInfo = $derived(pt ? STATE_INFO[pt.state] : null);
  const sectionMode = $derived(mode === 'canvas2d');
  const hpbw = $derived(data?.antenna.hpbwDeg ?? 10);
  const text = $derived(data && pt ? textAlternative(data, pt, sun, sunReal) : '');
  const siteName = $derived(customSel ? customSel.name : sites.find((s) => s.id === siteId)?.name ?? siteId);
  const previousScene = $derived(controlled && !!data && (!readySceneParams || !currentParams(readySceneParams)));
  const renderedSiteName = $derived(readySceneParams?.customSite?.name ?? sites.find((s) => s.id === data?.site.id)?.name ?? siteName);

  /* ------------------------------------------ dati ------------------------------------------ */

  function params(): SceneParams | null {
    if (!siteId || simMs === null) return null;
    return { site: siteId, ms: simMs, station, gain, rate, mast, ...(customSel ? { customSite: customSel } : {}) };
  }

  function currentParams(p: SceneParams): boolean {
    const current = params();
    return !!current && current.site === p.site && current.ms === p.ms &&
      current.station === p.station && current.gain === p.gain && current.rate === p.rate && current.mast === p.mast &&
      JSON.stringify(current.customSite ?? null) === JSON.stringify(p.customSite ?? null);
  }

  $effect(() => {
    const p = params();
    if (!p || !client || (!p.customSite && !controlled && !covered.some((s) => s.id === p.site))) return;
    untrack(() => client?.request(p));
  });

  function onScene(s: LanderScene) {
    const first = data === null;
    data = s;
    problem = s.link.margin === null ? new SceneError('outside_model', '') : null;
    loading = false;
    vs.scene = s;
    vs.sceneGen++;
    if (first) {
      vs.cam = presetCamera(preset, s, vs.vExag);
    }
    refreshTerrain();
    push();
    markDrawn();
  }
  function onError(e: SceneError) {
    problem = e;
    loading = false;
  }

  function refreshTerrain() {
    vs.terrain = vs.scene ? buildTerrain(vs.scene, vs.vExag, sun) : null;
    vs.terrainGen++;
  }
  function push() {
    handle?.update(vs);
    secHandle?.update(vs);
  }
  function toggleCinematic() {
    cinematic = !cinematic;
    vs.showOverlays = !cinematic;
    push();
  }
  function markDrawn() {
    void tick().then(() => requestAnimationFrame(() => requestAnimationFrame(() => (drawn = !!data))));
  }

  // la luce (reale o di ripiego) cambia solo l'ombreggiatura
  $effect(() => {
    const s = sun;
    const real = sunReal;
    untrack(() => {
      vs.sun = s;
      if (real) hasRealLight = true;
      if (vs.scene) {
        refreshTerrain();
        push();
      }
    });
  });
  $effect(() => {
    const v = vExag;
    const t = tubeScale;
    const e = errorDeg;
    untrack(() => {
      const vChanged = v !== vs.vExag;
      vs.vExag = v;
      vs.tubeScale = t;
      vs.errorDeg = e;
      if (vs.scene) {
        if (vChanged) refreshTerrain();
        vs.sceneGen++;
      }
      push();
    });
  });
  $effect(() => {
    // sezione laterale: monta il secondo viewport quando la scheda e' visibile
    const el = secHost;
    if (!el || sectionMode) return;
    const h = mountViewport(sectionViewportFactory, el, () => {});
    untrack(() => {
      secHandle = h;
      h.update(vs);
    });
    return () => {
      h.dispose();
      if (secHandle === h) secHandle = null;
    };
  });

  function selectSite(id: string) {
    siteId = id;
    pick = null; // la nota riguarda l'istante scelto per il sito di partenza
    store.set({ site: id });
  }
  function onTime(ms: number, explicit: boolean) {
    if (pick && ms !== pick.ms) pick = null; // l'utente ha cambiato l'istante: la nota non vale piu'
    if (controlled && simMs !== ms) {
      problem = null;
      loading = true;
    }
    simMs = ms;
    if (explicit) store.set({ t: msToT(ms) });
  }
  function onLight(l: Light | null) {
    light = l;
  }
  $effect(() => {
    const p = readySceneParams;
    if (controlled && p && light?.ms === p.ms && currentParams(p)) plannerSceneState?.(p, true);
  });
  function onPlannerLightError(ms: number) {
    const p = params();
    if (controlled && p && p.ms === ms) plannerSceneState?.(p, false);
  }
  $effect(() => {
    if (!controlled) store.set({ station, gain: gain === DEFAULT_GAIN ? null : gain, bitrate: rate === 1e5 ? null : rate, mast });
  });
  $effect(() => {
    const radio = plannerRadio;
    if (!controlled || !radio) return;
    if (station !== radio.station || gain !== radio.gain || rate !== radio.rate || mast !== radio.mast) {
      station = radio.station;
      gain = radio.gain;
      rate = radio.rate;
      mast = radio.mast;
      problem = null;
      loading = true;
    }
  });
  $effect(() => {
    if (plannerSite !== null && siteId !== plannerSite) {
      siteId = plannerSite;
      problem = null;
      loading = true;
    }
  });
  $effect(() => {
    const key = JSON.stringify(customSel ?? null);
    if (key !== customKey) {
      customKey = key;
      problem = null;
      loading = true;
    }
  });

  onMount(() => {
    const stage = host;
    const onSkyError = () => (skyError = true);
    stage?.addEventListener('lander-sky-error', onSkyError);
    client = new SceneClient({
      onScene: (s, p) => {
        if (!controlled || currentParams(p)) {
          onScene(s);
          if (controlled) readySceneParams = p;
        }
      },
      onError: (e, p) => {
        if (!controlled || currentParams(p)) {
          onError(e);
          if (controlled) plannerSceneState?.(p, false);
        }
      },
      onBusy: (b) => (busy = b),
    });
    void (async () => {
      const r = await raven.sites();
      if (!r.ok) {
        listError = t('lander.listUnavailable');
        loading = false;
        if (controlled) plannerSceneState?.(null, false);
        return;
      }
      sites = r.data.sites;
      const cov = r.data.sites.filter((s) => s.dem_covered);
      if (!customSel && !cov.some((s) => s.id === siteId)) siteId = (cov.find((s) => s.id === 'de-gerlache') ?? cov[0])?.id ?? '';
      if (!siteId) loading = false;
      if (startMs === null) {
        const now = Math.floor(Date.now() / 1000) * 1000;
        const site = r.data.sites.find((x) => x.id === siteId);
        const found = site ? await chooseDefaultInstant(now, site.lat_deg, site.lon_deg_east) : null;
        pick = found;
        startMs = found?.ms ?? now;
        if (found?.kind === 'grazing') store.set({ t: msToT(found.ms) }); // gli altri link portano lo stesso istante
      }
    })();
    if (host) {
      handle = mountViewport(landerViewportFactory((m) => (mode = m)), host, () => (viewError = t('lander.viewUnavailable')));
      handle.update(vs);
    }
    return () => {
      stage?.removeEventListener('lander-sky-error', onSkyError);
      client?.dispose();
    };
  });
  onDestroy(() => {
    client?.dispose();
    clearTimeout(announceTimer);
    handle?.dispose();
    handle = null;
    secHandle?.dispose();
    secHandle = null;
    clearPageContext();
  });

  $effect(() => {
    const d = data;
    untrack(() => {
      setPageContext({
        params: sanitizeParams({
          sito: siteId,
          istante: d?.tUtc,
          stazione: station,
          bitrate_bps: rate,
          altezza_palo_m: mast,
          errore_puntamento_deg: errorDeg,
          margine_db: d?.link.margin,
          stato: d?.link.state,
          nu: d?.ridge.nu,
          scheda: tab,
        }),
      });
    });
  });

  /* ------------------------------------- camera: puntatore e tastiera ------------------------------------- */

  function say(msg: string) {
    clearTimeout(announceTimer);
    announceTimer = setTimeout(() => announce(msg, liveEl ?? null), 450);
  }
  function viewChanged() {
    push();
    say(`Vista: rotazione ${Math.round((vs.cam.yaw * 180) / Math.PI)}°, inclinazione ${Math.round((vs.cam.pitch * 180) / Math.PI)}°, distanza ${Math.round(vs.cam.dist)} metri.`);
  }
  const rotate = (dy: number, dp: number) => (orbit(vs.cam, dy, dp), viewChanged());
  const zoom = (f: number) => (zoomBy(vs.cam, f), viewChanged());
  function usePreset(p: Preset) {
    preset = p;
    vs.cam = presetCamera(p, vs.scene, vs.vExag);
    clampCam(vs.cam);
    viewChanged();
  }

  function onStageKey(e: KeyboardEvent) {
    const k = e.key;
    const fine = e.shiftKey ? 0.4 : 1;
    if (k === 'ArrowLeft') rotate(-STEP * fine, 0);
    else if (k === 'ArrowRight') rotate(STEP * fine, 0);
    else if (k === 'ArrowUp') rotate(0, STEP * fine);
    else if (k === 'ArrowDown') rotate(0, -STEP * fine);
    else if (k === '+' || k === '=') zoom(1.2);
    else if (k === '-' || k === '_') zoom(1 / 1.2);
    else if (k === '0' || k === 'Home') usePreset(preset);
    else if (k === '1') usePreset('lander');
    else if (k === '2') usePreset('side');
    else if (k === '3') usePreset('top');
    else return;
    e.preventDefault();
    e.stopPropagation();
  }

  const pts = new Map<number, { x: number; y: number; mouse: boolean }>();
  let pinch = 0;
  function pinchDist(): number {
    const it = pts.values();
    const a = it.next().value;
    const b = it.next().value;
    return a && b ? Math.hypot(a.x - b.x, a.y - b.y) : 0;
  }
  function onDown(e: PointerEvent) {
    if (e.pointerType === 'mouse' && e.button !== 0) return;
    pts.set(e.pointerId, { x: e.clientX, y: e.clientY, mouse: e.pointerType === 'mouse' });
    (e.currentTarget as HTMLElement).setPointerCapture?.(e.pointerId);
    if (pts.size === 2) pinch = pinchDist();
  }
  function onMove(e: PointerEvent) {
    const p = pts.get(e.pointerId);
    if (!p) return;
    const dx = e.clientX - p.x;
    const dy = e.clientY - p.y;
    p.x = e.clientX;
    p.y = e.clientY;
    if (pts.size === 2) {
      const d = pinchDist();
      if (pinch > 0 && d > 0) zoomBy(vs.cam, d / pinch);
      pinch = d;
      push();
      return;
    }
    orbit(vs.cam, dx * DRAG, p.mouse ? -dy * DRAG : 0); // al tocco solo rotazione orizzontale: lo scroll resta libero
    push();
  }
  function onUp(e: PointerEvent) {
    if (!pts.delete(e.pointerId)) return;
    pinch = 0;
    viewChanged();
  }
  function onWheel(e: WheelEvent) {
    if (!e.ctrlKey && !e.metaKey) return;
    e.preventDefault();
    zoomBy(vs.cam, Math.exp(-e.deltaY * 0.01));
    push();
  }

  /**
   * Learning | Avanzato: stessa scena e stessi numeri. Learning tiene sito, stazione, velocità e altezza del palo con
   * nomi semplici e le schede "Cosa succede" e "Cosa non è modellato"; guadagno, errore di puntamento, esagerazioni,
   * numeri ed esportazione sono in Avanzato (i valori restano quelli scelti). Chiavi stabili (i18n in arrivo).
   */
  const STR = $derived({
    learn: t('lander.learn'),
    introSimple: t('lander.introSimple'),
    site: t('lander.site'),
    station: t('lander.station'),
    rate: t('lander.rate'),
    mast: t('lander.mast'),
    tabs: {
      numbers: t('lander.tab.numbers'),
      section: t('lander.tab.section'),
      text: t('lander.tab.textSimple'),
      limits: t('lander.tab.limitsSimple'),
    } as Record<TabId, string>,
  });
  const LEARN_TABS: readonly TabId[] = ['text', 'limits'];
  const adv = $derived(modeNow.advanced);
  const visibleTabs = $derived(TABS.filter((t) => !(sectionMode && t.id === 'section') && (adv || LEARN_TABS.includes(t.id))));
  const shown = $derived.by<TabId>(() => (visibleTabs.some((t) => t.id === tab) ? tab : (visibleTabs[0]?.id ?? 'numbers')));

  function onTabKey(e: KeyboardEvent) {
    const list = visibleTabs;
    const i = list.findIndex((t) => t.id === shown);
    const next = e.key === 'ArrowRight' ? i + 1 : e.key === 'ArrowLeft' ? i - 1 : e.key === 'Home' ? 0 : e.key === 'End' ? list.length - 1 : null;
    if (next === null) return;
    e.preventDefault();
    const t = list[(next + list.length) % list.length]!;
    tab = t.id;
    void tick().then(() => document.getElementById(`ltab-${t.id}`)?.focus());
  }

  function exportJson() {
    if (!data) return;
    downloadText(`scena-lander-${siteId}.json`, 'application/json', sceneJson(data, { pointingErrorDeg: errorDeg, verticalExaggeration: vExag, tubeScale, sunReal, sunElevationDeg: sun.elDeg }));
  }

  const f = (v: number | null, d = 2) => v === null ? '?' : formatNumber(v, { maximumFractionDigits: d });
  const sgn = (v: number, d = 2) => `${v >= 0 ? '+' : '−'}${f(Math.abs(v), d)}`;
  const rateText = (bps: number) => bps >= 1e6
    ? `${formatNumber(bps / 1e6, { maximumFractionDigits: bps % 1e6 ? 1 : 0 })} Mbit/s`
    : `${formatNumber(bps / 1e3, { maximumFractionDigits: 0 })} kbit/s`;
  const localizedState = (state: string) =>
    state === 'open' ? t('lander.state.open')
      : state === 'transition' ? t('lander.state.transition')
      : state === 'blocked' ? t('lander.state.blocked')
      : t('lander.state.unknown');
  const localizedStateHelp = (state: string) =>
    state === 'open' ? t('lander.state.openHelp')
      : state === 'transition' ? t('lander.state.transitionHelp')
      : state === 'blocked' ? t('lander.state.blockedHelp')
      : t('lander.state.unknownHelp');
  const sceneProblem = (error: SceneError) => {
    switch (error.kind) {
      case 'range': return t('lander.error.range');
      case 'coverage': return t('lander.error.coverage');
      case 'unavailable': return t('lander.error.unavailable');
      case 'busy': return t('lander.error.busy');
      case 'network': return t('lander.error.network');
      case 'invalid': return t('lander.error.invalid');
      case 'outside_model': return t('lander.rfOutsideModel');
    }
  };
  const presetLabel = (id: Preset) => t(`lander.preset.${id}` as 'lander.preset.lander' | 'lander.preset.side' | 'lander.preset.top');
  const modeLabel = $derived(mode === 'webgl' ? t('lander.mode.webgl') : mode === 'canvas2d' ? t('lander.mode.canvas2d') : mode === 'none' ? t('lander.mode.none') : '');
</script>

{#if !embedded}<SubNav title="Scena lander" learn={STR.learn} />{/if}

<div class="workspace tile tile--alt">
  <div class="container container--wide">
    {#snippet setup()}
    <Callout title={t('lander.introTitle')} id="intro">
      {#if !adv}<p>{STR.introSimple}</p>{:else}
      <p>
        Dal polo Sud la Terra sta pochi gradi sopra l’orizzonte: l’antenna del rover guarda quasi radente al suolo e il crinale davanti a lei può tagliare la
        <strong>prima zona di Fresnel</strong> (il tubo traslucido). Verde, ambra o rosso: stato del link calcolato dal motore RAVEN; il testo e i numeri dicono la stessa cosa.
      </p>
      <p class="small">
        Il terreno viene dal prodotto LOLA a 20 m (mai inventato), campionato su una griglia più grossolana. La Terra è a circa 384 000 km: la zona di Fresnel e il fascio sono
        disegnati <strong>solo nel campo vicino</strong> all’antenna, e la Terra è disegnata con il suo diametro angolare vero ma a una distanza simbolica.
      </p>{/if}
    </Callout>

    <form class="panel setup" onsubmit={(e) => e.preventDefault()} aria-labelledby="setup-h">
      <h2 id="setup-h">Scenario</h2>
      <div class="grid">
        <p class="field">
          <label for="l-site">{adv ? 'Sito' : STR.site}</label>
          <select id="l-site" value={siteId} onchange={(e) => selectSite((e.currentTarget as HTMLSelectElement).value)} disabled={sites.length === 0}>
            {#each sites as s (s.id)}
              <option value={s.id} disabled={!s.dem_covered}>{s.name}{s.dem_covered ? '' : ' (fuori copertura DEM)'}</option>
            {/each}
            {#if customList.length}
              <optgroup label={t('custom.group')}>{#each customList as c (c.id)}<option value={c.id}>{c.name}</option>{/each}</optgroup>
            {/if}
          </select>
          <span class="hint">siti del catalogo coperti dal DEM LOLA (lat ≤ −85°); i siti personalizzati usano il prodotto LOLA che li copre</span>
        </p>
        {#if !embedded}<CustomSiteControl onadd={(id) => selectSite(id)} />{/if}
        <p class="field">
          <label for="l-station">{adv ? 'Stazione di terra' : STR.station}</label>
          <select id="l-station" bind:value={station}>
            <option value="dsn34">DSN 34 m</option>
            <option value="dsn18">DSN 18 m (ipotesi)</option>
          </select>
        </p>
        <p class="field">
          <label for="l-rate">{adv ? 'Bit-rate' : STR.rate}</label>
          <select id="l-rate" bind:value={rate}>
            {#each BITRATES as b (b)}<option value={b}>{rateText(b)}</option>{/each}
          </select>
        </p>
        {#if adv}
        <p class="field">
          <label for="l-gain">Guadagno antenna rover (dBi) <Badge status="I" /></label>
          <input id="l-gain" type="number" min="-10" max="45" step="0.5" bind:value={gain} />
        </p>
        {/if}
        <p class="field">
          <label for="l-mast">{adv ? 'Altezza del palo' : STR.mast}: <output for="l-mast" data-testid="mast-value">{f(mast, 1)}</output> m <Badge status="I" /></label>
          <input id="l-mast" type="range" min={MAST_RANGE[0]} max={MAST_RANGE[1]} step="0.5" bind:value={mast} />
        </p>
        {#if adv}
        <p class="field">
          <label for="l-err">Errore di puntamento: <output for="l-err" data-testid="err-value">{f(errorDeg, 1)}</output>° (HPBW {data ? f(hpbw, 1) : '…'}°)</label>
          <input id="l-err" type="range" min="0" max={Math.max(5, Math.ceil(hpbw))} step="0.1" bind:value={errorDeg} aria-describedby="l-err-hint" />
          <span id="l-err-hint" class="hint">{pt ? `perdita ${f(pt.lossDb, 2)} dB; ${pt.beyond ? 'oltre HPBW/2: cono rosso' : 'entro HPBW/2'}` : ''}</span>
        </p>
        <p class="field">
          <label for="l-vex">Esagerazione verticale del terreno</label>
          <select id="l-vex" bind:value={vExag}>
            <option value={1}>×1 (scala vera)</option>
            <option value={2}>×2</option>
            <option value={5}>×5</option>
          </select>
        </p>
        <p class="field">
          <label for="l-tube">Raggio disegnato del tubo di Fresnel</label>
          <select id="l-tube" bind:value={tubeScale}>
            <option value={1}>×1 (raggio vero)</option>
            <option value={5}>×5</option>
            <option value={20}>×20</option>
          </select>
        </p>
        {/if}
      </div>
    </form>

    <p class="status" role="status" data-testid="lander-status">
      {#if busy || loading}{data ? t('lander.sceneUpdating') : t('lander.calculatingScene')}{:else if data}{t('lander.sceneUpdated', { site: siteName, time: data.tUtc.replace('T', ' ').replace('Z', '') })}{/if}
    </p>
    {#if listError}<p role="alert" class="notice" data-testid="lander-error">{listError}</p>{/if}
    {#if problem}
      <div role="alert" class="notice" data-kind={problem.kind} data-testid="lander-error">
        <p>{sceneProblem(problem)}</p>
      </div>
    {/if}
    {/snippet}

    <div class="scene-layout">
    <section class="figure tone-dark" class:cinematic={cinematic && !sectionMode} aria-labelledby="fig-h">
      <h2 id="fig-h" class="visually-hidden">{sectionMode ? t('lander.sideSectionOfScene') : t('lander.scene3d')}</h2>
      <div class="stage-frame">
      <!-- svelte-ignore a11y_no_noninteractive_tabindex, a11y_no_noninteractive_element_interactions -->
      <div
        class="stage"
        bind:this={host}
        id="lander-stage"
        role="group"
        tabindex="0"
        aria-roledescription={sectionMode ? t('lander.sideSection') : t('lander.chart3d')}
        aria-label={sectionMode
          ? t('lander.stageSectionLabel')
          : t('lander.stageSceneLabel')}
        aria-describedby="lander-help"
        aria-busy={loading || busy}
        data-spatial-skip
        data-ready={drawn ? '1' : undefined}
        data-mode={mode ?? ''}
        onkeydown={onStageKey}
        onpointerdown={onDown}
        onpointermove={onMove}
        onpointerup={onUp}
        onpointercancel={onUp}
        onwheel={onWheel}
      ></div>
      <p id="lander-help" class="visually-hidden">
        {t('lander.stageHelp')}
      </p>
      {#if controlled && !data}
        <p class="stage-note stage-cover" role="status">{problem ? t('lander.stageUnavailable') : t('lander.calculatingScene')}</p>
      {:else if !data && (loading || busy)}
        <p class="stage-note" aria-hidden="true">{t('lander.calculatingScene')}</p>
      {/if}
      <div class="hud">
        {#if !sectionMode}
          <div class="view-controls" role="group" aria-label={t('lander.viewControls')}>
            {#each PRESETS as p (p.id)}
              <button type="button" aria-pressed={preset === p.id} onclick={() => usePreset(p.id)}>{presetLabel(p.id)}</button>
            {/each}
            <button type="button" aria-pressed={cinematic} onclick={toggleCinematic}>{t('lander.cinematic')}</button>
            <button type="button" aria-label={t('lander.rotateLeft')} onclick={() => rotate(-STEP, 0)}>◀</button>
            <button type="button" aria-label={t('lander.rotateRight')} onclick={() => rotate(STEP, 0)}>▶</button>
            <button type="button" aria-label={t('lander.tiltUp')} onclick={() => rotate(0, STEP)}>▲</button>
            <button type="button" aria-label={t('lander.tiltDown')} onclick={() => rotate(0, -STEP)}>▼</button>
            <button type="button" aria-label={t('lander.zoomIn')} onclick={() => zoom(1.25)}>+</button>
            <button type="button" aria-label={t('lander.zoomOut')} onclick={() => zoom(1 / 1.25)}>−</button>
          </div>
        {/if}
      </div>
      </div>
      {#if data && info}
        <div class="hud-state" data-testid="hud-state" data-state={data.link.state}>
          <span class="dot" style:background={info.color} aria-hidden="true"></span>
          <strong>{info.symbol} {localizedState(info.state)}</strong>
          <span class="num">{t('lander.rateAt', { margin: t('lander.margin'), value: f(data.link.margin, 1), rate: rateText(data.link.rateBps) })}</span>
        </div>
      {/if}
      <span class="mode" data-testid="lander-mode" role="status" data-mode={mode ?? ''}>{modeLabel}</span>
    </section>
    {#if controlled}
      {#if plannerSettings}<SceneSettings>{@render plannerSettings()}</SceneSettings>{/if}
      <div hidden>
        {#if startMs !== null}
          <SkyTime body="moon" onlight={onLight} initialMs={startMs} externalMs={plannerMs} ontime={onTime} onLightError={onPlannerLightError} />
        {/if}
      </div>
    {:else}
    <SceneSettings>
    {@render setup()}
    <div class="skybar tone-dark">
      {#if startMs !== null}
        <SkyTime body="moon" onlight={onLight} initialMs={startMs} ontime={onTime} />
      {:else}
        <p class="small muted" role="status">{t('lander.selectingTrueSunInstant')}</p>
      {/if}
    </div>
    </SceneSettings>
    {/if}
    </div>
    {#if controlled && listError}<p role="alert">{listError}</p>{/if}
    {#if controlled && problem}<p role="alert">{sceneProblem(problem)}</p>{/if}
    {#if controlled && data}
      <p role="status" data-testid="planner-scene-status">
        {#if previousScene}{t('lander.previousScene')} {/if}
        {t('lander.sceneUpdated', { site: renderedSiteName, time: data.tUtc.replace('T', ' ').replace('Z', '') })}
      </p>
    {/if}
    {#if controlled && !light}<p role="status">{t('lander.lightUpdating')}</p>{/if}
    {#if viewError}<p role="alert">{viewError}</p>{/if}
    {#if mode === 'webgl'}
{#if !compact}      <p class="small muted" data-testid="lander-visual-credit">{t('lander.visualCredit')} {t(data?.sky ? 'lander.skyOriented' : 'lander.skyIllustrative')} {t('lander.terrainVisual')}</p>{/if}
      {#if skyError}<p class="small notice" role="status" data-testid="lander-sky-error">{t('lander.skyUnavailable')}</p>{/if}
    {/if}

    {#if pick}
      <p class="small" role="status" data-testid="instant-note" data-kind={pick.kind}>
        {#if pick.kind === 'grazing'}
          Istante scelto perché il Sole è radente: {f(pick.elDeg, 1)}° sull’orizzonte del sito (tra 1° e 3° nel mese successivo all’ora attuale), così il rilievo si vede. L’istante è
          nello scenario e si può cambiare dal pannello della data.
        {:else if pick.elDeg !== null && pick.elDeg < 0}
          Nessun istante con Sole radente (1°-3°) nel mese successivo all’ora attuale: resta l’istante dato, con il Sole a {f(pick.elDeg, 1)}°. Il terreno è in ombra.
        {:else}
          Nessun istante con Sole radente (1°-3°) nel mese successivo all’ora attuale: resta l’istante dato{pick.elDeg !== null ? `, con il Sole a ${f(pick.elDeg, 1)}°` : ''}.
        {/if}
      </p>
    {/if}
{#if !compact}    <p class="small muted" data-testid="sun-note">
      {#if sunReal}Luce: Sole reale a {f(sun.elDeg, 2)}° sull’orizzonte del sito (JPL DE440){vs.terrain ? `; ombre portate dal rilievo campionato: ${Math.round((vs.terrain.shadowFraction) * 100)}% del terreno in ombra` : ''}.
      {:else if hasRealLight}{t('lander.previousLight')}
      {:else}Luce di ripiego: Sole fisso a 1,5° dietro l’osservatore, <strong>non</strong> il Sole reale (nessuna luce calcolata per questo istante).{/if}
      {#if data}Il terreno sotto l’orizzonte del Sole è scuro. Le ombre sono quelle del campo di quote campionato a {f(data.terrain.patch?.spacingM ?? 0, 0)} m.{/if}
    </p>{/if}

    <div class="legend" aria-label={t('lander.legend')}>
      <ul class="key-list small">
        <li><span class="sw cyan" aria-hidden="true"></span>{t('lander.legend.profile')}</li>
        <li><span class="sw white" aria-hidden="true"></span>{t('lander.legend.lineOfSight')}</li>
        <li><span class="sw amber" aria-hidden="true"></span>{t('lander.legend.ridge')}</li>
        <li><span class="sw green" aria-hidden="true"></span>{t('lander.legend.beam')}</li>
      </ul>
{#if !compact}      <p class="small muted">
        {#if cinematic}{t('lander.overlaysHidden')} {/if}
        {tubeScale > 1 ? `Il raggio del tubo di Fresnel è disegnato ×${tubeScale} (il valore vero è nei numeri). ` : ''}{vExag > 1 ? `Il terreno è esagerato ×${vExag} in verticale. ` : ''}Il richiamo giallo sull’antenna e il segno arancione sul crinale sono ingranditi nelle viste lontane.
      </p>{/if}
    </div>

    {#snippet sceneDetails()}
    <section class="panel" aria-labelledby="res-h">
      <h2 id="res-h">Dettagli della scena</h2>
      <div class="tablist" role="tablist" aria-label="Dettagli della scena" tabindex="-1">
        {#each visibleTabs as tabItem (tabItem.id)}
          <button type="button" role="tab" id="ltab-{tabItem.id}" aria-selected={shown === tabItem.id} aria-controls="lpanel-{tabItem.id}" tabindex={shown === tabItem.id ? 0 : -1} onclick={() => (tab = tabItem.id)} onkeydown={onTabKey}>{tabItem.label}</button>
        {/each}
      </div>
      {#each TABS as tabItem (tabItem.id)}
        <div role="tabpanel" id="lpanel-{tabItem.id}" aria-labelledby="ltab-{tabItem.id}" hidden={shown !== tabItem.id} tabindex="0" class="tabpanel">
          {#if shown === tabItem.id}
            {#if !data}
              <p class="muted">Nessuna scena: attendi il calcolo o scegli un sito coperto dal DEM.</p>
            {:else if tabItem.id === 'numbers'}
              <dl class="meta" data-testid="lander-hud">
                <dt>Terra</dt>
                <dd data-testid="hud-earth">elevazione {f(data.earth.elDeg, 2)}°, azimut {f(data.earth.azDeg, 1)}°, distanza {Math.round(data.earth.rangeKm).toLocaleString('it-IT')} km <Badge status="D" /></dd>
                <dt>Crinale dominante</dt>
                <dd data-testid="hud-ridge">cima a {f(data.ridge.tipElevationDeg, 2)}° ({sgn(data.ridge.angleAboveLosDeg)}° rispetto alla Terra), a {f(data.ridge.arcDistanceM, 0)} m; {f(Math.abs(data.ridge.heightAboveLosM), 1)} m {data.ridge.heightAboveLosM >= 0 ? 'sopra' : 'sotto'} la linea di vista <Badge status="V" /></dd>
                <dt>ν</dt><dd data-testid="hud-nu">{f(data.ridge.nu, 2)}</dd>
                <dt>Zona di Fresnel</dt>
                <dd data-testid="hud-fresnel">raggio al crinale {f(data.fresnel.r1AtRidgeM, 2)} m (λ {f(data.fresnel.wavelengthM * 100, 2)} cm, d1 {f(data.ridge.d1M, 0)} m); il crinale occupa {f(ridgeObstruction(data) * 100, 0)}% del raggio <Badge status="D" /></dd>
                <dt>Perdita di diffrazione</dt>
                <dd data-testid="hud-diffraction">lama {f(data.diffraction.knifeEdgeDb, 2)} dB + correzione cresta {f(data.diffraction.correctionDb, 2)} dB = {f(data.diffraction.lossDb, 2)} dB<br /><span class="small muted">{data.diffraction.correctionLabel}; raggio cresta {data.ridge.radiusM === null ? 'non stimabile' : `${f(data.ridge.radiusM, 0)} m`}{data.ridge.radiusResolved ? '' : ' (non risolto dal DEM)'}</span></dd>
                <dt>Multipath</dt>
                <dd data-testid="hud-multipath">{data.diffraction.multipathApplicable ? `${sgn(data.diffraction.multipathGainDb ?? 0)} dB` : `non applicabile${data.diffraction.multipathReason ? `: ${data.diffraction.multipathReason}` : ''}`} <Badge status="D" /></dd>
                <dt>Perdita totale</dt><dd data-testid="hud-total">{f(data.diffraction.totalLossDb, 2)} dB (lama + correzione − multipath)</dd>
                <dt>Margine di link</dt>
                <dd data-testid="hud-margin">{t('lander.marginAtRate', { value: f(data.link.margin, 2), rate: rateText(data.link.rateBps) })} <strong>{info?.symbol} {localizedState(data.link.state)}</strong> <span class="small muted">({localizedStateHelp(data.link.state)})</span> <Badge status="I" /></dd>
                <dt>Antenna</dt>
                <dd data-testid="hud-antenna">guadagno {f(data.antenna.gainDbi, 1)} dBi, diametro {f(data.antenna.diameterM, 2)} m, HPBW {f(data.antenna.hpbwDeg, 1)}°; palo {f(data.antenna.mastM, 1)} m <Badge status={data.antenna.mastTag} /></dd>
                <dt>Puntamento</dt>
                <dd data-testid="hud-pointing">{t('lander.pointingError', { error: f(errorDeg, 1) })}: {t('lander.loss')} {f(pt?.lossDb ?? 0, 2)} dB, {pt?.beyond ? t('lander.beamBeyond') : t('lander.beamWithin')}; {t('lander.pointingMargin')} {f(pt?.marginDb ?? null, 2)} dB, {t('lander.stateLabel')} {pt ? localizedState(pt.state).toLowerCase() : ''}</dd>
                <dt>Terreno</dt>
                <dd>{data.terrain.label}{data.terrain.synthetic ? ' — profilo sintetico di prova' : ''}; {data.terrain.patch ? `campo ${f(data.terrain.patch.sizeM / 1000, 1)} km, ${data.terrain.patch.n}×${data.terrain.patch.n} punti a ${f(data.terrain.patch.spacingM, 0)} m (prodotto a ${data.terrain.patch.nativeResolutionM} m)` : 'solo profilo'}; raggio cresta {data.terrain.radiusResolved ? 'risolto' : 'non risolto'}</dd>
              </dl>
              <p class="export">
                <button type="button" onclick={exportJson} data-testid="export-json">Scarica i numeri della scena (JSON)</button>
              </p>
            {:else if tabItem.id === 'section'}
              <p class="small muted">Sezione verticale lungo l’azimut della Terra: la banda è la prima zona di Fresnel, il terreno la copre dove il crinale la interseca. La scala verticale è esagerata (indicata nel grafico).</p>
              <div class="section-box" bind:this={secHost} data-testid="section-canvas" role="img" aria-label="Sezione laterale con profilo del terreno, crinale, linea di vista, zona di Fresnel, antenna, fascio e direzione della Terra. I numeri sono nella scheda Numeri e nella descrizione testuale."></div>
            {:else if tabItem.id === 'text'}
              <p data-testid="lander-text">{text}</p>
            {:else}
              <ul class="limits" data-testid="lander-limits">
                {#each data.limits as l (l)}<li>{l}</li>{/each}
                <li>La correzione della cresta arrotondata è T(m,n) di ITU-R P.526-9 par. 4.2 (formula verificata sul testo, non misurata); lo scarto dallo split-step simulato è l’incertezza.</li>
                <li>I parametri radio (guadagno, potenza, Tsys, altezza del palo) hanno tag I: illustrativi, senza fonte.</li>
                <li>Il campo di quote è a {data.terrain.patch ? f(data.terrain.patch.spacingM, 0) : '—'} m di passo: rocce o creste più piccole possono non comparire; il profilo del motore è a {f(data.terrain.profileSpacingM, 0)} m.</li>
              </ul>
              <p class="small muted">{data.disclaimer}</p>
            {/if}
          {/if}
        </div>
      {/each}
    </section>
    {/snippet}
    {#if compact}
      {#if !sectionMode && data}
        <section class="panel" aria-labelledby="sec-h" data-testid="lander-section-panel">
          <h2 id="sec-h">{t('lander.sectionPanel')}</h2>
          <div class="section-box" bind:this={secHost} data-testid="section-canvas" role="img"
            aria-label={t('lander.compactSectionLabel')}></div>
        </section>
      {/if}
    {:else}{@render sceneDetails()}{/if}
  </div>
</div>

<ModelStamp />
<div class="visually-hidden" role="status" aria-live="polite" aria-atomic="true" bind:this={liveEl}></div>

<style>
  .workspace {
    container-type: inline-size;
    padding-block: var(--space-2) var(--space-7);
  }
  .workspace > .container {
    max-width: none;
  }
  .small,
  .hint {
    font-size: var(--fs-small);
  }
  .hint {
    display: block;
    color: var(--c-muted);
    margin-top: var(--space-1);
  }
  .setup,
  .figure,
  .legend,
  .skybar {
    margin-top: var(--space-4);
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
  .field input:not([type='range']),
  .field select {
    width: 100%;
  }
  .field input[type='range'] {
    width: 100%;
    min-height: var(--target);
  }
  .status:empty {
    margin: 0;
  }
  .notice {
    border-left: 3px solid var(--c-danger);
    padding-left: var(--space-3);
    margin-block: var(--space-3);
  }
  .figure {
    margin-top: 0;
    position: relative;
    border-radius: var(--radius-md);
    overflow: hidden;
    background: #05070b;
    color: #f2f4f8;
  }
  .stage-frame {
    position: relative;
  }
  .stage {
    height: var(--scene-stage-height);
    width: 100%;
    touch-action: pan-y;
    cursor: grab;
    outline-offset: -3px;
  }
  .stage:active {
    cursor: grabbing;
  }
  .figure.cinematic .stage {
    height: max(320px, calc(100svh - var(--nav-h) - var(--space-4)));
  }
  .stage-note {
    position: absolute;
    inset: 0;
    display: grid;
    place-items: center;
    margin: 0;
    pointer-events: none;
    font-size: var(--fs-small);
  }
  .stage-cover {
    background: #080b12;
  }
  .hud-state {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: var(--space-2);
    max-width: calc(100% - 2 * var(--space-3));
    background: rgb(5 7 11 / 80%);
    padding: var(--space-1) var(--space-3);
    border-radius: var(--radius-md);
    font-size: var(--fs-small);
    pointer-events: none;
  }
  .dot {
    width: 0.7rem;
    height: 0.7rem;
    border-radius: 50%;
    display: inline-block;
  }
  .hud {
    position: absolute;
    inset-inline: var(--space-2);
    inset-block-end: var(--space-2);
    display: flex;
    overflow-x: auto;
    align-items: flex-end;
    justify-content: space-between;
    gap: var(--space-2);
    padding: var(--space-1);
  }
  .view-controls {
    display: flex;
    flex-wrap: nowrap;
    gap: var(--space-1);
    pointer-events: auto;
  }
  .view-controls button {
    white-space: nowrap;
    min-width: var(--target);
    min-height: var(--target);
    background: rgb(11 15 23 / 78%);
    color: #f2f4f8;
    border: 1px solid rgb(255 255 255 / 40%);
  }
  .view-controls button[aria-pressed='true'] {
    background: #f2f4f8;
    color: #0b0f17;
  }
  .mode {
    font-size: var(--fs-small);
    color: #f2f4f8;
    background: rgb(11 15 23 / 78%);
    padding: var(--space-1) var(--space-3);
    border-radius: var(--radius-md);
  }
  .mode:empty {
    display: none;
  }
  .skybar {
    padding: var(--space-2) var(--space-4);
    border-radius: var(--radius-md);
    background: #0b0f17;
    color: #f2f4f8;
    position: relative;
  }
  .key-list {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-1) var(--space-4);
    list-style: none;
    margin: var(--space-2) 0;
    padding: 0;
  }
  .key-list li {
    display: inline-flex;
    align-items: center;
    gap: var(--space-2);
  }
  .sw.cyan {
    background: #6ee7ff;
  }
  .sw.white {
    background: #fff;
  }
  .sw.amber {
    background: #ffb340;
  }
  .sw.green {
    background: #30d158;
  }
  .sw {
    display: inline-block;
    width: 1.5rem;
    height: 4px;
    flex: none;
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
  .tabpanel[hidden] {
    display: none;
  }
  .section-box {
    position: relative;
    height: clamp(260px, 44vh, 460px);
    border-radius: var(--radius-md);
    overflow: hidden;
    background: #05070b;
  }
  .meta {
    display: grid;
    grid-template-columns: minmax(0, 1fr);
    gap: 0;
    margin: 0;
  }
  .meta dt {
    font-weight: 600;
    margin-top: var(--space-2);
  }
  .meta dd {
    margin: 0;
    overflow-wrap: anywhere;
  }
  .export {
    margin: var(--space-3) 0 0;
  }
  .limits {
    padding-left: var(--space-5);
  }
  @media (min-width: 720px) {
    .meta {
      grid-template-columns: 14rem minmax(0, 1fr);
      gap: var(--space-1) var(--space-4);
    }
    .meta dt {
      margin-top: 0;
    }
  }
  @media (max-width: 639px) {
    [role='tab'] {
      padding: 0 var(--space-2);
      font-size: var(--fs-small);
    }
  }
</style>
