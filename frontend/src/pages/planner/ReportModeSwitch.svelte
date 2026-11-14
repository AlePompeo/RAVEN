<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- Learn | Expert report mode. Native radio group (arrow keys, one tab stop). Does not change the site mode.
     `compact` is the two-option switch of the Report step; the default is the card version of the Dossier. -->
<script lang="ts">
  import { t } from '../../i18n/i18n.svelte';
  import { REPORT_MODES, type ReportMode } from './reportSections';
  let { mode, onchange, name = 'report-mode', compact = false }: { mode: ReportMode; onchange: (mode: ReportMode) => void; name?: string; compact?: boolean } = $props();
</script>

<fieldset class="mode" class:compact data-testid="report-mode" data-mode={mode}>
  <legend>{t('rmode.legend')}</legend>
  <div class="options">
    {#each REPORT_MODES as option}
      <label class:on={mode === option}>
        <input type="radio" {name} value={option} checked={mode === option} onchange={() => { if (mode !== option) onchange(option); }} />
        <span><strong>{t(`rmode.${option}`)}</strong>{#if !compact}<small>{t(`rmode.${option}Desc`)}</small>{/if}</span>
      </label>
    {/each}
  </div>
  {#if !compact}<p class="note">{t('rmode.note')}</p>{/if}
</fieldset>

<style>
  .mode { margin-block: 1rem; border: 1px solid #7b9cb36e; border-radius: .65rem; padding: .8rem 1rem; }
  .options { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: .75rem; }
  label { display: flex; align-items: flex-start; gap: .7rem; min-height: 44px; padding: .6rem .8rem; margin: 0; font-weight: 400; border: 1px solid #7b9cb36e; border-radius: .6rem; cursor: pointer; }
  label.on { border-color: #9bdfff; background: #11263c; }
  input { flex: 0 0 auto; width: 1.2rem; min-height: 1.2rem; margin-top: .15rem; accent-color: #9bdfff; }
  span { display: grid; gap: .25rem; } small { line-height: 1.45; color: #c3d4e0; font-size: .9rem; }
  .note { margin: .6rem 0 0; font-size: .9rem; line-height: 1.5; }
  input:focus-visible { outline: 2px solid #b1e6ff; outline-offset: 3px; }
  .compact { margin: 0; padding: 0; border: 0; min-width: 0; }
  .compact legend { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); }
  .compact .options { display: inline-flex; gap: 0; border: 1px solid #7b9cb36e; border-radius: .6rem; overflow: hidden; }
  .compact label { min-height: 44px; border: 0; border-radius: 0; align-items: center; padding: .4rem .9rem; }
  @media (max-width: 650px) { .options { grid-template-columns: 1fr; } .compact .options { display: inline-flex; } }
</style>
