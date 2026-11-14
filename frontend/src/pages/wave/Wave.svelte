<!-- SPDX-License-Identifier: Apache-2.0 -->
<!--
  Onda 3D: superficie dell'intensità |E|^2 di un'onda piana dopo un crinale (split-step di Fresnel, API /api/raven/wave),
  orbitabile con mouse, tocco e tastiera; un cursore sposta il piano della sezione e aggiorna il grafico 2D con la curva
  esatta del bordo a lama. WebGL con ripiego Canvas 2D scelto come nel visualizzatore.
-->
<script lang="ts">
  import SceneSettings from '../../components/ui/SceneSettings.svelte';
  import { onMount, onDestroy, tick, untrack } from 'svelte';
  import SubNav from '../../components/ui/SubNav.svelte';
  import Callout from '../../components/ui/Callout.svelte';
  import ChartBox, { type Spec as ChartSpec } from '../grazinglink/ChartBox.svelte';
  import ExportBar from '../grazinglink/ExportBar.svelte';
  import { setPageContext, clearPageContext } from '../../shell/pageContext.svelte';
  import { announce } from '../../shell/a11y';
  import { sanitizeParams } from '../chat/assistant';
  import { mountViewport, type ViewportHandle } from '../../viewports/port';
  import { detectQuality } from '../../viewports/quality';
  import type { ViewportMode } from '../../viewports/select';
  import { waveViewportFactory } from './waveViewport';
  import {
    BANDS,
    buildUrl,
    clampCursor,
    createRequester,
    cursorRange,
    DEFAULT_FORM,
    initialForm,
    flattenGrid,
    fmt,
    gridCsv,
    gridJson,
    lambdaOf,
    PRESETS,
    RES_HI,
    RES_LO,
    sectionAt,
    sectionCsv,
    sectionJson,
    sectionStats,
    sizeText,
    validateForm,
    warningText,
    zTopOf,
    type Requester,
    type WaveForm,
    type WaveOutcome,
    type WaveResult,
    type WaveSection,
  } from './wave';
  import { EMPTY_SCENE, legendGradient, orbit, resetCamera, zoomBy, type WaveScene } from './surface';
  import { modeNow } from '../../shell/modeState.svelte';
  import { getWaveHandoff } from '../simula/handoff';
  let { embedded = false }: { embedded?: boolean } = $props();

  const TABS = [
    { id: 'section', label: 'Sezione 2D' },
    { id: 'table', label: 'Tabella' },
    { id: 'meta', label: 'Parametri e avvisi' },
    { id: 'about', label: 'Cosa mostra' },
  ] as const;
  type TabId = (typeof TABS)[number]['id'];

  const STEP_DEG = 8 * (Math.PI / 180);
  const DRAG_RAD_PER_PX = 0.008;
  const PLAY_SECONDS = 14;
  const quality = detectQuality();
  const res = quality.tier === 'lo' ? RES_LO : RES_HI;

  // valori iniziali: quelli della scena di Simula se la scheda è aperta da lì, altrimenti i predefiniti
  const startForm = initialForm(getWaveHandoff());
  let form = $state<WaveForm>({ ...startForm });
  let result = $state.raw<WaveResult | null>(null);
  let loading = $state(true);
  let error = $state('');
  let errorKind = $state('');
  let cursor = $state(0);
  let tab = $state<TabId>('section');
  let mode = $state<ViewportMode | null>(null);
  let viewError = $state('');
  let playing = $state(false);
  let reduced = $state(false);
  let drawn = $state(false);
  let host: HTMLElement | undefined = $state();
  let liveEl: HTMLElement | undefined = $state();
  let handle: ViewportHandle | null = null;
  let requester: Requester | null = null;
  let lastUrl = '';
  let pendingForm: WaveForm = { ...startForm };
  let resultForm: WaveForm | null = null;
  let secReq: Requester | null = null;
  let apiSec = $state.raw<WaveSection | null>(null);
  let announceTimer: ReturnType<typeof setTimeout> | undefined;
  let raf = 0;
  let mql: MediaQueryList | null = null;

  const scene: WaveScene = { ...EMPTY_SCENE(), tier: quality.tier };

  const errors = $derived(validateForm(form));
  const valid = $derived(Object.keys(errors).length === 0);
  const range = $derived(result ? cursorRange(result) : ([0, 1] as [number, number]));
  const section = $derived(result ? sectionAt(result, cursor, apiSec) : null);
  const stats = $derived(section ? sectionStats(section) : null);
  const lambdaShown = $derived(form.spec === 'frequency' ? (form.frequencyGhz ? lambdaOf(form.frequencyGhz) : null) : form.wavelengthM);
  const freqShown = $derived(form.spec === 'wavelength' ? (form.wavelengthM ? 299792458 / form.wavelengthM / 1e9 : null) : form.frequencyGhz);
  const warnings = $derived((result?.meta.warnings ?? []).map(warningText));
  const tableStride = $derived(section ? Math.max(1, Math.ceil(section.y.length / 80)) : 1);
  const series: ChartSpec[] = [
    { label: 'Simulazione (split-step)', token: '--c-uplink' },
    { label: 'Bordo a lama esatto', token: '--c-power', dash: [8, 5] },
  ];
  const gradient = legendGradient();
  const zTop = $derived(result ? scene.zTop : 1.2);

  /* ------------------------------------------ richieste ------------------------------------------ */

  function onOutcome(o: WaveOutcome) {
    loading = false;
    if (!o.ok) {
      error = o.message;
      errorKind = o.kind;
      lastUrl = ''; // consente di ripetere la stessa richiesta
      return;
    }
    error = '';
    resultForm = pendingForm;
    apiSec = null;
    errorKind = '';
    const atEnd = !result || cursor >= range[1] - 1e-6;
    const g = flattenGrid(o.data.intensity, scene.grid.length === o.data.x_m.length * o.data.y_m.length ? scene.grid : undefined);
    scene.grid = g;
    scene.nx = o.data.x_m.length;
    scene.ny = o.data.y_m.length;
    scene.xs = o.data.x_m;
    scene.zTop = zTopOf(g);
    scene.geom++;
    const next = atEnd ? o.data.x_m[o.data.x_m.length - 1]! : clampCursor(o.data, cursor);
    result = o.data;
    cursor = next;
    scene.cursor = next;
    handle?.update(scene);
    markDrawn();
  }

  function request(immediate: boolean) {
    if (!valid || !requester) return;
    const url = buildUrl(form, res);
    if (url === lastUrl) return;
    lastUrl = url;
    pendingForm = { ...$state.snapshot(form) };
    if (immediate) requester.now(url);
    else requester.schedule(url);
  }

  // ogni modifica dei campi valida riprogramma la richiesta (debounce); la prima parte subito
  $effect(() => {
    if (!valid) return;
    const url = buildUrl(form, res);
    untrack(() => {
      if (url !== lastUrl) request(false);
    });
  });

  function applyPreset(radius: number) {
    form.radiusM = radius;
    request(true);
  }
  function applyBand(ghz: number) {
    form.spec = 'frequency';
    form.frequencyGhz = ghz;
    form.wavelengthM = Math.round(lambdaOf(ghz) * 1e5) / 1e5;
    request(true);
  }
  function retry() {
    lastUrl = '';
    request(true);
  }

  function markDrawn() {
    void tick().then(() => requestAnimationFrame(() => requestAnimationFrame(() => (drawn = !!result))));
  }

  /* ------------------------------------------- vita ------------------------------------------- */

  onMount(() => {
    mql = typeof matchMedia === 'function' ? matchMedia('(prefers-reduced-motion: reduce)') : null;
    reduced = mql?.matches ?? false;
    const onMotion = () => {
      reduced = mql?.matches ?? false;
      if (reduced) playing = false;
    };
    mql?.addEventListener('change', onMotion);
    requester = createRequester(fetch, { onStart: () => (loading = true), onResult: onOutcome });
    secReq = createRequester(fetch, { onStart: () => {}, onResult: (o) => { if (o.ok) apiSec = o.data.section; } }, 250);
    if (host) {
      handle = mountViewport(waveViewportFactory((m) => (mode = m)), host, () => (viewError = 'Impossibile caricare la visualizzazione 3D. Usa la sezione 2D e la tabella.'));
      handle.update(scene);
    }
    if (valid) {
      lastUrl = buildUrl(form, res);
      requester.now(lastUrl);
    }
    return () => mql?.removeEventListener('change', onMotion);
  });
  onDestroy(() => {
    requester?.cancel();
    secReq?.cancel();
    cancelAnimationFrame(raf);
    clearTimeout(announceTimer);
    handle?.dispose();
    handle = null;
    if (!embedded) clearPageContext();
  });

  // il cursore sposta il piano della sezione
  $effect(() => {
    const c = cursor;
    untrack(() => {
      scene.cursor = c;
      handle?.update(scene);
    });
  });

  // sezione esatta alla distanza del cursore: richiesta dopo una pausa (non durante il trascinamento o l'animazione)
  $effect(() => {
    const c = cursor;
    const r = result;
    untrack(() => {
      if (!r || !resultForm || !secReq) return;
      const xe = r.x_m[r.x_m.length - 1]!;
      if (Math.abs(c - xe) < 1e-6 || (apiSec && Math.abs(apiSec.x_m - c) < 0.5)) secReq.cancel();
      else secReq.schedule(buildUrl({ ...resultForm, distanceM: Math.round(c) }, res));
    });
  });

  $effect(() => {
    if (embedded) return;
    setPageContext({
      params: sanitizeParams({
        frequenza_ghz: form.frequencyGhz ?? undefined,
        lunghezza_onda_m: form.wavelengthM ?? undefined,
        raggio_cresta_m: form.radiusM ?? undefined,
        distanza_m: form.distanceM ?? undefined,
        cursore_m: Math.round(cursor),
        scheda: tab,
      }),
    });
  });

  /* ------------------------------------------ animazione ------------------------------------------ */

  function togglePlay() {
    if (reduced || !result) return;
    playing = !playing;
  }
  $effect(() => {
    if (!playing) return;
    let last = performance.now();
    const loop = (t: number) => {
      const [a, b] = range;
      const dt = Math.min(0.1, (t - last) / 1000);
      last = t;
      let c = cursor + ((b - a) / PLAY_SECONDS) * dt;
      if (c >= b) c = a;
      cursor = c;
      raf = requestAnimationFrame(loop);
    };
    raf = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(raf);
  });

  /* ------------------------------------ camera: puntatore e tastiera ------------------------------------ */

  function say(msg: string) {
    clearTimeout(announceTimer);
    announceTimer = setTimeout(() => announce(msg, liveEl ?? null), 450);
  }
  function viewChanged() {
    handle?.update(scene);
    say(`Vista: rotazione ${Math.round((scene.camera.yaw * 180) / Math.PI)}°, inclinazione ${Math.round((scene.camera.pitch * 180) / Math.PI)}°, ingrandimento ${fmt(scene.camera.zoom, 1)}x.`);
  }
  const rotate = (dy: number, dp: number) => (orbit(scene.camera, dy, dp), viewChanged());
  const zoom = (f: number) => (zoomBy(scene.camera, f), viewChanged());
  const reset = () => (resetCamera(scene.camera), viewChanged());

  function stepCursor(dir: number) {
    const [a, b] = range;
    cursor = Math.min(b, Math.max(a, Math.round(cursor) + dir * Math.max(1, Math.round((b - a) / 50))));
    say(`Distanza della sezione ${Math.round(cursor)} metri.`);
  }

  function onStageKey(e: KeyboardEvent) {
    const k = e.key;
    const fine = e.shiftKey ? 0.4 : 1;
    if (k === 'ArrowLeft') rotate(-STEP_DEG * fine, 0);
    else if (k === 'ArrowRight') rotate(STEP_DEG * fine, 0);
    else if (k === 'ArrowUp') rotate(0, STEP_DEG * fine);
    else if (k === 'ArrowDown') rotate(0, -STEP_DEG * fine);
    else if (k === '+' || k === '=') zoom(1.2);
    else if (k === '-' || k === '_') zoom(1 / 1.2);
    else if (k === '0' || k === 'Home') reset();
    else if (k === ']' || k === 'PageDown') stepCursor(1);
    else if (k === '[' || k === 'PageUp') stepCursor(-1);
    else return;
    e.preventDefault();
    e.stopPropagation();
  }

  const pts = new Map<number, { x: number; y: number; mouse: boolean }>();
  let pinch = 0;
  function onDown(e: PointerEvent) {
    if (e.pointerType === 'mouse' && e.button !== 0) return;
    pts.set(e.pointerId, { x: e.clientX, y: e.clientY, mouse: e.pointerType === 'mouse' });
    (e.currentTarget as HTMLElement).setPointerCapture?.(e.pointerId);
    if (pts.size === 2) pinch = pinchDist();
  }
  function pinchDist(): number {
    const it = pts.values();
    const a = it.next().value;
    const b = it.next().value;
    return a && b ? Math.hypot(a.x - b.x, a.y - b.y) : 0;
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
      if (pinch > 0 && d > 0) zoomBy(scene.camera, d / pinch);
      pinch = d;
      handle?.update(scene);
      return;
    }
    // al tocco solo rotazione orizzontale: lo scroll verticale della pagina resta libero (touch-action: pan-y)
    orbit(scene.camera, dx * DRAG_RAD_PER_PX, p.mouse ? dy * DRAG_RAD_PER_PX : 0);
    handle?.update(scene);
  }
  function onUp(e: PointerEvent) {
    if (!pts.delete(e.pointerId)) return;
    pinch = 0;
    viewChanged();
  }
  function onWheel(e: WheelEvent) {
    if (!e.ctrlKey && !e.metaKey) return; // la rotellina semplice fa scorrere la pagina
    e.preventDefault();
    zoomBy(scene.camera, Math.exp(-e.deltaY * 0.01));
    handle?.update(scene);
  }

  /* ---------------------------------------------- schede ---------------------------------------------- */

  /**
   * Learning | Avanzato: stessa superficie e stessi numeri. Learning tiene i preset della cresta, il raggio e il cursore
   * della distanza con nomi semplici e le schede "Il segnale a questa distanza" e "Cosa mostra"; banda, frequenza,
   * finestra, tabella e parametri sono in Avanzato (i valori restano quelli scelti). Chiavi stabili (i18n in arrivo).
   */
  const STR = {
    learn: 'come si comporta l’onda radio subito dopo il crinale: in basso è in ombra e si indebolisce piano, in alto oscilla. Più è alta la superficie, più forte è il segnale.',
    introSimple:
      'Il segnale radio è un’onda: quando sfiora la cima di un crinale si piega un po’ verso il basso (diffrazione). Per questo dietro il crinale non c’è un buio netto ma un’ombra che sfuma.',
    radius: 'Quanto è arrotondata la cima (m)',
    tabs: { section: 'Il segnale a questa distanza', table: 'Tabella', meta: 'Parametri e avvisi', about: 'Cosa mostra' } as Record<TabId, string>,
  } as const;
  const LEARN_TABS: readonly TabId[] = ['section', 'about'];
  const adv = $derived(modeNow.advanced);
  const visibleTabs = $derived(adv ? TABS : TABS.filter((t) => LEARN_TABS.includes(t.id)));
  const shown = $derived.by<TabId>(() => (visibleTabs.some((t) => t.id === tab) ? tab : 'section'));

  function onTabKey(e: KeyboardEvent) {
    const i = visibleTabs.findIndex((t) => t.id === shown);
    const next = e.key === 'ArrowRight' ? i + 1 : e.key === 'ArrowLeft' ? i - 1 : e.key === 'Home' ? 0 : e.key === 'End' ? visibleTabs.length - 1 : null;
    if (next === null) return;
    e.preventDefault();
    const t = visibleTabs[(next + visibleTabs.length) % visibleTabs.length]!;
    tab = t.id;
    void tick().then(() => document.getElementById(`wtab-${t.id}`)?.focus());
  }

  const MODE_LABEL: Record<string, string> = {
    webgl: 'Rendering WebGL',
    canvas2d: 'Modalità compatibile (senza WebGL)',
    none: 'Grafica 3D non disponibile',
  };
