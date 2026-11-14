<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- Expert only, inside a closed "Customise sections" group: which appendices follow the four parts of the report. -->
<script lang="ts">
  import { t, type MessageKey } from '../../i18n/i18n.svelte';
  import { REPORT_APPENDICES, type ReportSections } from './reportSections';
  let { selection = $bindable(), pages }: { selection: ReportSections; pages: number | null } = $props();
</script>

<section class="section-picker" data-testid="report-section-picker">
  <p>{t('reportSelection.intro')}</p>
  <div class="items">
    {#each REPORT_APPENDICES as app}
      <label for={`report-section-${app.id}`}><input id={`report-section-${app.id}`} type="checkbox"
        checked={app.keys.every((k) => selection[k])}
        onchange={(e) => { const next = { ...selection }; for (const k of app.keys) next[k] = e.currentTarget.checked; selection = next; }} />{t(`reportSelection.app.${app.id}` as MessageKey)}</label>
    {/each}
  </div>
  <p role="status">{t('reportSelection.pages', { pages: pages ?? t('reportSelection.updating') })}</p>
</section>

<style>
  .section-picker { padding: .5rem 0; }
  p { line-height: 1.5; }
  .items { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 0 1rem; }
  label { display: flex; align-items: center; gap: .6rem; min-height: 44px; line-height: 1.35; }
  input { flex: 0 0 auto; width: 1.2rem; height: 1.2rem; accent-color: #9bdfff; }
  input:focus-visible { outline: 2px solid #b1e6ff; outline-offset: 3px; }
  @media (max-width: 650px) { .items { grid-template-columns: 1fr; } }
</style>
