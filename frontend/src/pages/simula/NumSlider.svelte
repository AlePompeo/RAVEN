<!-- SPDX-License-Identifier: Apache-2.0 -->
<!--
  Controllo di Simula: cursore + campo numerico legati allo stesso valore, aggiornati mentre si muove (nessun pulsante
  "Calcola"). Bersagli >= 44 px, tastiera nativa del range (frecce, Pagina su/giù, Home/Fine). `tip`: definizione di una
  riga (glossario), `tag`/`source`: etichetta V/D/I e fonte (solo Avanzato). Proprietà CSS logiche (RTL pronto).
-->
<script lang="ts">
  import Badge from '../grazinglink/Badge.svelte';
  import { formatNumber, t } from '../../i18n/i18n.svelte';

  let {
    id,
    label,
    value = $bindable(),
    min,
    max,
    step,
    unit = '',
    digits = 2,
    tip = '',
    tag = '',
    source = '',
    disabled = false,
    text,
    testid,
  }: {
    id: string;
    label: string;
    value: number;
    min: number;
    max: number;
    step: number;
    unit?: string;
    digits?: number;
    tip?: string;
    tag?: string;
    source?: string;
    disabled?: boolean;
    /** testo del valore (es. "100 kbps" per un indice); senza, il campo numerico */
    text?: string;
    testid?: string;
  } = $props();

  const STR = $derived({ tip: t('sim.slider.tip'), source: t('sim.slider.source') });
  const clamp = (v: number) => Math.min(max, Math.max(min, v));
  function fromNumber(e: Event) {
    const v = (e.currentTarget as HTMLInputElement).valueAsNumber;
    if (Number.isFinite(v)) value = clamp(v);
  }
</script>

<div class="ctl" data-testid={testid}>
  <div class="head">
    <label for={id}>{label}</label>
    {#if tip}
      <details class="tip">
        <summary aria-label="{STR.tip}: {label}">?</summary>
        <p>{tip}</p>
      </details>
    {/if}
    {#if tag}<Badge status={tag} />{/if}
  </div>
  <div class="row">
    <input
      {id}
      type="range"
      {min}
      {max}
      {step}
      {disabled}
      bind:value
      aria-valuetext={text ?? `${formatNumber(value, { minimumFractionDigits: digits, maximumFractionDigits: digits })} ${unit}`.trim()}
    />
    {#if text !== undefined}
      <output for={id} class="val" data-testid={testid ? `${testid}-value` : undefined}>{text}</output>
    {:else}
      <span class="num">
        <input
          type="number"
          {min}
          {max}
          {step}
          {disabled}
          value={Number(value.toFixed(digits))}
          oninput={fromNumber}
          aria-label="{label} ({unit || t('sim.slider.value')})"
          data-testid={testid ? `${testid}-num` : undefined}
        />
        {#if unit}<span class="unit">{unit}</span>{/if}
      </span>
    {/if}
  </div>
  {#if source}<p class="src"><span class="visually-hidden">{STR.source}: </span>{source}</p>{/if}
</div>

<style>
  .ctl {
    display: grid;
    gap: var(--space-1);
  }
  .head {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    flex-wrap: wrap;
  }
  label {
    font-weight: 600;
  }
  .row {
    display: flex;
    align-items: center;
    gap: var(--space-2);
  }
  input[type='range'] {
    flex: 1 1 auto;
    min-inline-size: 0;
    block-size: 44px;
    accent-color: var(--c-accent, #0071e3);
  }
  .num {
    display: inline-flex;
    align-items: center;
    gap: var(--space-1);
  }
  input[type='number'] {
    inline-size: 6.5rem;
    min-block-size: 44px;
    padding-inline: var(--space-2);
    font-variant-numeric: tabular-nums;
  }
  .val {
    min-inline-size: 6rem;
    font-variant-numeric: tabular-nums;
    font-weight: 600;
  }
  .unit {
    color: var(--c-muted);
  }
  .tip {
    position: relative;
  }
  .tip summary {
    list-style: none;
    display: inline-grid;
    place-items: center;
    inline-size: 44px;
    block-size: 44px;
    margin-block: -10px;
    border-radius: 50%;
    cursor: pointer;
    font-weight: 700;
    color: var(--c-muted);
  }
  .tip summary::-webkit-details-marker {
    display: none;
  }
  .tip summary::before {
    content: '';
    position: absolute;
    inset: 11px;
    border: 1.5px solid currentColor;
    border-radius: 50%;
  }
  .tip p {
    position: absolute;
    inset-inline-start: 0;
    inset-block-start: 100%;
    z-index: 5;
    inline-size: min(18rem, 70vw);
    margin: 0;
    padding: var(--space-2);
    border-radius: var(--radius-xs);
    background: var(--c-text);
    color: var(--c-bg);
    font-size: var(--fs-small, 0.875rem);
  }
  .src {
    margin: 0;
    color: var(--c-muted);
    font-size: var(--fs-micro, 0.75rem);
  }
</style>
