<!-- SPDX-License-Identifier: Apache-2.0 -->
<script lang="ts">
  import { t } from '../../i18n/i18n.svelte';
  let { id, label, value = $bindable<number | null>(null), min, max, step = 1, unit = '', tag = 'I', source = '', hint = '' }: {
    id: string; label: string; value: number | null; min: number; max: number; step?: number;
    unit?: string; tag?: string; source?: string; hint?: string;
  } = $props();
  const invalid = $derived(value === null || !Number.isFinite(value) || value < min || value > max);
</script>

<div class="parameter">
  <div class="heading"><label for={id}>{label}</label><span class="tag">{tag}</span></div>
  <div class="inputs">
    <input type="range" id={`${id}-range`} {min} {max} {step} value={value ?? min}
      aria-label={label} aria-valuetext={`${value ?? '—'} ${unit}`}
      oninput={(e) => value = e.currentTarget.valueAsNumber} />
    <div class="number"><input {id} type="number" {min} {max} {step} value={value ?? ''}
      aria-invalid={invalid} aria-describedby={`${id}-help`}
      oninput={(e) => value = Number.isNaN(e.currentTarget.valueAsNumber) ? null : e.currentTarget.valueAsNumber} /><span>{unit}</span></div>
  </div>
  <p id={`${id}-help`}>{hint || `${min} – ${max} ${unit}`}{#if source}<small> · {source}</small>{/if}</p>
  {#if invalid}<p class="invalid" role="alert">{t('journey.valueRange', { min, max, unit })}</p>{/if}
</div>

<style>
  .parameter { display: grid; gap: .55rem; }
  .heading, .inputs, .number { display: flex; align-items: center; gap: .75rem; }
  .heading { justify-content: space-between; } label { font-weight: 600; }
  .tag { font-size: .7rem; border: 1px solid var(--c-hairline); padding: .1rem .4rem; border-radius: .3rem; }
  input[type='range'] { flex: 1; min-width: 0; min-height: 44px; accent-color: #9bdfff; }
  .number input { width: 7rem; } .number span { min-width: 2rem; }
  p { margin: 0; color: var(--c-muted); font-size: .85rem; } .invalid { color: #ffb6a8; }
</style>
