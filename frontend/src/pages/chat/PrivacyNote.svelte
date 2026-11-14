<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- Avviso di privacy: visibile quando il testo può lasciare il computer (modello non verificato come locale, o stato ignoto). -->
<script lang="ts">
  import Callout from '../../components/ui/Callout.svelte';
  import { sendsTextOutside, type AssistantMode } from './assistant';
  import { t } from '../../i18n/i18n.svelte';

  let { mode, provider = '', external = null, id = 'assistant-privacy' }: { mode: AssistantMode | 'checking' | null; provider?: string; external?: boolean | null; id?: string } = $props();
  const show = $derived(mode !== 'checking' && sendsTextOutside(mode, provider, external));
</script>

{#if show}
  <Callout kind="warning" {id}>
    <p>{t('si.privacy')} {provider ? `(${provider})` : ''}</p>
  </Callout>
{/if}
