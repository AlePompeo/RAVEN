<!-- SPDX-License-Identifier: Apache-2.0 -->
<!--
  Stato dell'assistente in una riga: modalità estrattiva ("Risposte dal materiale del sito") o modello (llm).
  mode === 'checking': verifica in corso (riga già riservata, nessuno spostamento di layout).
  mode === null: stato non noto -> si presenta come servizio esterno (fail closed).
-->
<script lang="ts">
  import type { AssistantMode } from './assistant';
  import { t } from '../../i18n/i18n.svelte';

  let { mode, provider = '', model = '' }: { mode: AssistantMode | 'checking' | null; provider?: string; model?: string } = $props();
</script>

<p class="status-pill" data-state={mode === 'extractive' ? 'ok' : mode === 'checking' ? undefined : 'warn'} data-testid="assistant-mode">
  {#if mode === 'extractive'}
    {t('si.extractive')}
  {:else if mode === 'llm'}
    {t('si.generated')}{provider ? ` (${provider}${model ? ', ' + model : ''})` : ''}
  {:else if mode === 'checking'}
    {t('si.checking')}
  {:else}
    {t('si.unknown')}
  {/if}
</p>
