<!-- SPDX-License-Identifier: Apache-2.0 -->
<!--
  Visualizzatore come strumento (HUD): corpo celeste a tutta finestra con mappe NASA, scelta del corpo
  (tablist), pannello "Esplora" (foglio dal basso sotto 834px) con ricerca, filtri e luoghi citati,
  marcatori come veri pulsanti, cifra chiave con fonte, cursore della luce con riproduzione, zoom, schermo
  intero, indicatore in diretta legato alla telemetria (solo Luna), attribuzione sempre visibile.
-->
<script lang="ts">
  import ModelStamp from '../../shell/ModelStamp.svelte';
  import SceneSettings from '../../components/ui/SceneSettings.svelte';
  import { onMount, tick, type Snippet } from 'svelte';
  import { customSites as customStore, type CustomSiteDef } from '../../shell/customSites';
  import CustomSiteControl from '../../shell/CustomSiteControl.svelte';
  import { setPageContext, clearPageContext } from '../../shell/pageContext.svelte';
  import { announce } from '../../shell/a11y';
  import Icon from '../../components/ui/Icon.svelte';
  import { mountViewport, type ViewportHandle } from '../../viewports/port';
  import { selectViewportFactory, type ViewportMode } from '../../viewports/select';
  import { router } from '../../registry';
  import { withBase } from '../../shell/router';
  import { BITRATES, msToT, scenarioStore, tToMs, withScenario, type Scenario } from '../../shell/scenario';
  import {
    centerOn,
    clampPitch,
    clampZoom,
    DEFAULT_SCENE,
    describeScene,
    projectLatLon,
    rotationRows,
    wrapYaw,
    ZOOM_MAX,
    ZOOM_MIN,
    type BodyId,
    type DiskFrame,
    type OverlayRaster,
    type SceneState,
  } from '../../viewports/scene';
  import { ASSETS } from '../../viewports/bodies/assets';
  import { assetsFor, BODIES, KIND_LABEL, starsAsset, type Place, type PlaceKind } from '../../viewports/bodies/registry';
  import { preloadIdle } from '../../viewports/textures';
  import { formatNumber, subscribeTelemetry, utcClock, type TelemetrySnapshot } from '../../shell/telemetryStore';
  import { readBody, VIEWER_BODIES, writeBody } from './bodyState';
  import SkyTime from './SkyTime.svelte';
  import { thinMarkers } from './markerLayout';
  import { getContext } from 'svelte';
  import { HUB_KEY } from '../../shell/hub';
  import { modeNow } from '../../shell/modeState.svelte';
  import type { Light, SkyBody } from './skyLight';
  import {
    earthAngleText,
    fsplDeltaText,
    highlightedComplex,
    localDirToBody,
    moonSeenText,
    placeState,
    rangeText,
    SnapshotClient,
    STATE_HELP,
    STATE_LABEL,
    type LinkState,
    type SnapComplex,
    type Snapshot,
  } from './snapshot';

  let { embedded = false, onBodyChange, overlay = null, tall = false, below }: {
    embedded?: boolean; onBodyChange?: (body: BodyId) => void;
    /** Sovramappa del polo sud (RGBA) sulla Luna; la scelta e la legenda stanno nella pagina che la passa. */
    overlay?: OverlayRaster | null;
    /** Occupa gran parte dello schermo (dashboard). */
    tall?: boolean;
    /** Contenuto della pagina ospite subito sotto la scena (es. la scelta delle sovramappe). */
    below?: Snippet;
  } = $props();
  const STEP = 10;
  const DRAG_DEG_PER_PX = 0.35;
  const mql = typeof window.matchMedia === 'function' ? window.matchMedia('(prefers-reduced-motion: reduce)') : null;
  let motionAllowed = $state(!(mql?.matches ?? false));
  let liveEl: HTMLElement | undefined = $state();
  let announceTimer: ReturnType<typeof setTimeout> | undefined;

  let body = $state<BodyId>(readBody(location.search));
  $effect(() => { onBodyChange?.(body); });
  let skyLight = $state<Light | null>(null);
  let telemetry = $state<TelemetrySnapshot>({ status: null, last: null });
  let view = $state({ yaw_deg: DEFAULT_SCENE.yaw_deg, pitch_deg: DEFAULT_SCENE.pitch_deg, autoRotate: false, zoom: 1 });
  let stageW = $state(0);
  let stageH = $state(0);
  const narrow = $derived(stageW > 0 && stageW <= 833);
  let query = $state('');
  let kind = $state<PlaceKind | 'all'>('all');
  let selected = $state<string | null>(null);
  let sheetOpen = $state(false);
  let fullscreen = $state(false);
  const canFullscreen = typeof document !== 'undefined' && !!document.fullscreenEnabled;

  /* ---------------- scenario condiviso e istantanea RAVEN (/api/raven/snapshot) ---------------- */
  const BASE = import.meta.env.BASE_URL;
  const store = scenarioStore();
  let sc = $state<Scenario>(store.reload());
  const rate = $derived(sc.bitrate ?? 1e5);
  const initialMs = tToMs(store.get().t);
  let simMs = $state<number | null>(null);
  let snap = $state.raw<Snapshot | null>(null);
  let snapProblem = $state<string | null>(null);
  let snapBusy = $state(false);
  let skyTime: { pause: () => void } | undefined = $state();
  const snapClient = new SnapshotClient({
    onSnapshot: (s) => {
      snap = s;
      snapProblem = null;
    },
    onError: (e) => {
      // mai mostrare lo stato di un altro istante come se fosse questo
      snap = null;
      snapProblem =
        e.kind === 'range'
          ? 'Istante o parametri non validi per il servizio: nessuno stato del link.'
          : 'Analisi del link non disponibile in questo momento: nessuno stato del link.';
    },
    onBusy: (b) => (snapBusy = b),
  });
  function onTime(ms: number, explicit: boolean) {
    simMs = ms;
    if (explicit) store.set({ t: msToT(ms) });
  }
  $effect(() => {
    const ms = simMs;
    const r = rate;
    const st = sc.station;
    const gain = sc.gain;
    if (ms !== null) {
      snap = null;
      snapClient.request(ms, r, st, gain);
    }
  });
  const landerAvailable = router.resolve('/lander')?.path === '/lander';
  // dentro Siti (scheda Globo) l'h1 è della pagina contenitore: qui il titolo del corpo scende a h2
  const inHub = !!getContext(HUB_KEY);

  const def = $derived(BODIES[body]);
  const skyBody = $derived<SkyBody | null>(def.emissive ? null : (body as SkyBody));
  // la luce vale solo per il corpo per cui e' stata calcolata
  const sunObj = $derived(skyLight && skyLight.body === body && !def.emissive ? skyLight.dir : undefined);
  const live = $derived(telemetry.status?.kind === 'open');

  const frame = $derived.by<DiskFrame | undefined>(() => {
    if (stageW < 1 || stageH < 1) return undefined;
    const r = Math.min(stageW * 0.42, stageH * 0.42) * view.zoom;
    return { cx: stageW / 2, cy: stageH / 2, r };
  });


  let host: HTMLElement | undefined = $state();
  let root: HTMLElement | undefined = $state();
  let error = $state<string | null>(null);
  let mode = $state<ViewportMode | null>(null);
  const modeLabel = $derived(
    mode === 'webgl'
      ? 'Accelerazione WebGL attiva'
      : mode === 'canvas2d'
        ? 'Modalità compatibile (senza WebGL)'
        : mode === 'none'
          ? 'Grafica non disponibile: usa la descrizione testuale'
          : '',
  );
  let handle: ViewportHandle | null = null;

  /* ------------------------------ luoghi e marcatori ------------------------------ */

  const norm = (s: string) => s.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();
  // Luna: luoghi del registro; Terra: complessi DSN dal servizio (coordinate DSN 810-005 Tab. 5, mai scritte qui)
  const stationPlaces = $derived<Place[]>(
    snap
      ? snap.complexes.map((c) => ({
          id: c.complex.toLowerCase(),
          name: c.complex,
          kind: 'station' as const,
          lat: c.lat,
          lon: c.lon,
          note: 'complesso della Deep Space Network',
          source: snap!.source.document,
        }))
      : [],
  );
  // siti personalizzati dello scenario condiviso: segnaposto accanto a quelli del catalogo (stato dal servizio)
  let customList = $state<readonly CustomSiteDef[]>(customStore.get());
  onMount(() => customStore.subscribe((l) => { customList = l; }));
  const customPlaces = $derived<Place[]>(customList.map((c) => ({
    id: c.id, name: c.name, kind: 'custom', lat: c.lat_deg, lon: c.lon_deg_east, siteId: c.id,
    note: 'sito personalizzato: coordinate dell\'utente, non verificate', source: 'utente',
  })));
  const allPlaces = $derived<Place[]>(body === 'earth' ? stationPlaces : [...def.places, ...(body === 'moon' ? customPlaces : [])]);
  const complexOf = (p: Place): SnapComplex | null => snap?.complexes.find((c) => c.complex.toLowerCase() === p.id) ?? null;
  const bestComplex = $derived(snap ? highlightedComplex(snap) : null);
  const kinds = $derived([...new Set(allPlaces.map((p) => p.kind))]);
  const shown = $derived(
    allPlaces.filter((p) => (kind === 'all' || p.kind === kind) && (!query.trim() || norm(`${p.name} ${p.note ?? ''}`).includes(norm(query.trim())))),
  );
  /** Stato mostrato per un marcatore: colore e testo (il testo c'e' sempre). */
  function markerInfo(p: Place): { state: string; text: string } {
    if (body === 'earth') {
      const c = complexOf(p);
      if (!c) return { state: 'none', text: '' };
      return c.complex === bestComplex
        ? { state: 'sees-best', text: 'vede la Luna' }
        : c.sees
          ? { state: 'sees', text: 'vede la Luna' }
          : { state: 'nomoon', text: 'Luna non visibile' };
    }
    if (!p.siteId && p.kind !== 'polar') return { state: 'none', text: '' };
    if (!snap && snapProblem && p.lat <= -85) return { state: 'unavailable', text: 'stato non disponibile' };
    const l = placeState(p.siteId, p.lat, snap);
    return { state: l.state, text: l.label };
  }
  const markers = $derived(
    frame
      ? thinMarkers(
          shown
            .map((p) => ({ p, at: projectLatLon(p.lat, p.lon, view, frame), id: p.id }))
            .filter((m) => m.at.visible && m.at.x > 0 && m.at.y > 0 && m.at.x < stageW && m.at.y < stageH)
            .map((m) => ({ ...m, x: m.at.x, y: m.at.y, info: markerInfo(m.p) })),
          selected,
        )
      : [],
  );
  /** Etichette che si sovrappongono: resta solo il punto (l'etichetta torna al passaggio o al focus). */
  const labelled = $derived.by(() => {
    const boxes: { x: number; y: number; w: number }[] = [];
    const out = new Set<string>();
    for (const m of [...markers].sort((a, b) => (a.p.id === selected ? -1 : b.p.id === selected ? 1 : 0))) {
      const w = 22 + (m.p.name.length + (m.info.text ? m.info.text.length + 3 : 0)) * 7;
      const box = { x: m.at.x + 12, y: m.at.y - 11, w };
      if (boxes.some((b) => box.x < b.x + b.w && b.x < box.x + box.w && Math.abs(box.y - b.y) < 22)) continue;
      boxes.push(box);
      out.add(m.p.id);
    }
    return out;
  });
  const current = $derived(allPlaces.find((p) => p.id === selected) ?? null);
  const selSite = $derived(body === 'moon' && current?.siteId ? (snap?.sites.find((s) => s.id === current.siteId) ?? null) : null);
  const selComplex = $derived(body === 'earth' && current ? complexOf(current) : null);

  const scene = $derived<SceneState>({
    yaw_deg: view.yaw_deg,
    pitch_deg: view.pitch_deg,
    autoRotate: view.autoRotate,
    zoom: view.zoom,
    body,
    sun: def.emissive || sunObj ? undefined : { az_deg: 120, el_deg: 8 },
    sunObj,
    // Terra dal sito scelto (snapshot) o dalla telemetria; senza dati resta "non disponibile" (nessun valore di ripiego)
    earth: body === 'moon' ? (selSite ? { az_deg: selSite.earthAz, el_deg: selSite.earthEl } : telemetry.last?.earth) : undefined,
    frame,
  });
  const description = $derived(describeScene(scene, motionAllowed));

  /** Linea dal punto verso una direzione locale (azimut, elevazione): proiezione ortografica schematica sul disco. */
  function dirLine(lat: number, lon: number, az: number, el: number) {
    if (!frame) return null;
    const p = projectLatLon(lat, lon, view, frame);
    if (!p.visible) return null;
    const d = localDirToBody(lat, lon, az, el);
    const m = rotationRows(view.yaw_deg, view.pitch_deg);
    const vx = m[0]! * d[0] + m[1]! * d[1] + m[2]! * d[2];
    const vy = m[3]! * d[0] + m[4]! * d[1] + m[5]! * d[2];
    const vz = m[6]! * d[0] + m[7]! * d[1] + m[8]! * d[2];
    const h = Math.hypot(vx, vy);
    const len = 64 + 56 * h;
    const ux = h > 0.02 ? vx / h : 0;
    const uy = h > 0.02 ? vy / h : 1;
    const x2 = p.x + ux * len;
    const y2 = p.y - uy * len;
    return { x1: p.x, y1: p.y, x2, y2, ang: (Math.atan2(y2 - p.y, x2 - p.x) * 180) / Math.PI, front: vz >= 0 };
  }
  /** Luna: sito -> Terra. Terra: complesso (scelto, altrimenti quello che vede la Luna) -> Luna. */
  const dirOverlay = $derived.by(() => {
    if (selSite && current) {
      const l = dirLine(current.lat, current.lon, selSite.earthAz, selSite.earthEl);
      return l ? { ...l, id: 'earth-line', text: earthAngleText(selSite.earthEl), sub: `azimut ${Math.round(selSite.earthAz)}°` } : null;
    }
    if (body === 'earth' && snap) {
      const c = selComplex ?? snap.complexes.find((x) => x.complex === bestComplex) ?? null;
      if (!c || c.moonEl <= 0) return null;
      const l = dirLine(c.lat, c.lon, c.moonAz, c.moonEl);
      return l ? { ...l, id: 'moon-line', text: `${c.complex}: Luna a ${Math.round(c.moonEl)}° sull’orizzonte`, sub: `azimut ${Math.round(c.moonAz)}°` } : null;
    }
    return null;
  });
  const overlayLabel = $derived.by(() => {
    const o = dirOverlay;
    if (!o) return null;
    const x = Math.max(8, Math.min(stageW - 190, o.x2 + (Math.cos((o.ang * Math.PI) / 180) >= 0 ? 8 : -178)));
    const y = Math.max(8, Math.min(stageH - 60, o.y2 - 18));
    return { x, y };
  });

  // "Spiega questa pagina": corpo celeste e luogo scelti
  $effect(() => {
    if (embedded) return;
    setPageContext({
      params: {
        body,
        ...(selected ? { place: selected } : {}),
        ...(snap ? { istante_utc: snap.tUtc, distanza_terra_luna_km: Math.round(snap.rangeKm) } : {}),
        ...(selSite ? { stato_link: STATE_LABEL[selSite.state], elevazione_terra_gradi: Number(selSite.earthEl.toFixed(2)) } : {}),
      },
    });
  });
  $effect(() => {
    if (!embedded) return clearPageContext;
  });

  const coord = (v: number, pos: string, neg: string) => `${formatNumber(Math.abs(v), 2)}° ${v >= 0 ? pos : neg}`;
  const latLon = (p: Place) => `${coord(p.lat, 'N', 'S')}, ${coord(p.lon, 'E', 'O')}`;

  let tween = 0;
  function goTo(p: Place) {
    selected = p.id;
    if (p.siteId) store.set({ site: p.siteId });
    const target = centerOn(p.lat, p.lon);
    cancelAnimationFrame(tween);
    const from = { ...view };
    const dyaw = wrapYaw(target.yaw_deg - from.yaw_deg);
    const dpitch = target.pitch_deg - from.pitch_deg;
    const done = () => announceNow(`${p.name} al centro: ${latLon(p)}.`);
    if (!motionAllowed) {
      view = { ...view, yaw_deg: target.yaw_deg, pitch_deg: target.pitch_deg, autoRotate: false };
      done();
      return;
    }
    view = { ...view, autoRotate: false };
    const t0 = performance.now();
    const stepT = (now: number) => {
      const t = Math.min(1, (now - t0) / 700);
      const e = 1 - (1 - t) ** 3;
      view = { ...view, yaw_deg: wrapYaw(from.yaw_deg + dyaw * e), pitch_deg: from.pitch_deg + dpitch * e };
      if (t < 1) tween = requestAnimationFrame(stepT);
      else done();
    };
    tween = requestAnimationFrame(stepT);
  }

  export function revealSite(siteId: string) {
    const place = BODIES.moon.places.find((p) => p.siteId === siteId);
    if (!place) return;
    if (body !== 'moon') selectBody('moon');
    goTo(place);
  }

  export function pauseTime() {
    skyTime?.pause();
  }

  /* ------------------------------------ corpo ------------------------------------ */

  let tabs: HTMLElement | undefined = $state();
  function selectBody(id: BodyId, focus = false) {
    if (id === body) return;
    cancelAnimationFrame(tween);
    body = id;
    selected = null;
    query = '';
    kind = 'all';
    view = { yaw_deg: DEFAULT_SCENE.yaw_deg, pitch_deg: DEFAULT_SCENE.pitch_deg, autoRotate: false, zoom: 1 };
    writeBody(id);
    announceNow(`${BODIES[id].name} selezionata.`.replace('Sole selezionata', 'Sole selezionato'));
    if (focus) void tick().then(() => tabs?.querySelector<HTMLElement>(`[data-body="${id}"]`)?.focus());
  }
  function onTabKey(e: KeyboardEvent) {
    const i = VIEWER_BODIES.indexOf(body);
    const n = VIEWER_BODIES.length;
    const next =
      e.key === 'ArrowRight' || e.key === 'ArrowDown' ? (i + 1) % n
      : e.key === 'ArrowLeft' || e.key === 'ArrowUp' ? (i - 1 + n) % n
      : e.key === 'Home' ? 0
      : e.key === 'End' ? n - 1
      : -1;
    if (next < 0) return;
    e.preventDefault();
    e.stopPropagation();
    selectBody(VIEWER_BODIES[next]!, true);
  }
  function preload(id: BodyId) {
    preloadIdle(assetsFor(id, 'hi').map((a) => ASSETS[a].url));
  }

  /* --------------------------------- ciclo di vita --------------------------------- */

  $effect(() => {
    const s = { ...($state.snapshot(scene) as SceneState), overlay };
    handle?.update(s);
  });

  const onMotion = () => {
    motionAllowed = !(mql?.matches ?? false);
  };
  const onFs = () => (fullscreen = document.fullscreenElement === root);

  onMount(() => {
    mql?.addEventListener('change', onMotion);
    document.addEventListener('fullscreenchange', onFs);
    const unsub = subscribeTelemetry((s) => (telemetry = s));
    const unsubScenario = store.subscribe((s) => {
      const changedSite = embedded && s.site !== sc.site;
      sc = s;
      if (changedSite && s.site) revealSite(s.site);
    });
    // sito dello scenario (link da un'altra pagina): selezionato e portato al centro, senza animazione
    const wanted = body === 'moon' && sc.site ? [...def.places, ...customPlaces].find((p) => p.siteId === sc.site) : undefined;
    if (wanted) {
      selected = wanted.id;
      const c = centerOn(wanted.lat, wanted.lon);
      view = { ...view, yaw_deg: c.yaw_deg, pitch_deg: c.pitch_deg };
    }
    let ro: ResizeObserver | null = null;
    if (host && typeof ResizeObserver !== 'undefined') {
      ro = new ResizeObserver(() => {
        stageW = host!.clientWidth;
        stageH = host!.clientHeight;
      });
      ro.observe(host);
    }
    if (host) {
      stageW = host.clientWidth;
      stageH = host.clientHeight;
      handle = mountViewport(
        selectViewportFactory({ onMode: (m) => (mode = m) }),
        host,
        () => (error = 'Impossibile caricare la visualizzazione 3D. Usa la descrizione testuale.'),
      );
      handle.update({ ...($state.snapshot(scene) as SceneState), overlay });
    }
    // cielo e corpi non scelti: in coda quando il browser è libero
    preloadIdle([ASSETS[starsAsset('hi')].url]);
    return () => {
      mql?.removeEventListener('change', onMotion);
      document.removeEventListener('fullscreenchange', onFs);
      unsub();
      unsubScenario();
      snapClient.dispose();
      store.dispose();
      ro?.disconnect();
      cancelAnimationFrame(tween);
      clearTimeout(announceTimer);
      handle?.dispose();
      handle = null;
    };
  });

  /* ------------------------------------ annunci ------------------------------------ */

  function announceNow(msg: string) {
    clearTimeout(announceTimer);
    announce(msg, liveEl ?? null);
  }
  /** Annuncio breve e debounced, solo dopo azioni esplicite dell'utente. */
  function announceSoon() {
    clearTimeout(announceTimer);
    announceTimer = setTimeout(() => {
      announce(`Vista aggiornata: rotazione ${view.yaw_deg.toFixed(0)}°, inclinazione ${view.pitch_deg.toFixed(0)}°.`, liveEl ?? null);
    }, 500);
  }
  function rotate(dyaw: number, dpitch: number, speak = true) {
    cancelAnimationFrame(tween);
    view = { ...view, yaw_deg: wrapYaw(view.yaw_deg + dyaw), pitch_deg: clampPitch(view.pitch_deg + dpitch) };
    if (speak) announceSoon();
  }
  function reset() {
    view = { ...view, yaw_deg: DEFAULT_SCENE.yaw_deg, pitch_deg: DEFAULT_SCENE.pitch_deg, zoom: 1 };
    selected = null;
    announceSoon();
  }
  function toggleAuto() {
    view = { ...view, autoRotate: !view.autoRotate };
    announceSoon();
  }
  function zoomBy(f: number) {
    view = { ...view, zoom: clampZoom(view.zoom * f) };
    announceNow(`Ingrandimento ${formatNumber(view.zoom, 1)}x.`);
  }
  async function toggleFullscreen() {
    try {
      if (document.fullscreenElement) await document.exitFullscreen();
      else await root?.requestFullscreen();
    } catch {
      /* rifiutato dal browser: nessun effetto */
    }
  }

  /* ---------------- barra degli strumenti: tabindex mobile (pattern ARIA toolbar) ---------------- */

  type Action = { id: string; label: string; icon: 'left' | 'right' | 'up' | 'down' | 'reset' | 'spin'; run: () => void; pressed?: boolean };
  const actions = $derived<Action[]>([
    { id: 'left', label: 'Ruota a sinistra', icon: 'left', run: () => rotate(-STEP, 0) },
    { id: 'right', label: 'Ruota a destra', icon: 'right', run: () => rotate(STEP, 0) },
    { id: 'up', label: "Inclina verso l'alto", icon: 'up', run: () => rotate(0, -STEP) },
    { id: 'down', label: 'Inclina verso il basso', icon: 'down', run: () => rotate(0, STEP) },
    { id: 'reset', label: 'Ripristina vista', icon: 'reset', run: reset },
    ...(motionAllowed ? [{ id: 'auto', label: 'Rotazione automatica', icon: 'spin' as const, run: toggleAuto, pressed: view.autoRotate }] : []),
  ]);
  let active = $state(0);
  let toolbar: HTMLElement | undefined = $state();
  const currentTool = $derived(Math.min(active, actions.length - 1));

  function onToolbarKey(e: KeyboardEvent) {
    const n = actions.length;
    const next =
      e.key === 'ArrowRight' || e.key === 'ArrowDown' ? (currentTool + 1) % n
      : e.key === 'ArrowLeft' || e.key === 'ArrowUp' ? (currentTool - 1 + n) % n
      : e.key === 'Home' ? 0
      : e.key === 'End' ? n - 1
      : -1;
    if (next < 0) return;
    e.preventDefault();
    e.stopPropagation();
    active = next;
    toolbar?.querySelectorAll<HTMLButtonElement>('button')[next]?.focus();
  }

  /* --------------------- scena: frecce da tastiera e trascinamento --------------------- */

  function onStageKey(e: KeyboardEvent) {
    const map: Record<string, [number, number]> = {
      ArrowLeft: [-STEP, 0],
      ArrowRight: [STEP, 0],
      ArrowUp: [0, -STEP],
      ArrowDown: [0, STEP],
    };
    if (e.key === '+' || e.key === '=') {
      e.preventDefault();
      zoomBy(1.25);
      return;
    }
    if (e.key === '-') {
      e.preventDefault();
      zoomBy(0.8);
      return;
    }
    const d = map[e.key];
    if (!d) return;
    e.preventDefault();
    e.stopPropagation();
    rotate(d[0], d[1]);
  }

  let drag: { id: number; x: number; y: number; mouse: boolean } | null = null;
  function onDown(e: PointerEvent) {
    if (e.button !== 0) return;
    drag = { id: e.pointerId, x: e.clientX, y: e.clientY, mouse: e.pointerType === 'mouse' };
    (e.currentTarget as HTMLElement).setPointerCapture?.(e.pointerId);
  }
  function onMove(e: PointerEvent) {
    if (!drag || e.pointerId !== drag.id) return;
    const dx = e.clientX - drag.x;
    const dy = e.clientY - drag.y;
    drag.x = e.clientX;
    drag.y = e.clientY;
    // al tocco solo rotazione orizzontale: lo scroll verticale della pagina resta libero (touch-action: pan-y)
    rotate(dx * DRAG_DEG_PER_PX, drag.mouse ? dy * DRAG_DEG_PER_PX : 0, false);
  }
  function onUp(e: PointerEvent) {
    if (!drag || e.pointerId !== drag.id) return;
    drag = null;
    announceSoon();
  }

  // distanza Terra-Luna del momento (efemeridi) se l'istantanea c'e'; altrimenti il valore medio con la sua fonte
  const stat = $derived(
    snap
      ? { value: snap.rangeKm, unit: 'km', digits: 0, label: 'distanza Terra-Luna all’istante scelto' }
      : { ...def.keyStat, digits: def.keyStat.digits ?? 0 },
  );
  const crossLinks = $derived.by(() => {
    const t = sc.t ?? (simMs !== null ? msToT(simMs) : null);
    const site = current?.siteId ?? sc.site;
    const s: Scenario = { ...sc, site, t };
    return {
      analysis: withBase(withScenario('/analizza', s), BASE),
      lander: withBase(withScenario('/lander', s), BASE),
      compare: withBase(withScenario('/compare', s), BASE),
    };
  });
  function setStation(e: Event) {
    const v = (e.currentTarget as HTMLSelectElement).value;
    if (v === 'dsn34' || v === 'dsn18') store.set({ station: v });
  }
  function setRate(e: Event) {
    store.set({ bitrate: Number((e.currentTarget as HTMLSelectElement).value) });
  }
  const rateText = (r: number) => (r >= 1e6 ? `${r / 1e6} Mbit/s` : `${r / 1e3} kbit/s`).replace('.', ',');
  const dec1 = (v: number) => formatNumber(v, 1);
