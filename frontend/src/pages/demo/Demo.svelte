<!-- SPDX-License-Identifier: Apache-2.0 -->
<script lang="ts">
  import { t } from '../../i18n/i18n.svelte';
</script>

<div class="workspace tile tile--alt">
  <div class="container container--wide demo">
    <h1>{t('title.demo')}</h1>
    <div class="video-placeholder" role="img" aria-label={t('demo.videoPlaceholder')}>
      <p>{t('demo.videoPlaceholder')}</p>
    </div>
  </div>
</div>

<style>
  .demo { padding-block: var(--space-7); }
  .video-placeholder {
    display: grid;
    place-items: center;
    aspect-ratio: 16 / 9;
    max-width: 72rem;
    background: #080b10;
    border: 1px solid var(--c-muted);
    color: #fff;
    text-align: center;
    padding: var(--space-4);
  }
</style>
