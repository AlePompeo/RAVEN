<!-- SPDX-License-Identifier: Apache-2.0 -->
<script lang="ts">
  import { t } from '../../i18n/i18n.svelte';
  import { newReportSections, type ReportSections } from './reportSections';

  let { selection = $bindable(newReportSections()) }: { selection: ReportSections } = $props();

  function set(key: 'methodology' | 'reliability', checked: boolean): void {
    selection = { ...selection, [key]: checked };
  }

  function setParameters(checked: boolean): void {
    selection = { ...selection, configuration: checked, provenance: checked };
  }
</script>

<fieldset class="optional-report-sections" data-testid="report-optional-sections">
  <legend>{t('dossier.reportOptions')}</legend>
  <label><input id="report-option-methodology" type="checkbox" checked={selection.methodology}
    onchange={(event) => set('methodology', event.currentTarget.checked)} />{t('reportSelection.methodology')}</label>
  <label><input id="report-option-reliability" type="checkbox" checked={selection.reliability}
    onchange={(event) => set('reliability', event.currentTarget.checked)} />{t('reportSelection.app.reliability')}</label>
  <label><input id="report-option-parameters" type="checkbox" checked={selection.configuration && selection.provenance}
    onchange={(event) => setParameters(event.currentTarget.checked)} />{t('reportSelection.app.parameters')}</label>
</fieldset>

<style>
  fieldset { margin-block: 1.5rem; border: 1px solid #7b9cb36e; border-radius: .65rem; padding: 1rem; }
  label { display: flex; align-items: center; gap: .75rem; min-height: 44px; margin-block: .4rem; }
  input { flex: 0 0 auto; width: 1.2rem; height: 1.2rem; accent-color: #9bdfff; }
  input:focus-visible { outline: 2px solid #b1e6ff; outline-offset: 3px; }
</style>
