<!-- SPDX-License-Identifier: Apache-2.0 -->
<script lang="ts">
  import { t } from '../../i18n/i18n.svelte';
  import { withBase } from '../../shell/router';

  const videoUrl = withBase('/raven-demo.mp4', import.meta.env.BASE_URL);
</script>

<div class="workspace tile tile--alt">
  <div class="container container--wide demo">
    <h1>{t('title.demo')}</h1>
    <!-- svelte-ignore a11y_media_has_caption: The supplied video has no audio track. -->
    <video controls playsinline preload="metadata" aria-label={t('demo.videoLabel')}>
      <source src={videoUrl} type="video/mp4" />
      {t('demo.videoUnsupported')}
    </video>
    <p><a href={videoUrl}>{t('demo.videoDownload')}</a></p>
  </div>
</div>

<style>
  .demo { padding-block: var(--space-7); }
  video {
    display: block;
    width: 100%;
    max-width: 72rem;
    background: #080b10;
    border: 1px solid var(--c-muted);
  }
</style>
