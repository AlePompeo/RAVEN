<!-- SPDX-License-Identifier: Apache-2.0 -->
<!--
  Data e ora UTC del visualizzatore (stile "ora" di Google Earth): campi data/ora, "Adesso", passi di un giorno o
  un'ora e riproduzione a tre velocita'. La direzione del Sole viene da GET /api/raven/sky/subsolar (LightClient:
  throttle ~4/s, richieste superate annullate). In errore resta l'ultima luce valida e il messaggio e' visibile.
  "Ombra" qui = terminatore + ombreggiatura del rilievo, non ombre portate.
-->
<script lang="ts">
  import { onDestroy, untrack } from 'svelte';
  import Icon from '../../components/ui/Icon.svelte';
  import { LightClient, type Light, type SkyBody, type SkyError } from './skyLight';
  import {
    advance,
    clampMs,
    dateValue,
    inRange,
    MAX_MS,
    MIN_MS,
    parseDateTime,
    RANGE_TEXT,
    SPEEDS,
    stepMs,
    STEPS,
    timeValue,
    type SpeedId,
  } from './simTime';

  interface Props {
    /** Corpo mostrato; `null` per il Sole (nessuna luce da regolare). */
    body: SkyBody | null;
    onlight: (l: Light | null) => void;
    /** Istante iniziale (ms UTC, dallo scenario condiviso); senza, l'ora attuale. */
    initialMs?: number | null;
    /** Aggiornamento esterno dello scenario, senza reinviare la scelta allo store. */
    externalMs?: number | null;
    /** Ogni istante scelto; `explicit` e' falso per l'istante iniziale e i cambi di corpo (nessuna scelta dell'utente). */
    ontime?: (ms: number, explicit: boolean) => void;
    onLightError?: (ms: number) => void;
    belowScene?: boolean;
  }
  let { body, onlight, initialMs = null, externalMs = null, ontime, onLightError, belowScene = false }: Props = $props();

  const TICK_MS = 250;
  const start = clampMs(untrack(() => initialMs) ?? Math.floor(Date.now() / 1000) * 1000);
  let ms = $state(start);
  let dateStr = $state(dateValue(start));
  let timeStr = $state(timeValue(start));
  let playing = $state(false);
  let speed = $state<SpeedId>('hour');
  let light = $state<Light | null>(null);
  let problem = $state<string | null>(null);
  let note = $state('');
  let busy = $state(false);
  let open = $state(false);
  let invalidFields = false;

  const disabled = $derived(body === null);
  const msPerS = $derived(SPEEDS.find((s) => s.id === speed)!.msPerS);

  const client = new LightClient({
    onLight: (l) => {
      if (invalidFields || l.ms !== ms || l.body !== body) return;
      light = l;
      problem = null;
      onlight(l);
    },
    onError: (e: SkyError, errorBody, errorMs) => {
      if (invalidFields || errorMs !== ms || errorBody !== body) return;
      problem =
        e.kind === 'range'
          ? `Data fuori dall’intervallo supportato (${RANGE_TEXT}). Resta l’ultima luce valida.`
          : `${e.message} Resta l’ultima luce valida.`;
      playing = false;
      onLightError?.(errorMs);
    },
    onBusy: (b) => (busy = b),
  });

  function sync() {
    dateStr = dateValue(ms);
    timeStr = timeValue(ms);
  }
  function request() {
    ontime?.(ms, true);
    if (body) client.request(body, ms);
  }
  function setTime(next: number, say?: string) {
    invalidFields = false;
    ms = next;
    sync();
    note = say ?? '';
    request();
  }
  function step(delta: number) {
    const r = stepMs(ms, delta);
    setTime(r.ms, r.clamped ? `Raggiunto il limite dell’intervallo supportato (${RANGE_TEXT}).` : '');
  }
  function commitFields() {
    const parsed = parseDateTime(dateStr, timeStr);
    if (parsed === null) {
      invalidFields = true;
      problem = 'Data o ora non valida: usa il formato aaaa-mm-gg e hh:mm:ss (UTC). Resta l’ultima luce valida.';
      return;
    }
    if (!inRange(parsed)) {
      invalidFields = true;
      problem = `Data fuori dall’intervallo supportato (${RANGE_TEXT}). Resta l’ultima luce valida.`;
      return;
    }
    problem = null;
    invalidFields = false;
    setTime(parsed);
  }
  function now() {
    playing = false;
    problem = null;
    invalidFields = false;
    setTime(clampMs(Math.floor(Date.now() / 1000) * 1000), 'Ora attuale.');
  }
  function togglePlay() {
    playing = !playing;
    if (playing) problem = null;
    note = playing ? `Riproduzione: ${SPEEDS.find((s) => s.id === speed)!.label} di tempo simulato.` : 'Riproduzione ferma.';
  }

  export function pause() {
    if (playing) {
      playing = false;
      note = 'Riproduzione ferma.';
    }
  }

  $effect(() => {
    const next = externalMs;
    if (next === null) return;
    untrack(() => {
      if (Math.floor(ms / 1000) === Math.floor(next / 1000)) return;
      playing = false;
      problem = null;
      ms = next;
      sync();
      ontime?.(ms, false);
      if (body) client.request(body, ms);
    });
  });

  let timer: ReturnType<typeof setInterval> | undefined;
  $effect(() => {
    if (!playing || disabled) return;
    let last = performance.now();
    timer = setInterval(() => {
      const t = performance.now();
      const r = advance(ms, t - last, msPerS);
      last = t;
      ms = r.ms;
      sync();
      request();
      if (r.atLimit) {
        playing = false;
        note = `Riproduzione ferma al limite dell’intervallo supportato (${RANGE_TEXT}).`;
      }
    }, TICK_MS);
    return () => clearInterval(timer);
  });

  // cambio di corpo: nuova luce per lo stesso istante (la Luce di un altro corpo non vale)
  $effect(() => {
    const b = body;
    untrack(() => {
      light = null;
      onlight(null);
      ontime?.(ms, false);
      if (b) client.request(b, ms);
      else {
        playing = false;
        problem = null;
      }
    });
  });

  onDestroy(() => {
    clearInterval(timer);
    client.dispose();
  });

  const fmtDeg = (v: number, pos: string, neg: string) => `${Math.abs(v).toFixed(2)}° ${v >= 0 ? pos : neg}`;
  const status = $derived(
    problem ?? (note || (light && !playing ? `Luce calcolata per ${dateStr} ${timeStr} UTC.` : '')),
  );
