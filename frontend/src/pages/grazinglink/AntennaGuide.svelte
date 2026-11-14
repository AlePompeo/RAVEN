<!-- SPDX-License-Identifier: Apache-2.0 -->
<script lang="ts">
  import { t } from '../../i18n/i18n.svelte';
</script>

<details class="antenna-guide" data-testid="antenna-guide">
  <summary>{t('antennaGuide.title')}</summary>
  <p>{t('antennaGuide.intro')}</p>
  <dl>
    <dt>{t('antennaGuide.omniTitle')}</dt><dd>{t('antennaGuide.omni')}</dd>
    <dt>{t('antennaGuide.patchTitle')}</dt><dd>{t('antennaGuide.patch')}</dd>
    <dt>{t('antennaGuide.dishTitle')}</dt><dd>{t('antennaGuide.dish')}</dd>
  </dl>
  <p>{t('antennaGuide.station')}</p>
  <p class="note">{t('antennaGuide.model')}</p>
</details>

<style>
  .antenna-guide { margin-block: 1rem; }
  summary { min-height: var(--target); display: list-item; padding-block: .6rem; cursor: pointer; font-weight: 600; }
  p, dd { max-inline-size: 72ch; line-height: 1.65; color: var(--c-muted); }
  dt { font-weight: 600; margin-block-start: 1rem; }
  dd { margin: .35rem 0 0; }
  .note { border-inline-start: 3px solid var(--c-power); padding-inline-start: 1rem; }
</style>