</script>

<div class="viewer tone-dark" class:tall bind:this={root} data-body={body}>
  <div class="scene-layout">
  <div class="viewer-main">
  <div class="stage-wrap">
    <!-- La scena è focalizzabile e risponde a frecce/trascinamento come scorciatoia: gli stessi comandi
         esistono come pulsanti nella barra degli strumenti, quindi il gruppo resta un "group" con istruzioni. -->
    <!-- svelte-ignore a11y_no_noninteractive_tabindex, a11y_no_noninteractive_element_interactions -->
    <div
      class="stage"
      bind:this={host}
      id="viewer-stage"
      role="group"
      tabindex="0"
      aria-roledescription="scena 3D"
      aria-label={`${def.name}. Trascina o usa le frecce per ruotare, più e meno per ingrandire.`}
      aria-describedby="stage-help scene-description"
      data-spatial-skip
      onkeydown={onStageKey}
      onpointerdown={onDown}
      onpointermove={onMove}
      onpointerup={onUp}
      onpointercancel={onUp}
    ></div>
    <p id="stage-help" class="visually-hidden">
      Con il focus sulla scena, le frecce sinistra e destra ruotano il corpo, su e giù lo inclinano; più e meno cambiano l'ingrandimento.
    </p>

    <!-- marcatori: pulsanti veri sopra il canvas -->
    <div class="markers" aria-label={`Luoghi visibili su ${def.name}`} role="group">
      {#each markers as m (m.p.id)}
        <button
          type="button"
          class="marker"
          class:is-selected={selected === m.p.id}
          class:no-label={!labelled.has(m.p.id)}
          data-kind={m.p.kind}
          data-state={m.info.state}
          data-place={m.p.id}
          style={`transform: translate(${m.at.x.toFixed(1)}px, ${m.at.y.toFixed(1)}px)`}
          aria-label={`${m.p.name}, ${latLon(m.p)}${m.info.text ? `, ${m.info.text}` : ''}`}
          aria-pressed={selected === m.p.id}
          onclick={() => goTo(m.p)}
        >
          <span class="marker-dot" aria-hidden="true"></span>
          <span class="marker-label" aria-hidden="true">{m.p.name}{m.info.text ? ` · ${m.info.text}` : ''}</span>
        </button>
      {/each}
      {#if dirOverlay && overlayLabel}
        <svg class="dir-overlay" width={stageW} height={stageH} viewBox={`0 0 ${stageW} ${stageH}`} aria-hidden="true" data-testid="dir-line" data-kind={dirOverlay.id}>
          <line class="dir-halo" x1={dirOverlay.x1} y1={dirOverlay.y1} x2={dirOverlay.x2} y2={dirOverlay.y2} />
          <line class="dir-line" class:is-back={!dirOverlay.front} x1={dirOverlay.x1} y1={dirOverlay.y1} x2={dirOverlay.x2} y2={dirOverlay.y2} />
          <polygon class="dir-head" points="0,0 -11,-5 -11,5" transform={`translate(${dirOverlay.x2} ${dirOverlay.y2}) rotate(${dirOverlay.ang})`} />
        </svg>
        <p class="dir-label" data-testid="dir-label" style={`transform: translate(${overlayLabel.x.toFixed(1)}px, ${overlayLabel.y.toFixed(1)}px)`}>
          <strong>{dirOverlay.text}</strong>
          <span>{dirOverlay.sub}</span>
        </p>
      {/if}
    </div>
    <div class="hud-tools">
      <div class="round-group" role="group" aria-label="Ingrandimento">
        <button type="button" class="round" aria-label="Ingrandisci" disabled={view.zoom >= ZOOM_MAX} onclick={() => zoomBy(1.25)}><Icon name="plus" /></button>
        <button type="button" class="round" aria-label="Riduci" disabled={view.zoom <= ZOOM_MIN} onclick={() => zoomBy(0.8)}><Icon name="minus" /></button>
      </div>
      {#if canFullscreen}
        <button type="button" class="round" aria-label={fullscreen ? 'Esci da schermo intero' : 'Schermo intero'} aria-pressed={fullscreen} onclick={toggleFullscreen}>
          <Icon name={fullscreen ? 'collapse' : 'expand'} />
        </button>
      {/if}
      <div class="toolbar" role="toolbar" aria-label="Controlli della vista" aria-orientation="vertical" tabindex="-1" bind:this={toolbar} onkeydown={onToolbarKey} data-spatial-skip>
        {#each actions as a, i (a.id)}
          <button type="button" class="round" tabindex={i === currentTool ? 0 : -1} aria-pressed={a.pressed} aria-label={a.label} title={a.label} onfocus={() => (active = i)} onclick={a.run}>
            <Icon name={a.icon} />
          </button>
        {/each}
      </div>
    </div>
  </div>
  <div class="hud-bar">
    <SkyTime belowScene bind:this={skyTime} body={skyBody} onlight={(l) => (skyLight = l)} {initialMs} externalMs={embedded ? tToMs(sc.t) : null} ontime={onTime} />
    {#if def.telemetry}
      <div class="live">
        <p class="live-pill" role="status" data-state={live ? 'ok' : telemetry.status?.kind === 'reconnecting' ? 'warn' : 'idle'}>
          {live ? 'In diretta' : telemetry.status?.kind === 'reconnecting' ? 'Collegamento perso' : 'Telemetria non collegata'}
        </p>
        <p class="observed num">
          {telemetry.last ? `Campione delle ${utcClock(telemetry.last.t_utc)} UTC` : 'In attesa del primo campione'}
        </p>
      </div>
    {:else}
      <p class="observed muted">La telemetria riguarda il sito lunare: scegli la Luna per vederla.</p>
    {/if}
  </div>
  {@render below?.()}
  </div>
    <SceneSettings>
    <div class="hud">
      <header class="hud-title">
        {#if inHub}<h2 class="hud-h"><span class="body-name">{def.name}</span><span class="visually-hidden"> nel visualizzatore 3D</span></h2>{:else}<h1 class="hud-h"><span class="body-name">{def.name}</span><span class="visually-hidden"> nel visualizzatore 3D</span></h1>{/if}
        <div class="tabs" role="tablist" aria-label="Corpo celeste" bind:this={tabs} tabindex="-1" onkeydown={onTabKey} data-spatial-skip>
          {#each VIEWER_BODIES as id (id)}
            <button
              type="button"
              role="tab"
              data-body={id}
              id={`tab-${id}`}
              aria-selected={body === id}
              aria-controls="viewer-stage"
              tabindex={body === id ? 0 : -1}
              onclick={() => selectBody(id)}
              onpointerenter={() => preload(id)}
              onfocus={() => preload(id)}
            >{BODIES[id].name}</button>
          {/each}
        </div>
      </header>

      <div class="hud-stat">
        <p class="stat">
          <span class="stat-value num" data-testid="stat-value">{formatNumber(stat.value, stat.digits ?? 0)}</span>
          <span class="stat-unit">{stat.unit}</span>
        </p>
        {#if snap}
          <p class="stat-label">{stat.label[0]!.toUpperCase() + stat.label.slice(1)}<span class="stat-source">, efemeridi NAIF DE440</span></p>
          {#if modeNow.advanced}<p class="stat-delta num" data-testid="fspl-delta">Perdita in spazio libero {fsplDeltaText(snap.fsplDeltaDb)} rispetto a {formatNumber(snap.referenceKm, 0)} km fissi</p>{/if}
        {:else}
          <p class="stat-label">{stat.label[0]!.toUpperCase() + stat.label.slice(1)}<span class="stat-source">, <a href={def.factsSource} rel="noreferrer">fonte NSSDCA</a></span></p>
        {/if}
      </div>

      <!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
      <section
        class="panel-explore"
        class:is-open={sheetOpen}
        aria-labelledby="explore-h"
        onkeydown={(e) => {
          if (e.key === 'Escape' && narrow && sheetOpen) {
            e.preventDefault();
            const panel = e.currentTarget as HTMLElement;
            sheetOpen = false;
            void tick().then(() => panel.querySelector<HTMLElement>('.sheet-toggle')?.focus());
          }
        }}
      >
        <header class="explore-head">
          <h2 id="explore-h">Esplora</h2>
          {#if narrow}
            <button type="button" class="sheet-toggle" aria-expanded={sheetOpen} aria-controls="explore-body" onclick={() => (sheetOpen = !sheetOpen)}>
              <Icon name={sheetOpen ? 'chevronDown' : 'chevronUp'} />
              <span>{sheetOpen ? 'Chiudi' : `Luoghi e dati di ${def.name}`}</span>
            </button>
          {/if}
        </header>
        <div class="explore-body" id="explore-body" hidden={narrow && !sheetOpen}>
          {#if allPlaces.length}
            {#if allPlaces.length > 6}
              <label class="search">
                <span class="visually-hidden">Cerca un luogo</span>
                <Icon name="search" />
                <input type="search" placeholder="Cerca un luogo" bind:value={query} autocomplete="off" />
              </label>
              <div class="chips" role="group" aria-label="Filtra per tipo">
                <button type="button" class="chip" aria-pressed={kind === 'all'} onclick={() => (kind = 'all')}>Tutti</button>
                {#each kinds as k (k)}
                  <button type="button" class="chip" aria-pressed={kind === k} onclick={() => (kind = k)}>{KIND_LABEL[k]}</button>
                {/each}
              </div>
            {/if}
            {#if body === 'moon'}<CustomSiteControl />{/if}
            {#if shown.length}
              <ul class="places" aria-label={body === 'earth' ? 'Complessi DSN' : 'Luoghi'}>
                {#each shown as p (p.id)}
                  {@const info = markerInfo(p)}
                  <li>
                    <button type="button" class="place" data-place={p.id} data-state={info.state} aria-pressed={selected === p.id} onclick={() => goTo(p)}>
                      <span class="place-name">{p.name}</span>
                      <span class="place-meta num">{latLon(p)}</span>
                      {#if info.text}<span class="place-state" data-state={info.state}><span class="state-glyph" aria-hidden="true"></span>{info.text}</span>{/if}
                    </button>
                  </li>
                {/each}
              </ul>
            {:else}
              <p class="empty">Nessun luogo corrisponde a “{query}”. Prova con un altro nome o scegli “Tutti”.</p>
            {/if}
            {#if current}
              <div class="detail" aria-live="polite" data-testid="place-detail">
                <p class="detail-name">{current.name}</p>
                <p class="muted">{current.note}</p>
                {#if body === 'moon'}
                  {#if selSite}
                    <p class="earth-line num" data-testid="detail-earth">{earthAngleText(selSite.earthEl)}, azimut {formatNumber(selSite.earthAz, 1)}° (parallasse e librazione)</p>
                    <p class="link-line" data-testid="detail-state">
                      Link: <strong class="place-state" data-state={selSite.state}><span class="state-glyph" aria-hidden="true"></span>{STATE_LABEL[selSite.state]}</strong>
                      {#if selSite.marginDb !== null}, margine <span class="num">{formatNumber(selSite.marginDb, 1)} dB</span> a {rateText(rate)}{/if}
                    </p>
                    <p class="muted small">{STATE_HELP[selSite.state]}.</p>
                    {#if selSite.ridgeEl !== null}
                      <p class="muted small num">Crinale dominante a {formatNumber(selSite.ridgeEl, 2)}° di elevazione{selSite.ridgeEl > selSite.earthEl ? ', sopra il centro della Terra' : ''}.</p>
                    {/if}
                    {#if selSite.demCovered}
                      <p class="muted small">Terreno: DEM LOLA (cache locale); correzione della cresta da ITU-R P.526-9, non misurata. Calcolato per {snap?.tUtc.replace('T', ' ').replace('Z', ' UTC')}.</p>
                    {/if}
                  {:else if current.siteId && snapProblem}
                    <p class="muted small">Nessuno stato del link: {snapProblem}</p>
                  {:else if current.siteId}
                    <p class="muted small">Stato del link in calcolo…</p>
                  {:else}
                    <p class="muted small" data-testid="detail-nosite">{STATE_LABEL.out_of_coverage}: questo luogo non è tra i siti dell’analisi, nessun valore stimato.</p>
                  {/if}
                {:else if selComplex && snap}
                  <p class="earth-line" data-testid="detail-moon">{moonSeenText(selComplex, snap.minElevationDeg)}, azimut {formatNumber(selComplex.moonAz, 0)}°.</p>
                  <ul class="antennas">
                    {#each selComplex.antennas as a (a.id)}
                      <li>{a.diameterM} m ({a.name}){a.verified ? '' : ': ipotesi senza fonte'}</li>
                    {/each}
                  </ul>
                {/if}
                <p class="muted small">Fonte: {current.source}</p>
                {#if body === 'moon' && current.siteId}
                  <div class="actions" data-testid="detail-actions">
                    {#if landerAvailable}
                      <a class="btn" href={crossLinks.lander} data-testid="open-lander">Apri scena lander</a>
                    {:else}
                      <button type="button" class="btn" disabled aria-disabled="true" data-testid="open-lander" title="La scena lander non è ancora disponibile">Apri scena lander <em>(in arrivo)</em></button>
                    {/if}
                    {#if selSite?.demCovered}
                      <a class="btn" href={crossLinks.analysis} data-testid="open-analysis">Analisi completa</a>
                    {:else}
                      <p class="muted small" data-testid="analysis-unavailable">Analisi completa solo per i siti coperti dal DEM.</p>
                    {/if}
                  </div>
                  <p><a class="analyze-link" href={crossLinks.compare}>Analizza in Confronto siti</a></p>
                {/if}
              </div>
            {/if}
          {:else if body === 'earth'}
            <p class="empty" data-testid="stations-empty">
              {snapProblem ?? 'Complessi DSN in caricamento…'}
            </p>
          {:else}
            <p class="empty">Per {def.name} non ci sono ancora luoghi con coordinate verificate.</p>
          {/if}

          {#if snapProblem && allPlaces.length}
            <p class="problem" role="status" data-testid="snap-problem">{snapProblem}</p>
          {/if}

          {#if snap && body === 'earth'}
            <ul class="moon-seen" data-testid="moon-seen">
              {#each snap.complexes as c (c.complex)}
                <li class:is-best={c.complex === bestComplex}>{moonSeenText(c, snap.minElevationDeg)}{c.complex === bestComplex ? ' (evidenziata)' : ''}</li>
              {/each}
            </ul>
            <p class="muted small">Coordinate: {snap.source.document}{snap.source.url ? '' : ''}. La stazione da 34 m è quella delle coordinate; quella da 18 m è un’ipotesi dello script della ricerca, senza fonte.</p>
          {/if}

          <fieldset class="scenario">
            <legend>Scenario del link</legend>
            <label>
              Stazione di terra
              <select value={sc.station} onchange={setStation} data-testid="sel-station">
                <option value="dsn34">DSN 34 m</option>
                <option value="dsn18">18 m (ipotesi)</option>
              </select>
            </label>
            <label>
              Bit-rate
              <select value={String(rate)} onchange={setRate} data-testid="sel-rate">
                {#each BITRATES as r (r)}<option value={String(r)}>{rateText(r)}</option>{/each}
              </select>
            </label>
          </fieldset>

          <section class="why" aria-labelledby="why-h" data-testid="why-grazinglink">
            <h3 id="why-h">Perché RAVEN</h3>
            <p>
              Dal polo Sud lunare la Terra sta radente all’orizzonte, tra 0,5° e 1,5°. Un crinale la nasconde o la sfiora, e la sola
              geometria («vista / non vista») non basta: ai bordi la diffrazione lascia passare parte del segnale.
            </p>
            <p>
              RAVEN calcola quel margine nel tempo, con la Terra e la librazione reali. Il globo mostra solo il contesto geometrico:
              la fisica d’onda sta in Onda 3D, nella scena lander e nell’analisi.
            </p>
          </section>

          <dl class="facts">
            {#each def.facts as f (f.label)}
              <div><dt>{f.label}</dt><dd class="num">{formatNumber(f.value, f.digits ?? 0)} {f.unit}</dd></div>
            {/each}
          </dl>
          <p class="facts-source small"><a href={def.factsSource} rel="noreferrer">Dati: NSSDCA Planetary Fact Sheet</a></p>
        </div>
      </section>

      <p class="hud-limits" data-testid="limits-line" aria-busy={snapBusy}>
        <strong>Limiti:</strong> copertura DEM solo a latitudine ≤ −85°; un solo ostacolo dominante; parametri radio ipotesi illustrative (tag I);
        Cresta: T(m,n) di ITU-R P.526-9 con lo split-step come banda; nessuna misura.
      </p>

      <p class="hud-credit">
        <span>{def.shortCredit}. {def.emissive ? 'Immagine fissa: la rotazione sposta il cielo.' : 'Trascina per ruotare.'}</span>
        <span class="mode" data-testid="viewer-mode" role="status" data-mode={mode ?? ''}>{modeLabel}</span>
      </p>
    </div>
    </SceneSettings>
  </div>

  <div class="container container--wide below">
    {#if error}<p role="alert">{error}</p>{/if}
    <section aria-labelledby="desc-h" class="desc">
      <h2 id="desc-h">Descrizione della scena</h2>
      <p id="scene-description">{description}</p>
      {#if !motionAllowed}
        <p class="muted">Rotazione automatica disattivata: il sistema richiede meno movimento.</p>
      {/if}
    </section>
    <section aria-labelledby="cred-h" class="credits">
      <h2 id="cred-h">Crediti delle immagini</h2>
      <ul>
        {#each [...assetsFor(body, 'hi'), starsAsset('hi')] as a (a)}
          <li>{ASSETS[a].credit}. {ASSETS[a].licence}. <a href={ASSETS[a].sourcePage} rel="noreferrer">Pagina della fonte</a></li>
        {/each}
      </ul>
      <p class="muted small">Rilievo lunare esagerato 3 volte per renderlo leggibile. Nessuna immagine implica l'approvazione della NASA.</p>
    </section>
  </div>
</div>

<ModelStamp />
<div class="visually-hidden" role="status" aria-live="polite" aria-atomic="true" bind:this={liveEl}></div>

<style>
  .viewer {
    container-type: inline-size;
    background: #000;
    color: var(--c-text);
    padding-bottom: var(--space-6);
    --glass: rgb(0 0 0 / 0.72);
    --glass-line: rgb(255 255 255 / 0.16);
  }
  .viewer.tall {
    --scene-stage-height: max(30rem, 74svh);
  }
  .viewer:fullscreen {
    padding: 0;
    overflow: auto;
  }
  .stage-wrap {
    position: relative;
    height: var(--scene-stage-height);
    overflow: hidden;
    isolation: isolate;
  }
  .viewer:fullscreen .stage-wrap {
    height: 100dvh;
  }
  .stage {
    position: absolute;
    inset: 0;
    cursor: grab;
    touch-action: pan-y;
  }
  .stage:active {
    cursor: grabbing;
  }
  .stage:focus-visible {
    outline-offset: -4px;
  }

  /* --------------------------------- marcatori --------------------------------- */
  .markers {
    position: absolute;
    inset: 0;
    pointer-events: none;
    z-index: 1;
  }
  .marker {
    position: absolute;
    left: 0;
    top: 0;
    min-height: 0;
    width: var(--target);
    height: var(--target);
    margin: calc(var(--target) / -2) 0 0 calc(var(--target) / -2);
    padding: 0;
    border: 0;
    border-radius: 50%;
    background: transparent;
    pointer-events: auto;
    color: var(--c-text);
    transition: none;
  }
  .marker:active {
    transform: none;
  }
  .marker-dot {
    width: 12px;
    height: 12px;
    border-radius: 50%;
    border: 1.5px solid #fff;
    background: rgb(0 0 0 / 0.55);
    box-shadow: 0 0 0 1px rgb(0 0 0 / 0.6);
  }
  .marker[data-kind='crater'] .marker-dot,
  .marker[data-kind='feature'] .marker-dot,
  .marker[data-kind='polar'] .marker-dot {
    border-style: solid;
    width: 10px;
    height: 10px;
    background: transparent;
  }
  .marker.is-selected .marker-dot {
    background: var(--c-link);
    border-color: #fff;
    width: 14px;
    height: 14px;
  }
  .marker-label {
    position: absolute;
    left: calc(50% + 12px);
    top: 50%;
    transform: translateY(-50%);
    padding: 2px 8px;
    border-radius: var(--r-inner, 6px);
    background: var(--glass);
    font-size: var(--fs-micro);
    line-height: 1.4;
    white-space: nowrap;
  }
  .marker.no-label .marker-label {
    display: none;
  }
  .marker.no-label:hover .marker-label,
  .marker.no-label:focus-visible .marker-label {
    display: block;
  }
  .marker:hover .marker-label,
  .marker:focus-visible .marker-label,
  .marker.is-selected .marker-label {
    background: #000;
    outline: 1px solid var(--glass-line);
  }

  /* ------------------------------------ HUD ------------------------------------ */
  .hud {
    max-width: 2000px;
    margin-inline: auto;
    display: grid;
    grid-template-columns: minmax(0, 1fr);
    grid-template-areas:
      'title'
      'stat'
      'bar'
      'panel'
      'limits'
      'credit';
    gap: var(--space-3) var(--space-4);
    padding: var(--space-2) 0;
  }
  .hud > * {
    pointer-events: auto;
    min-width: 0;
  }
  .hud-title {
    grid-area: title;
    align-self: start;
  }
  .hud-h {
    margin: 0 0 var(--space-3);
    font-size: 1.6rem;
    font-weight: 600;
    font-stretch: var(--wdth-display);
    letter-spacing: -0.03em;
    line-height: 1;
  }
  .tabs {
    display: inline-flex;
    padding: 3px;
    gap: 2px;
    border-radius: var(--radius-pill);
    background: var(--glass);
    border: 1px solid var(--glass-line);
  }
  .tabs:focus {
    outline: none;
  }
  [role='tab'] {
    min-height: 38px;
    padding: 0 1rem;
    border: 0;
    color: var(--c-muted);
    font-size: var(--fs-small);
  }
  [role='tab']:hover {
    color: var(--c-text);
  }
  [role='tab'][aria-selected='true'] {
    background: var(--c-text);
    color: #000;
    font-weight: 600;
  }
  .hud-stat {
    grid-area: stat;
    justify-self: start;
    text-align: start;
  }
  .stat {
    margin: 0;
    line-height: 1;
  }
  .stat-value {
    font-size: 1.5rem;
    font-weight: 300;
    letter-spacing: -0.02em;
  }
  .stat-unit {
    font-size: var(--fs-body);
    color: var(--c-muted);
    margin-left: 0.25em;
  }
  .stat-label {
    margin: var(--space-2) 0 0;
    font-size: var(--fs-small);
    color: var(--c-muted);
  }
  .stat-label a {
    color: var(--c-link);
  }
  .hud-tools {
    position: absolute;
    z-index: 3;
    inset-inline-start: var(--space-2);
    inset-block-start: var(--space-2);
    max-block-size: calc(100% - 2 * var(--space-2));
    display: flex;
    flex-direction: column;
    flex-wrap: nowrap;
    overflow-y: auto;
    gap: var(--space-2);
    align-items: center;
  }
  .round-group,
  .toolbar {
    display: flex;
    flex-shrink: 0;
    flex-direction: column;
    flex-wrap: nowrap;
    gap: var(--space-2);
  }
  .toolbar:focus {
    outline: none;
  }
  .round {
    flex: 0 0 var(--target);
    width: var(--target);
    height: var(--target);
    min-height: var(--target);
    padding: 0;
    border-radius: 50%;
    border: 1px solid var(--glass-line);
    background: var(--glass);
    color: var(--c-text);
  }
  .round:hover:not(:disabled) {
    border-color: rgb(255 255 255 / 0.42);
    background: #111;
  }
  .round:disabled {
    opacity: 0.4;
  }
  .round[aria-pressed='true'] {
    background: var(--c-text);
    color: #000;
    border-color: var(--c-text);
  }

  /* ------------------------------- pannello Esplora ------------------------------- */
  .panel-explore {
    grid-area: panel;
    align-self: start;
    max-height: 100%;
    overflow: auto;
    overscroll-behavior: contain;
    padding: var(--space-4);
    border-radius: var(--r-panel, 14px);
    background: var(--glass);
    border: 1px solid var(--glass-line);
  }
  @supports ((-webkit-backdrop-filter: blur(1px)) or (backdrop-filter: blur(1px))) {
    .panel-explore,
    .tabs,
    .hud-bar {
      -webkit-backdrop-filter: blur(18px) saturate(140%);
      backdrop-filter: blur(18px) saturate(140%);
    }
  }
  .explore-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: var(--space-3);
  }
  .explore-head h2 {
    margin: 0;
    font-size: var(--fs-h3);
    font-stretch: var(--wdth-heading);
  }
  .explore-body[hidden] {
    display: none;
  }
  .facts-source {
    margin: 0;
    color: var(--c-muted);
  }
  .explore-body {
    display: grid;
    gap: var(--space-3);
    margin-top: var(--space-3);
  }
  .search {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    padding: 0 var(--space-3);
    border-radius: var(--radius-pill);
    border: 1px solid var(--glass-line);
    background: #000;
    color: var(--c-muted);
  }
  .search:focus-within {
    outline: 2px solid var(--c-focus);
    outline-offset: 2px;
  }
  .search input {
    flex: 1;
    min-width: 0;
    min-height: var(--target);
    border: 0;
    background: transparent;
    color: var(--c-text);
    font: inherit;
    font-size: var(--fs-small);
    outline: none;
  }
  .chips {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-2);
  }
  .chip {
    min-height: 36px;
    padding: 0 0.85rem;
    border-color: var(--glass-line);
    color: var(--c-text);
    font-size: var(--fs-small);
  }
  .chip[aria-pressed='true'] {
    background: var(--c-text);
    border-color: var(--c-text);
    color: #000;
  }
  .chip:hover:not(:disabled) {
    border-color: rgb(255 255 255 / 0.42);
  }
  .chip:disabled {
    opacity: 0.4;
  }
  .places {
    list-style: none;
    margin: 0;
    padding: 0;
    border-top: 1px solid var(--glass-line);
  }
  .place {
    display: grid;
    justify-items: start;
    justify-content: stretch;
    gap: 2px;
    width: 100%;
    min-height: 52px;
    padding: var(--space-2) 0;
    border: 0;
    border-bottom: 1px solid var(--glass-line);
    border-radius: 0;
    background: transparent;
    color: var(--c-text);
    text-align: left;
  }
  .place:hover .place-name {
    color: var(--c-link);
  }
  .place[aria-pressed='true'] {
    background: transparent;
    color: var(--c-text);
  }
  .place[aria-pressed='true'] .place-name::before {
    content: '';
    display: inline-block;
    width: 8px;
    height: 8px;
    margin-right: 8px;
    border-radius: 50%;
    background: var(--c-link);
    vertical-align: middle;
  }
  .place-name {
    font-size: var(--fs-small);
    font-weight: 600;
  }
  .place-meta {
    font-size: var(--fs-micro);
    color: var(--c-muted);
  }
  .empty {
    margin: 0;
    font-size: var(--fs-small);
    color: var(--c-muted);
    text-wrap: pretty;
  }
  .detail p {
    margin: 0;
    font-size: var(--fs-small);
  }
  .analyze-link {
    display: inline-flex;
    align-items: center;
    min-height: var(--target);
    color: var(--c-link);
  }
  .detail-name {
    font-weight: 600;
  }
  .facts {
    display: grid;
    margin: 0;
    border-top: 1px solid var(--glass-line);
  }
  .facts div {
    display: flex;
    justify-content: space-between;
    gap: var(--space-3);
    padding: var(--space-2) 0;
    border-bottom: 1px solid var(--glass-line);
    font-size: var(--fs-small);
  }
  .facts dt {
    color: var(--c-muted);
  }
  .facts dd {
    margin: 0;
  }

  /* --------------------------------- barra in basso --------------------------------- */
  .hud-bar {
    position: relative;
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: var(--space-1) var(--space-3);
    padding: var(--space-1) var(--space-2);
    border-radius: var(--r-panel, 14px);
    background: var(--glass);
    border: 1px solid var(--glass-line);
  }
  .live {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: var(--space-2) var(--space-3);
  }
  .live-pill {
    display: inline-flex;
    align-items: center;
    gap: var(--space-2);
    margin: 0;
    font-size: var(--fs-small);
    font-weight: 600;
  }
  .live-pill::before {
    content: '';
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: var(--c-control);
  }
  .live-pill[data-state='ok']::before {
    background: var(--c-success);
    box-shadow: 0 0 0 3px rgb(48 209 88 / 0.25);
  }
  .live-pill[data-state='warn']::before {
    background: var(--c-power);
  }
  .observed {
    margin: 0;
    font-size: var(--fs-small);
    color: var(--c-muted);
  }
  .hud-credit {
    grid-area: credit;
    display: flex;
    flex-wrap: wrap;
    justify-content: space-between;
    gap: var(--space-1) var(--space-4);
    margin: 0;
    padding: 2px 6px;
    font-size: var(--fs-micro);
    color: var(--c-muted);
    background: rgb(0 0 0 / 0.6);
    border-radius: var(--r-inner, 6px);
    justify-self: start;
  }
  .mode {
    color: var(--c-muted);
  }

  /* ------------------------------- sotto il palco ------------------------------- */
  .below {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(min(100%, 420px), 1fr));
    gap: var(--space-5);
    padding-top: var(--space-5);
  }
  .desc h2,
  .credits h2 {
    font-size: var(--fs-h3);
    font-stretch: 100%;
  }
  #scene-description {
    color: var(--c-muted);
    max-width: var(--measure);
  }
  .credits ul {
    margin: 0;
    padding-left: 1.1em;
    color: var(--c-muted);
    font-size: var(--fs-small);
  }
  .credits li + li {
    margin-top: var(--space-2);
  }

  /* ------------------------ RAVEN: stati, linee, pannelli ------------------------ */
  .hud-limits {
    grid-area: limits;
    margin: 0;
    padding: 4px 10px;
    font-size: var(--fs-micro);
    line-height: 1.4;
    color: var(--c-text);
    background: var(--glass);
    border: 1px solid var(--glass-line);
    border-radius: var(--r-inner, 6px);
  }
  .dir-overlay {
    position: absolute;
    inset: 0;
    pointer-events: none;
    overflow: visible;
  }
  .dir-halo {
    stroke: #000;
    stroke-width: 6;
    stroke-linecap: round;
    opacity: 0.7;
  }
  .dir-line {
    stroke: #fff;
    stroke-width: 2.5;
    stroke-linecap: round;
  }
  .dir-line.is-back {
    stroke-dasharray: 6 5;
  }
  .dir-head {
    fill: #fff;
    stroke: #000;
    stroke-width: 1;
  }
  .dir-label {
    position: absolute;
    left: 0;
    top: 0;
    z-index: 1;
    display: grid;
    gap: 0;
    width: 182px;
    margin: 0;
    padding: 4px 8px;
    border-radius: var(--r-inner, 6px);
    background: #000;
    outline: 1px solid var(--glass-line);
    font-size: var(--fs-small);
    line-height: 1.3;
    pointer-events: none;
  }
  .dir-label span {
    font-size: var(--fs-micro);
    color: var(--c-muted);
  }
  /* stato del link: colore + forma + testo (mai solo il colore) */
  .marker[data-state='open'] .marker-dot,
  .marker[data-state='sees'] .marker-dot,
  .marker[data-state='sees-best'] .marker-dot {
    background: var(--c-success);
  }
  .marker[data-state='transition'] .marker-dot {
    background: var(--c-power);
    border-radius: 2px;
    transform: rotate(45deg);
  }
  .marker[data-state='blocked'] .marker-dot {
    background: var(--c-danger);
    border-radius: 0;
  }
  .marker[data-state='out_of_coverage'] .marker-dot,
  .marker[data-state='unavailable'] .marker-dot,
  .marker[data-state='unknown'] .marker-dot,
  .marker[data-state='nomoon'] .marker-dot {
    background: transparent;
    border-style: dashed;
    border-color: var(--c-muted);
  }
  .marker[data-state='sees-best'] .marker-dot {
    width: 16px;
    height: 16px;
    box-shadow: 0 0 0 3px rgb(48 209 88 / 0.35);
  }
  .marker.is-selected .marker-dot {
    outline: 2px solid var(--c-link);
    outline-offset: 2px;
  }
  .place-state {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    font-size: var(--fs-micro);
    color: var(--c-text);
  }
  .state-glyph {
    display: inline-block;
    width: 9px;
    height: 9px;
    border-radius: 50%;
    border: 1.5px dashed var(--c-muted);
  }
  .place-state[data-state='open'] .state-glyph,
  .place-state[data-state='sees'] .state-glyph,
  .place-state[data-state='sees-best'] .state-glyph {
    border: 0;
    background: var(--c-success);
  }
  .place-state[data-state='transition'] .state-glyph {
    border: 0;
    background: var(--c-power);
    border-radius: 1px;
    transform: rotate(45deg);
  }
  .place-state[data-state='blocked'] .state-glyph {
    border: 0;
    background: var(--c-danger);
    border-radius: 0;
  }
  .stat-delta {
    margin: var(--space-1) 0 0;
    font-size: var(--fs-micro);
    color: var(--c-muted);
  }
  .earth-line,
  .link-line {
    margin: 0;
  }
  .actions {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-2);
    margin-top: var(--space-2);
  }
  .actions .btn {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    min-height: var(--target);
    padding: 0 1rem;
    border: 1px solid var(--glass-line);
    border-radius: var(--radius-pill);
    background: transparent;
    color: var(--c-text);
    font-size: var(--fs-small);
    text-decoration: none;
  }
  .actions a.btn {
    background: var(--c-text);
    color: #000;
    font-weight: 600;
  }
  .actions .btn:disabled {
    color: var(--c-muted);
    border-style: dashed;
  }
  .actions .btn em {
    margin-left: 0.3em;
    font-style: normal;
  }
  .antennas,
  .moon-seen {
    margin: 0;
    padding-left: 1.1em;
    font-size: var(--fs-small);
  }
  .moon-seen .is-best {
    font-weight: 600;
  }
  .scenario {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-2) var(--space-3);
    margin: 0;
    padding: var(--space-2) 0 0;
    border: 0;
    border-top: 1px solid var(--glass-line);
  }
  .scenario legend {
    padding: 0;
    font-size: var(--fs-small);
    font-weight: 600;
  }
  .scenario label {
    display: grid;
    gap: 2px;
    font-size: var(--fs-micro);
    color: var(--c-muted);
  }
  .scenario select {
    min-height: var(--target);
    padding: 0 0.5rem;
    border: 1px solid var(--glass-line);
    border-radius: var(--r-inner, 6px);
    background: #000;
    color: var(--c-text);
    font: inherit;
    font-size: var(--fs-small);
  }
  .why {
    border-top: 1px solid var(--glass-line);
    padding-top: var(--space-2);
  }
  .why h3 {
    margin: 0 0 var(--space-1);
    font-size: var(--fs-small);
  }
  .why p {
    margin: 0 0 var(--space-1);
    font-size: var(--fs-small);
    color: var(--c-muted);
  }
  .problem {
    margin: 0;
    font-size: var(--fs-small);
    color: var(--c-power);
  }

  /* --------------------------- telefono e tablet stretto --------------------------- */
  @container (max-width: 833px) {
    .hud {
      grid-template-columns: minmax(0, 1fr);
      grid-template-areas:
        'title'
        'stat'
        'bar'
        'panel'
        'limits'
        'credit';
      padding-bottom: max(var(--space-2), env(safe-area-inset-bottom));
      gap: var(--space-2);
    }
    .hud-h {
      margin-bottom: var(--space-2);
    }
    .hud-stat {
      align-self: start;
      max-width: 13.5rem;
    }
    .stat-value {
      font-size: 1.5rem;
    }
    .stat-label {
      font-size: var(--fs-micro);
    }
    .stat-source {
      display: none;
    }
    .hud-tools {
      gap: var(--space-2);
    }
    .panel-explore {
      padding: var(--space-2) var(--space-3);
    }
    .panel-explore:not(.is-open) .explore-head h2 {
      position: absolute;
      width: 1px;
      height: 1px;
      overflow: hidden;
      clip-path: inset(50%);
    }
    .sheet-toggle {
      width: 100%;
      justify-content: flex-start;
      border: 0;
      color: var(--c-text);
      font-size: var(--fs-small);
      padding: 0;
    }
    .hud-bar {
      padding: var(--space-1) var(--space-3);
    }
    .hud-credit {
      font-size: 0.6875rem;
    }
  }
  /* telefono in orizzontale: pannello e barra si comprimono */
  @media (max-height: 500px) and (orientation: landscape) {
    .stage-wrap {
      height: max(360px, 100svh);
    }
    .hud-h {
      font-size: 2rem;
    }
  }
  @media (pointer: coarse) {
    .chip,
    [role='tab'] {
      min-height: var(--target);
    }
  }
  @media (prefers-reduced-motion: no-preference) {
    .panel-explore {
      transition: max-height var(--dur-ui) var(--ease-out);
    }
  }
</style>
