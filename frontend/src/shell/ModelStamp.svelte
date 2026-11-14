<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- Dichiara il modello da cui escono i numeri della pagina: versione e registro dei parametri (una sola richiesta, in cache). -->
<script lang="ts">
  import { onMount } from 'svelte';
  import { t } from '../i18n/i18n.svelte';
  import { raven } from './ravenApi';

  let { note = '' }: { note?: string } = $props();
  let stamp = $state<{ version: string; registry: string } | null>(null);
  let alive = true;
  onMount(() => {
    void raven.model().then((r) => {
      if (alive && r.ok && typeof r.data.model_version === 'string') {
        stamp = { version: r.data.model_version, registry: String(r.data.registry_sha256 ?? '').slice(0, 12) };
      }
    });
    return () => { alive = false; };
  });
</script>

{#if stamp}
  <p class="model-stamp muted small" data-testid="model-stamp" data-model-version={stamp.version}>{t('model.version', { version: stamp.version, hash: stamp.registry })}{note ? ` ${note}` : ''}</p>
{/if}