</script>

{#if !embedded}<SubNav title="Onda 3D" learn={STR.learn} />{/if}

<div class="workspace tile tile--alt">
  <div class:container={!embedded} class:container--wide={!embedded}>
    {#snippet setup()}
    <Callout title="L’onda dopo il crinale: perché l’intensità oscilla" id="intro">
      {#if !adv}<p>{STR.introSimple}</p>{:else}
      <p>
        Un’onda piana che sfiora un crinale non si ferma in una linea netta: dietro lo spigolo l’intensità <strong>cala dolcemente nell’ombra</strong>
        e, sopra la linea di vista, <strong>oscilla</strong> (frange di Fresnel). La superficie mostra l’intensità relativa |E|² in funzione della distanza dal
        crinale e della quota. Muovi il cursore per tagliare la superficie e confrontare la sezione con il bordo a lama esatto.
      </p>
      <p class="small">
        Simulazione <strong>scalare e parassiale</strong> (split-step di Fresnel con FFT): un solo crinale, onda piana, nessun regolite. I parametri sono illustrativi.
      </p>{/if}
    </Callout>

    <form class="panel setup" onsubmit={(e) => (e.preventDefault(), request(true))} novalidate aria-labelledby="setup-h">
      <h2 id="setup-h">Scenario</h2>
      <div class="presets" role="group" aria-label="Preset della cresta">
        {#each PRESETS as p (p.id)}
          <button type="button" aria-pressed={form.radiusM === p.radiusM} onclick={() => applyPreset(p.radiusM)}>{p.label}</button>
        {/each}
      </div>
      {#if adv}
      <div class="presets" role="group" aria-label="Preset della banda">
        {#each BANDS as b (b.id)}
          <button type="button" aria-pressed={form.spec === 'frequency' && form.frequencyGhz === b.ghz} onclick={() => applyBand(b.ghz)}>{b.label}</button>
        {/each}
      </div>
      {/if}
      <div class="grid">
        {#if adv}
        <fieldset class="field spec">
          <legend>Si specifica</legend>
          <label class="check"><input type="radio" name="spec" value="frequency" bind:group={form.spec} /> Frequenza</label>
          <label class="check"><input type="radio" name="spec" value="wavelength" bind:group={form.spec} /> Lunghezza d’onda</label>
        </fieldset>
        {#if form.spec === 'frequency'}
          <p class="field">
            <label for="f-freq">Frequenza (GHz)</label>
            <input id="f-freq" type="number" step="any" inputmode="decimal" bind:value={form.frequencyGhz} aria-invalid={errors.frequencyGhz ? 'true' : undefined} aria-describedby="f-freq-hint{errors.frequencyGhz ? ' f-freq-err' : ''}" />
            <span id="f-freq-hint" class="hint">{lambdaShown ? `λ = ${fmt(lambdaShown, 4)} m` : ''}</span>
            {#if errors.frequencyGhz}<span id="f-freq-err" class="field-error">{errors.frequencyGhz}</span>{/if}
          </p>
        {:else}
          <p class="field">
            <label for="f-lambda">Lunghezza d’onda (m)</label>
            <input id="f-lambda" type="number" step="any" inputmode="decimal" bind:value={form.wavelengthM} aria-invalid={errors.wavelengthM ? 'true' : undefined} aria-describedby="f-lambda-hint{errors.wavelengthM ? ' f-lambda-err' : ''}" />
            <span id="f-lambda-hint" class="hint">{freqShown ? `f = ${fmt(freqShown, 3)} GHz` : ''}</span>
            {#if errors.wavelengthM}<span id="f-lambda-err" class="field-error">{errors.wavelengthM}</span>{/if}
          </p>
        {/if}
        {/if}
        <p class="field">
          <label for="f-radius">{adv ? 'Raggio della cresta (m)' : STR.radius}</label>
          <input id="f-radius" type="number" step="any" inputmode="decimal" bind:value={form.radiusM} aria-invalid={errors.radiusM ? 'true' : undefined} aria-describedby="f-radius-hint{errors.radiusM ? ' f-radius-err' : ''}" />
          <span id="f-radius-hint" class="hint">0 = bordo a lama; fino a 400 m</span>
          {#if errors.radiusM}<span id="f-radius-err" class="field-error">{errors.radiusM}</span>{/if}
        </p>
        {#if adv}
        <p class="field">
          <label for="f-distance">Distanza massima (m)</label>
          <input id="f-distance" type="number" step="any" inputmode="decimal" bind:value={form.distanceM} aria-invalid={errors.distanceM ? 'true' : undefined} aria-describedby="f-distance-hint{errors.distanceM ? ' f-distance-err' : ''}" />
          <span id="f-distance-hint" class="hint">dal crinale, da 100 a 5000 m</span>
          {#if errors.distanceM}<span id="f-distance-err" class="field-error">{errors.distanceM}</span>{/if}
        </p>
        <p class="field">
          <label for="f-window">Finestra verticale ± (m)</label>
          <input id="f-window" type="number" step="any" inputmode="decimal" bind:value={form.halfWindowM} aria-invalid={errors.halfWindowM ? 'true' : undefined} aria-describedby="f-window-hint{errors.halfWindowM ? ' f-window-err' : ''}" />
          <span id="f-window-hint" class="hint">quota da −h a +h sulla linea di vista</span>
          {#if errors.halfWindowM}<span id="f-window-err" class="field-error">{errors.halfWindowM}</span>{/if}
        </p>
        {/if}
      </div>
      <p class="hint">Le modifiche si applicano da sole dopo una breve pausa; i preset subito.</p>
    </form>

    <p class="status" role="status" data-testid="wave-status">
      {#if loading}{result ? 'Aggiornamento della superficie...' : 'Calcolo della superficie...'}{:else if result}Superficie aggiornata: {result.meta.grid_shape[0]} × {result.meta.grid_shape[1]} punti.{/if}
    </p>
    {#if error}
      <div role="alert" class="notice" data-kind={errorKind} data-testid="wave-error">
        <p>{error}</p>
        <p><button type="button" onclick={retry}>Riprova</button></p>
      </div>
    {/if}
    {#if warnings.length}
      <ul class="notice warn" data-testid="wave-warnings" aria-label="Avvisi del simulatore">
        {#each warnings as w (w)}<li>{w}</li>{/each}
      </ul>
    {/if}
    {/snippet}

    <div class="scene-layout">
    <section class="figure tone-dark" aria-labelledby="fig-h">
      <h2 id="fig-h" class="visually-hidden">Superficie 3D dell’intensità</h2>
      <!-- La scena è focalizzabile e risponde a frecce e trascinamento; gli stessi comandi esistono come pulsanti. -->
      <!-- svelte-ignore a11y_no_noninteractive_tabindex, a11y_no_noninteractive_element_interactions -->
      <div
        class="stage"
        bind:this={host}
        id="wave-stage"
        role="group"
        tabindex="0"
        aria-roledescription="grafico 3D"
        aria-label="Superficie dell’intensità dopo il crinale. Trascina o usa le frecce per ruotare e inclinare, più e meno per ingrandire, parentesi quadre per spostare la sezione."
        aria-describedby="wave-help wave-desc"
        aria-busy={loading}
        data-spatial-skip
        data-ready={drawn ? '1' : undefined}
        onkeydown={onStageKey}
        onpointerdown={onDown}
        onpointermove={onMove}
        onpointerup={onUp}
        onpointercancel={onUp}
        onwheel={onWheel}
      ></div>
      <p id="wave-help" class="visually-hidden">
        Con il focus sul grafico: frecce per ruotare e inclinare, più e meno per ingrandire, zero per ripristinare, parentesi quadre o Pagina su e giù per spostare il piano della sezione.
      </p>
      {#if !result && loading}<p class="stage-note" aria-hidden="true">Calcolo della superficie...</p>{/if}
      {#if loading && result}<p class="stage-badge" aria-hidden="true">Aggiornamento...</p>{/if}
      <div class="hud">
        <div class="view-controls" role="group" aria-label="Controlli della vista">
          <button type="button" aria-label="Ruota a sinistra" onclick={() => rotate(-STEP_DEG, 0)}>◀</button>
          <button type="button" aria-label="Ruota a destra" onclick={() => rotate(STEP_DEG, 0)}>▶</button>
          <button type="button" aria-label="Inclina verso l’alto" onclick={() => rotate(0, STEP_DEG)}>▲</button>
          <button type="button" aria-label="Inclina verso il basso" onclick={() => rotate(0, -STEP_DEG)}>▼</button>
          <button type="button" aria-label="Ingrandisci" onclick={() => zoom(1.2)}>+</button>
          <button type="button" aria-label="Riduci" onclick={() => zoom(1 / 1.2)}>−</button>
          <button type="button" onclick={reset}>Ripristina</button>
        </div>
      </div>
    </section>
    <SceneSettings>
    {@render setup()}
    </SceneSettings>
    </div>
    <span class="mode" data-testid="wave-mode" role="status" data-mode={mode ?? ''}>{mode ? (MODE_LABEL[mode] ?? '') : ''}</span>
    {#if viewError}<p role="alert">{viewError}</p>{/if}

    <div class="legend" aria-label="Legenda della scala di colore">
      <span class="legend-title">Intensità relativa |E|² (1 = onda libera)</span>
      <div class="bar" style:background={gradient} role="img" aria-label="Scala di colore viridis, dal viola (intensità 0) al giallo ({fmt(zTop, 1)})"></div>
      <div class="ticks" aria-hidden="true">
        <span>0</span><span>{fmt(zTop / 2, 2)}</span><span>{fmt(zTop, 1)}</span>
      </div>
    </div>
    <p id="wave-desc" class="small muted">
      Asse lungo: distanza dal crinale (il crinale è al bordo sinistro del riquadro). Asse in profondità: quota sopra (+) o sotto (−) la linea di vista.
      Altezza e colore: intensità relativa. {#if result}Distanza massima {sizeText(result.x_m[result.x_m.length - 1]!)}, quota da −{sizeText(Math.abs(result.y_m[0] ?? 0))} a +{sizeText(Math.abs(result.y_m[result.y_m.length - 1] ?? 0))}; il piano bianco è la sezione a {Math.round(cursor)} m.{/if}
    </p>

    <section class="panel cursor" aria-labelledby="cur-h">
      <h2 id="cur-h">Distanza della sezione</h2>
      <div class="cursor-row">
        <label for="f-cursor">Distanza dal crinale: <output for="f-cursor" data-testid="cursor-value">{Math.round(cursor)}</output> m</label>
        <input
          id="f-cursor"
          type="range"
          min={Math.ceil(range[0])}
          max={Math.floor(range[1])}
          step="1"
          value={Math.round(cursor)}
          disabled={!result}
          aria-valuetext="{Math.round(cursor)} metri dal crinale"
          oninput={(e) => (cursor = Number((e.currentTarget as HTMLInputElement).value))}
        />
        <button type="button" aria-pressed={playing} disabled={reduced || !result} onclick={togglePlay}>{playing ? 'Pausa' : 'Avanza lungo la distanza'}</button>
      </div>
      {#if reduced}<p class="hint">Animazione disattivata: il sistema richiede meno movimento. Usa il cursore.</p>{/if}
    </section>

    {#if result && section}
      <section class="panel" aria-labelledby="res-h">
        <h2 id="res-h">Sezione a {Math.round(cursor)} m</h2>
        <div class="tablist" role="tablist" aria-label="Dettagli della sezione" tabindex="-1">
          {#each visibleTabs as t (t.id)}
            <button type="button" role="tab" id="wtab-{t.id}" aria-selected={shown === t.id} aria-controls="wpanel-{t.id}" tabindex={shown === t.id ? 0 : -1} onclick={() => (tab = t.id)} onkeydown={onTabKey}>{adv ? t.label : STR.tabs[t.id]}</button>
          {/each}
        </div>
        {#each TABS as t (t.id)}
          <div role="tabpanel" id="wpanel-{t.id}" aria-labelledby="wtab-{t.id}" hidden={shown !== t.id} tabindex="0" class="tabpanel">
            {#if shown === t.id}
              {#if t.id === 'section'}
                <p class="small muted" data-testid="section-note" data-source={section.fromApi ? 'api' : 'interp'}>
                  Intensità relativa lungo la quota alla distanza scelta: la linea piena è la simulazione ({section.fromApi ? 'calcolata dal simulatore proprio a questa distanza' : 'anteprima interpolata dalla griglia, in aggiornamento: le frange lontane dall’asse sono approssimate'}), la tratteggiata il bordo a lama esatto.
                  Differenza massima {fmt(stats?.maxAbs ?? 0, 3)}, scarto quadratico medio {fmt(stats?.rms ?? 0, 3)}{result.meta.radius_m > 0 ? ' (la cresta arrotondata non coincide con la lama: è atteso)' : ''}.
                </p>
                <ChartBox
                  {series}
                  x={section.y}
                  ys={[section.simulated, section.exact]}
                  xNumeric
                  xLabel="quota y sulla linea di vista (m)"
                  axisLabels={{ y: 'intensità relativa' }}
                  label="Grafico dell’intensità relativa contro la quota alla distanza del cursore: simulazione e bordo a lama esatto; i valori sono nella tabella"
                />
                <ul class="key-list small" aria-label="Legenda del grafico">
                  <li><span class="key solid" aria-hidden="true"></span>simulazione (split-step)</li>
                  <li><span class="key dashed" aria-hidden="true"></span>bordo a lama esatto (Fresnel)</li>
                </ul>
                <ExportBar name="onda-sezione" csv={() => sectionCsv(section, result!.meta.wavelength_m)} json={() => sectionJson(section, result!)} />
              {:else if t.id === 'table'}
                <!-- svelte-ignore a11y_no_noninteractive_tabindex -->
                <div class="table-scroll" tabindex="0" role="region" aria-label="Tabella della sezione">
                  <table>
                    <caption>Sezione a {Math.round(cursor)} m: ogni {tableStride}° punto di {section.y.length}</caption>
                    <thead><tr><th scope="col">Quota y (m)</th><th scope="col">ν</th><th scope="col">Simulazione</th><th scope="col">Lama esatta</th></tr></thead>
                    <tbody>
                      {#each Array.from(section.y, (y, i) => i).filter((i) => i % tableStride === 0) as i (i)}
                        <tr>
                          <th scope="row">{fmt(section.y[i]!, 1)}</th>
                          <td class="num">{fmt(-section.y[i]! * Math.sqrt(2 / (result.meta.wavelength_m * section.x)), 2)}</td>
                          <td class="num">{fmt(section.simulated[i]!, 3)}</td>
                          <td class="num">{fmt(section.exact[i]!, 3)}</td>
                        </tr>
                      {/each}
                    </tbody>
                  </table>
                </div>
                <ExportBar name="onda-griglia" csv={() => gridCsv(result!)} json={() => gridJson(result!)} />
                <p class="small muted">I file della griglia contengono tutta la superficie ({result.x_m.length} × {result.y_m.length} punti); quelli della sezione, solo la curva mostrata.</p>
              {:else if t.id === 'meta'}
                <dl class="meta" data-testid="wave-meta">
                  <dt>Modello</dt><dd>{result.meta.model}</dd>
                  <dt>Lunghezza d’onda, frequenza</dt><dd>{fmt(result.meta.wavelength_m, 4)} m, {fmt(result.meta.frequency_ghz, 3)} GHz</dd>
                  <dt>Cresta</dt><dd>{result.meta.ridge}{result.meta.radius_m > 0 ? `, raggio ${fmt(result.meta.radius_m, 0)} m` : ''}</dd>
                  <dt>Griglia</dt><dd>{result.meta.grid_shape[0]} distanze × {result.meta.grid_shape[1]} quote; passo {fmt(result.meta.step_m_effective, 1)} m (richiesto {fmt(result.meta.step_m_requested, 1)} m)</dd>
                  <dt>FFT</dt><dd>{result.meta.fft_size} punti, finestra {fmt(result.meta.window_m, 0)} m, passo verticale {fmt(result.meta.dy_m, 2)} m</dd>
                  <dt>Riferimento onda libera</dt><dd>{fmt(result.meta.free_field_reference, 4)} (le intensità sono divise per questo valore)</dd>
                  <dt>Passo del nucleo</dt><dd>massimo {fmt(result.meta.kernel_dz_max_m, 1)} m, limite {fmt(result.meta.kernel_dz_limit_m, 0)} m</dd>
                </dl>
                {#if warnings.length}
                  <h3>Avvisi di campionamento</h3>
                  <ul>{#each warnings as w (w)}<li>{w}</li>{/each}</ul>
                {:else}
                  <p>Nessun avviso di campionamento per questi parametri.</p>
                {/if}
                <p class="small muted">{result.disclaimer}</p>
              {:else}
                <div class="about">
                  <h3>Che cosa mostra la figura</h3>
                  <p>Ogni punto della superficie è l’intensità |E|² del campo, divisa per quella dell’onda libera lontano dal crinale. Dove la superficie vale 1 l’onda passa come se il crinale non ci fosse; sotto 1 il crinale la indebolisce; sopra 1 c’è una frangia di Fresnel che la rinforza.</p>
                  <h3>Perché l’intensità oscilla</h3>
                  <p>Dietro lo spigolo arrivano contributi con cammini diversi: sopra la linea di vista l’onda diretta e quella diffratta dal bordo si sommano ora in fase, ora in opposizione. Le frange sono più larghe quanto più si è lontani dal crinale e quanto più è lunga l’onda (scala √(λx)); nell’ombra l’intensità cala senza oscillare.</p>
                  <h3>Il parametro ν e il segno</h3>
                  <p>ν = −y·√(2/(λx)), con y la quota sopra la linea di vista (la cima del crinale è a y = 0) e x la distanza. ν &gt; 0 è l’ombra (y &lt; 0), ν &lt; 0 la zona illuminata. Il bordo a lama esatto è |F(ν)|² con gli integrali di Fresnel, la curva tratteggiata del grafico.</p>
                  <h3>Limiti dichiarati</h3>
                  <ul>
                    <li>Modello scalare e parassiale 2D (split-step di Fresnel con FFT): niente polarizzazione né onde a grande angolo.</li>
                    <li>Un solo crinale, onda piana incidente, nessun regolite, nessun suolo e nessuna curvatura lunare.</li>
                    <li>La cresta arrotondata è una parabola assorbente: simulata, non validata (a passo fine resta circa 15-45 % sotto ITU-R P.526-9 eq. 30-32).</li>
                    <li>La finestra di calcolo è periodica: vale solo per quote molto minori di metà finestra (limite di 200 m).</li>
                    <li>Gli avvisi di campionamento compaiono quando la griglia è troppo grossolana per la lunghezza d’onda.</li>
                  </ul>
                </div>
              {/if}
            {/if}
          </div>
        {/each}
      </section>
    {:else if !loading}
      <section class="panel" aria-labelledby="empty-h">
        <h2 id="empty-h">Sezione</h2>
        <p class="muted">Nessuna superficie valida: correggi i parametri o ripremi un preset.</p>
      </section>
    {/if}
  </div>
</div>

<div class="visually-hidden" role="status" aria-live="polite" aria-atomic="true" bind:this={liveEl}></div>

<style>
  .workspace {
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
  .cursor,
  .legend {
    margin-top: var(--space-4);
  }
  h2 {
    font-size: var(--fs-h3);
    font-stretch: 100%;
  }
  h3 {
    font-size: var(--fs-body);
    margin: var(--space-4) 0 var(--space-2);
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
  .field input:not([type='radio']) {
    width: 100%;
  }
  fieldset.spec {
    border: 0;
    padding: 0;
    margin: 0 0 var(--space-3);
    min-width: 0;
  }
  .check {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    min-height: var(--target);
  }
  .presets {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-2);
    margin: 0 0 var(--space-3);
  }
  .presets button[aria-pressed='true'],
  .cursor button[aria-pressed='true'] {
    background: var(--c-text);
    color: var(--c-bg);
  }
  .status:empty {
    margin: 0;
  }
  .notice {
    border-left: 3px solid var(--c-power);
    padding-left: var(--space-3);
    margin-block: var(--space-3);
  }
  ul.notice {
    padding-left: var(--space-5);
  }
  .notice.warn {
    border-left-color: var(--c-danger);
    font-weight: 600;
  }
  .figure {
    margin-top: 0;
    position: relative;
    border-radius: var(--radius-md);
    overflow: hidden;
    background: #0b0f17;
    color: #f2f4f8;
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
  .stage-note,
  .stage-badge {
    position: absolute;
    margin: 0;
    pointer-events: none;
    font-size: var(--fs-small);
  }
  .stage-note {
    inset: 0;
    display: grid;
    place-items: center;
  }
  .stage-badge {
    top: var(--space-3);
    right: var(--space-3);
    background: rgb(0 0 0 / 55%);
    padding: var(--space-1) var(--space-3);
    border-radius: var(--radius-md);
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
  .legend {
    max-width: 32rem;
  }
  .legend-title {
    font-size: var(--fs-small);
    font-weight: 600;
  }
  .bar {
    height: 0.9rem;
    border-radius: 2px;
    margin-top: var(--space-1);
    border: 1px solid var(--c-hairline);
  }
  .ticks {
    display: flex;
    justify-content: space-between;
    font-size: var(--fs-small);
    color: var(--c-muted);
  }
  .cursor-row {
    display: grid;
    grid-template-columns: minmax(0, 1fr);
    gap: var(--space-2);
    align-items: center;
  }
  @media (min-width: 720px) {
    .cursor-row {
      grid-template-columns: auto minmax(8rem, 1fr) auto;
      gap: var(--space-4);
    }
  }
  .cursor-row input[type='range'] {
    width: 100%;
    min-height: var(--target);
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
  .tabpanel :global(.table-scroll) {
    position: relative;
    max-height: 24rem;
  }
  .tabpanel[hidden] {
    display: none;
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
  .key {
    display: inline-block;
    width: 1.5rem;
    height: 3px;
  }
  .key.solid {
    background: var(--c-uplink);
  }
  .key.dashed {
    background: repeating-linear-gradient(90deg, var(--c-power) 0 6px, transparent 6px 10px);
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
  @media (min-width: 720px) {
    .meta {
      grid-template-columns: 16rem minmax(0, 1fr);
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
