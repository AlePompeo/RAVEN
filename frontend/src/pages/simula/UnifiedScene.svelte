<!-- SPDX-License-Identifier: Apache-2.0 -->
<script lang="ts">
  import { onMount, untrack } from 'svelte';
  import SimulaScene from './SimulaScene.svelte';
  import Lander from '../lander/Lander.svelte';
  import { t } from '../../i18n/i18n.svelte';
  import SubNav from '../../components/ui/SubNav.svelte';

  type SceneMode = 'didactic' | 'site' | 'analysis';
  function modeFromUrl(): SceneMode {
    const p = new URLSearchParams(location.search);
    if (p.get('scene') === 'analysis' || p.get('real') === '1') return 'analysis';
    if (p.get('scene') === 'site' || p.get('tab') === 'sito') return 'site';
    return 'didactic';
  }

  let mode = $state<SceneMode>(untrack(modeFromUrl));

  onMount(() => {
    const p = new URLSearchParams(location.search);
    if (p.get('tab') !== 'sito' && p.get('real') !== '1') return;
    p.set('tab', 'scena');
    p.set('scene', mode);
    history.replaceState(history.state, '', `${location.pathname}?${p}${location.hash}`);
  });

  function selectMode(value: SceneMode) {
    if (mode === value) return;
    mode = value;
    const p = new URLSearchParams(location.search);
    p.set('tab', 'scena');
    if (value === 'analysis') p.set('real', '1');
    else p.delete('real');
    if (value !== 'didactic') p.set('scene', value);
    else p.delete('scene');
    history.replaceState(history.state, '', `${location.pathname}?${p}${location.hash}`);
  }
</script>

<svelte:window onpopstate={() => (mode = modeFromUrl())} />

<SubNav title={mode === 'site' ? 'Scena lander' : 'Simulatore'} learn={t('scene.help')}>
  {#snippet toolbar()}
    <div class="scene-choice" role="group" aria-label={t('scene.choice')}>
      <button type="button" aria-pressed={mode === 'didactic'} onclick={() => selectMode('didactic')}>{t('scene.didactic')}</button>
      <button type="button" aria-pressed={mode !== 'didactic'} onclick={() => selectMode('site')}>{t('scene.real')}</button>
      {#if mode !== 'didactic'}
        <span class="separator" aria-hidden="true"></span>
        <button type="button" aria-pressed={mode === 'site'} onclick={() => selectMode('site')}>{t('scene.siteTime')}</button>
        <button type="button" aria-pressed={mode === 'analysis'} onclick={() => selectMode('analysis')}>{t('scene.analysis')}</button>
      {/if}
    </div>
  {/snippet}
</SubNav>
{#if mode === 'site'}
  <Lander embedded />
{:else if mode === 'analysis'}
  <SimulaScene embedded forceReal hideRealToggle />
{:else}
  <SimulaScene hideReal embedded />
{/if}

<style>
  .scene-choice {
    display: flex;
    flex: none;
    gap: var(--space-1);
  }
  button {
    min-height: 44px;
    border-radius: var(--radius-pill);
    padding-inline: 0.75rem;
    font-size: var(--fs-small);
    white-space: nowrap;
    cursor: pointer;
  }
  button[aria-pressed='true'] {
    background: var(--c-action);
    color: var(--c-on-action);
  }
  .separator {
    border-inline-start: 1px solid var(--c-hairline);
    margin-inline: var(--space-1);
  }
</style>