</script>

<div class="sky" class:belowScene role="group" aria-labelledby="sky-h" data-testid="sky-time">
  <p id="sky-h" class="title"><Icon name="sun" /> Data e ora (UTC)</p>
  <button
    type="button"
    class="toggle"
    aria-expanded={open}
    aria-controls="sky-panel"
    onclick={() => (open = !open)}
  >
    <Icon name="sun" />
    <span class="num">{dateStr} {timeStr.slice(0, 5)}</span>
    <span class="vh">Data e ora UTC: {open ? 'chiudi' : 'modifica'}</span>
    <span aria-hidden="true">{open ? '▾' : '▴'}</span>
  </button>
  <div id="sky-panel" class="sky-body" class:is-open={open}>
  {#if disabled}
    <p class="hint" id="sky-hint">Il Sole è la sorgente di luce: qui non c’è nulla da regolare. Scegli la Luna o la Terra.</p>
  {/if}
  <div class="grid" aria-describedby={disabled ? 'sky-hint' : undefined}>
    <div class="field">
      <label for="sky-date">Data</label>
      <input
        id="sky-date"
        type="date"
        bind:value={dateStr}
        min={dateValue(MIN_MS)}
        max={dateValue(MAX_MS)}
        {disabled}
        aria-invalid={problem ? 'true' : undefined}
        aria-describedby="sky-status"
        onchange={commitFields}
        data-spatial-skip
      />
    </div>
    <div class="field">
      <label for="sky-time">Ora UTC</label>
      <input
        id="sky-time"
        type="time"
        step="1"
        bind:value={timeStr}
        {disabled}
        aria-invalid={problem ? 'true' : undefined}
        aria-describedby="sky-status"
        onchange={commitFields}
        data-spatial-skip
      />
    </div>
    <div class="steps" role="group" aria-label="Passi nel tempo">
      <button type="button" aria-label="Un giorno indietro" onclick={() => step(STEPS.dayBack)} {disabled}>−1 giorno</button>
      <button type="button" aria-label="Un’ora indietro" onclick={() => step(STEPS.hourBack)} {disabled}>−1 h</button>
      <button type="button" class="btn-now" onclick={now} {disabled}>Adesso</button>
      <button type="button" aria-label="Un’ora avanti" onclick={() => step(STEPS.hourFwd)} {disabled}>+1 h</button>
      <button type="button" aria-label="Un giorno avanti" onclick={() => step(STEPS.dayFwd)} {disabled}>+1 giorno</button>
    </div>

    <div class="play">
      <button type="button" class="play-btn" aria-pressed={playing} onclick={togglePlay} {disabled}>
        <Icon name={playing ? 'pause' : 'play'} />
        {playing ? 'Ferma' : 'Riproduci'}
      </button>
      <div class="field speed">
        <label for="sky-speed">Velocità</label>
        <select id="sky-speed" bind:value={speed} {disabled}>
          {#each SPEEDS as s (s.id)}<option value={s.id}>{s.short}</option>{/each}
        </select>
      </div>
    </div>
  </div>

  <div class="lines">
  <p class="status" id="sky-status" role="status" aria-live="polite" data-testid="sky-status" data-problem={problem ? '1' : undefined}>{status}</p>
  <p class="subsolar num" data-testid="sky-subsolar" aria-busy={busy}>
    {#if light}
      Punto subsolare: lat {fmtDeg(light.lat_deg, 'N', 'S')}, lon {fmtDeg(light.lon_deg_east, 'E', 'O')}
    {:else if !disabled}
      Punto subsolare: in calcolo…
    {/if}
  </p>
  </div>
  <p class="help">Luce reale dal Sole (JPL DE440). L’“ombra” è il terminatore più l’ombreggiatura del rilievo, non ombre portate.</p>
  </div>
</div>

<style>
  .sky {
    flex: 1 1 100%;
    display: grid;
    gap: var(--space-2);
    min-width: 0;
  }
  .lines {
    display: flex;
    flex-wrap: wrap;
    gap: 0 var(--space-4);
  }
  .title {
    display: none;
    align-items: center;
    align-items: center;
    gap: var(--space-2);
    margin: 0;
    font-size: var(--fs-small);
    font-weight: 600;
  }
  .grid {
    display: flex;
    flex-wrap: wrap;
    align-items: flex-end;
    gap: var(--space-2);
  }
  .field {
    min-width: 0;
  }
  .field label {
    margin-bottom: 2px;
    font-weight: 400;
    color: var(--c-muted);
  }
  select {
    width: 7.5rem;
  }
  input[type='date'],
  input[type='time'] {
    width: auto;
    min-height: var(--target);
    padding: 0.4rem 0.6rem;
    font-size: var(--fs-small);
    color-scheme: dark;
    font-variant-numeric: tabular-nums;
  }
  input:disabled,
  select:disabled {
    opacity: 0.5;
  }
  button {
    min-height: var(--target);
    min-width: var(--target);
    padding: 0 0.6rem;
    border-color: var(--glass-line);
    color: var(--c-text);
    font-size: var(--fs-small);
    white-space: nowrap;
  }
  button:disabled {
    opacity: 0.4;
  }
  button:hover:not(:disabled) {
    border-color: rgb(255 255 255 / 0.42);
  }
  button[aria-pressed='true'] {
    color: #000;
  }
  .steps,
  .play {
    display: flex;
    align-items: flex-end;
    gap: var(--space-2);
    flex-wrap: wrap;
  }
  .hint,
  .help,
  .subsolar {
    margin: 0;
    font-size: var(--fs-small);
    color: var(--c-muted);
  }
  .subsolar {
    color: var(--c-text);
  }
  .status {
    margin: 0;
    min-height: 1.3em;
    font-size: var(--fs-small);
    color: var(--c-text);
  }
  .status[data-problem='1'] {
    color: var(--c-danger, #ff6b6b);
    font-weight: 600;
  }
  .toggle {
    display: none;
  }
  .vh {
    position: absolute;
    width: 1px;
    height: 1px;
    overflow: hidden;
    clip-path: inset(50%);
  }
  .sky-body {
    display: grid;
    gap: var(--space-2);
    min-width: 0;
  }
  @container (max-width: 833px) {
    .sky {
      position: relative;
    }
    .sky.belowScene .toggle {
      display: none;
    }
    .sky.belowScene .sky-body {
      display: grid;
      position: static;
    }
    .toggle {
      display: inline-flex;
      justify-self: start;
    }
    /* sul telefono il pannello si apre sopra la barra e non spinge il corpo: chiuso e' fuori dall'albero di accessibilita' */
    .sky-body {
      display: none;
    }
    .sky-body.is-open {
      display: grid;
      position: absolute;
      z-index: 5;
      left: calc(-1 * var(--space-3));
      right: calc(-1 * var(--space-3));
      bottom: calc(100% + var(--space-3));
      padding: var(--space-3);
      border-radius: var(--r-panel, 14px);
      background: rgb(0 0 0 / 0.92);
      border: 1px solid var(--glass-line);
    }
    .grid {
      display: grid;
      grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
      gap: var(--space-2);
    }
    .steps {
      grid-column: 1 / -1;
      display: grid;
      grid-template-columns: repeat(5, minmax(0, 1fr));
    }
    .steps button {
      padding: 0 0.1rem;
      font-size: 0.75rem;
    }
    .play {
      grid-column: 1 / -1;
    }
    .play-btn {
      flex: 1;
    }
    input[type='date'],
    input[type='time'],
    select {
      width: 100%;
      padding-inline: 0.4rem;
    }
    .help {
      font-size: 0.75rem;
    }
  }
</style>
