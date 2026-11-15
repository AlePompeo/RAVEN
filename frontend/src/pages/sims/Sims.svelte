<!-- SPDX-License-Identifier: Apache-2.0 -->
<script lang="ts">
  import { onMount, onDestroy, tick } from 'svelte';
  import SubNav from '../../components/ui/SubNav.svelte';
  import { setPageContext, clearPageContext } from '../../shell/pageContext.svelte';
  import { sanitizeParams } from '../chat/assistant';
  import { buildInputs, listSimulations, runSimulation, type InputRow, type FieldError, type UiError } from './api';
  import { modeNow } from '../../shell/modeState.svelte';
  import { t } from '../../i18n/i18n.svelte';

  let sims = $state<string[]>([]);
  let loading = $state(true);
  let loadError = $state(false);
  let selected = $state('');
  let rows = $state<InputRow[]>([{ name: 'x', value: '' }]);
  let running = $state(false);
  let error = $state<UiError | null>(null);
  let fieldErrors = $state<FieldError[]>([]);
  let completed = $state(false);
  let outputs = $state<Record<string, number> | null>(null);
  let fsplC = $state<number | null>(null);
  let fsplError = $state(false);
  let ctrl: AbortController | null = null;

  onMount(async () => {
    try {
      sims = await listSimulations(fetch);
      selected = sims[0] ?? '';
    } catch {
      loadError = true;
    } finally {
      loading = false;
    }
  });
  onDestroy(() => {
    ctrl?.abort();
    clearPageContext();
  });

  // "Spiega questa pagina": pubblica la simulazione scelta, i valori inseriti (numeri validi) e l'ultimo risultato
  $effect(() => {
    const p: Record<string, number> = {};
    for (const r of rows) {
      const name = r.name.trim();
      const text = r.value.trim();
      const n = Number(text);
      if (name && text !== '' && Number.isFinite(n)) p[name] = n;
    }
    for (const [k, v] of Object.entries(outputs ?? {})) p[`risultato_${k}`] = v;
    setPageContext({ simulation_id: selected, params: sanitizeParams(p) });
  });

  const fieldError = (i: number, f: 'name' | 'value') => fieldErrors.find((e) => e.index === i && e.field === f);
  const focusId = async (id: string) => {
    await tick();
    document.getElementById(id)?.focus();
  };

  async function addRow() {
    rows.push({ name: '', value: '' });
    fieldErrors = [];
    await focusId(`in-name-${rows.length - 1}`);
  }
  async function removeRow(i: number) {
    rows.splice(i, 1);
    fieldErrors = [];
    // focus sul pulsante "Rimuovi" della riga precedente (o della prima); se resta una riga sola, su "Aggiungi"
    await focusId(rows.length > 1 ? `rm-${Math.max(i - 1, 0)}` : 'add-row');
  }

  function changeSimulation(e: Event) {
    const id = (e.currentTarget as HTMLSelectElement).value;
    outputs = null;
    fsplC = null;
    fsplError = false;
    error = null;
    completed = false;
    fieldErrors = [];
    if (id === 'grazinglink-link') {
      rows = [{ name: 'earth_el_deg', value: '1' }, { name: 'ridge_radius_m', value: '100' }];
    }
  }

  async function run(e: SubmitEvent) {
    e.preventDefault();
    if (running) return;
    error = null;
    completed = false;
    outputs = null;
    fsplC = null;
    fsplError = false;
    fieldErrors = [];
    const built = buildInputs(rows);
    if (!built.ok) {
      error = built.error;
      fieldErrors = built.errors;
      const first = built.errors[0];
      if (first) await focusId(`in-${first.field === 'name' ? 'name' : 'val'}-${first.index}`);
      return;
    }
    running = true;
    ctrl = new AbortController();
    const r = await runSimulation(fetch, selected, built.inputs, ctrl.signal);
    if (r.ok) {
      outputs = r.outputs;
      completed = true;
      if (selected === 'grazinglink-link') {
        const distance = r.outputs.distance_km;
        const frequency = r.outputs.frequency_ghz;
        if (!sims.includes('fspl-c') || distance === undefined || frequency === undefined || r.outputs.fspl_db === undefined) {
          fsplError = true;
        } else {
          const check = await runSimulation(fetch, 'fspl-c', { distance_km: distance, freq_ghz: frequency }, ctrl.signal);
          if (!check.ok || check.outputs.fspl_db === undefined) fsplError = true;
          else fsplC = check.outputs.fspl_db;
        }
      }
    } else error = r.error;
    running = false;
  }
</script>

<SubNav title={t('sims.title')} learn={t('sims.learn')} />

<div class="workspace tile tile--alt">
  <div class="container container--wide">
    {#if loading}
      <p role="status">{t('sims.loading')}</p>
    {:else if loadError}
      <p role="alert">{t('sims.loadError')}</p>
    {:else if sims.length === 0}
      <p>{t('sims.empty')}</p>
    {:else}
      <div class="layout">
        <form class="panel" onsubmit={run} novalidate>
          <h2>{t('sims.inputs')}</h2>
          {#if !modeNow.advanced}<p class="hint" data-testid="sims-steps">{t('sims.steps')}</p>{/if}
          <p class="field">
            <label for="sim-id">{t('sims.simulation')}</label>
            <select id="sim-id" bind:value={selected} disabled={running} onchange={changeSimulation}>
              {#each sims as s (s)}<option value={s}>{s === 'grazinglink-link' ? 'RAVEN' : s}</option>{/each}
            </select>
          </p>
          {#if selected === 'grazinglink-link'}<p class="hint">{t('sims.grazingHelp')}</p>{/if}
          <fieldset>
            <legend>{t('sims.numericInputs')}</legend>
            {#each rows as row, i (i)}
              {@const ne = fieldError(i, 'name')}
              {@const ve = fieldError(i, 'value')}
              <div class="row">
                <p class="field">
                  <label for="in-name-{i}">{t('sims.inputName', { n: i + 1 })}</label>
                  <input
                    id="in-name-{i}"
                    type="text"
                    bind:value={row.name}
                    autocomplete="off"
                    aria-required="true"
                    aria-invalid={ne ? 'true' : undefined}
                    aria-describedby={ne ? `in-name-err-${i}` : undefined}
                  />
                  {#if ne}<span id="in-name-err-{i}" class="field-error">{t(ne.message.key, ne.message.params)}</span>{/if}
                </p>
                <p class="field">
                  <label for="in-val-{i}">{t('sims.inputValue', { n: i + 1 })}</label>
                  <input
                    id="in-val-{i}"
                    type="text"
                    inputmode="decimal"
                    bind:value={row.value}
                    aria-required="true"
                    aria-invalid={ve ? 'true' : undefined}
                    aria-describedby={ve ? `in-val-err-${i}` : undefined}
                  />
                  {#if ve}<span id="in-val-err-{i}" class="field-error">{t(ve.message.key, ve.message.params)}</span>{/if}
                </p>
                {#if rows.length > 1}
                  <button type="button" class="remove" id="rm-{i}" onclick={() => removeRow(i)}>{t('sims.removeInput', { n: i + 1 })}</button>
                {/if}
              </div>
            {/each}
            <button type="button" id="add-row" onclick={addRow}>{t('sims.addInput')}</button>
          </fieldset>
          <p class="submit"><button type="submit" aria-disabled={running}>{t(running ? 'sims.running' : 'sims.run')}</button></p>
        </form>

        <section class="panel results" aria-labelledby="sim-out-h">
          <h2 id="sim-out-h">{t('sims.result')}</h2>
          <p role="status">{completed ? t('sims.completed') : ''}</p>
          {#if error}<p role="alert">{t(error.key, error.params)}</p>{/if}
          {#if fsplError}<p role="alert">{t('sims.fsplUnavailable')}</p>{/if}
          {#if outputs}
            {#if selected === 'grazinglink-link'}
              <p>{t('sims.grazingSynthetic')}</p>
              {#if fsplC !== null && outputs.fspl_db !== undefined}
                <p>{t('sims.fsplComparison', { python: outputs.fspl_db.toFixed(3), c: fsplC.toFixed(3), diff: (fsplC - outputs.fspl_db).toFixed(3) })}</p>
              {/if}
            {/if}
            <!-- svelte-ignore a11y_no_noninteractive_tabindex -->
            <div class="table-scroll" tabindex="0" role="region" aria-label={t('sims.resultOf', { name: selected })}>
              <table>
                <caption>{t('sims.resultOf', { name: selected })}</caption>
                <thead><tr><th scope="col">{t('sims.output')}</th><th scope="col">{t('sims.value')}</th></tr></thead>
                <tbody>
                  {#each Object.entries(outputs) as [k, v] (k)}
                    <tr><th scope="row">{k}</th><td class="num">{v}</td></tr>
                  {/each}
                </tbody>
              </table>
            </div>
          {:else if !error}
            <p class="muted">{t('sims.resultEmpty')}</p>
          {/if}
        </section>
      </div>
    {/if}
  </div>
</div>

<style>
  .workspace {
    padding-block: var(--space-5) var(--space-7);
  }
  .layout {
    display: grid;
    grid-template-columns: minmax(0, 7fr) minmax(0, 5fr);
    gap: var(--space-4);
    align-items: start;
  }
  .panel h2 {
    font-size: var(--fs-h3);
    font-stretch: 100%;
  }
  .field {
    margin-bottom: var(--space-4);
  }
  .row {
    display: grid;
    grid-template-columns: minmax(0, 1fr) minmax(0, 1fr) auto;
    gap: 0 var(--space-3);
    align-items: end;
  }
  .row .field {
    margin-bottom: var(--space-3);
  }
  .remove {
    margin-bottom: var(--space-3);
    font-size: var(--fs-small);
  }
  .submit {
    margin: 0;
  }
  /* la regione live resta nel DOM e visibile anche vuota: altrimenti il primo annuncio può perdersi */
  .results [role='status']:empty {
    margin: 0;
  }
  @media (max-width: 833px) {
    .layout {
      grid-template-columns: minmax(0, 1fr);
    }
  }
  @media (max-width: 479px) {
    .row {
      grid-template-columns: minmax(0, 1fr);
    }
    .remove {
      justify-self: start;
    }
  }
</style>
