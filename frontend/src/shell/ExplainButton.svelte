<!-- SPDX-License-Identifier: Apache-2.0 -->
<!--
  RAVEN SI: persistent launcher; the conversation UI is lazy-loaded on first opening.
  Scorciatoie: Alt+A sempre; il tasto "?" solo se l'utente lo attiva nel foglio (WCAG 2.1.4).
-->
<script lang="ts">
  import type { Component } from 'svelte';
  import { explainPrefs } from './pageContext.svelte';
  import { t } from '../i18n/i18n.svelte';

  let { pageId, inert = false, dark = false }: { pageId: string; inert?: boolean; dark?: boolean } = $props();

  let open = $state(false);
  let Sheet = $state<Component<{ pageId: string; onClose: () => void }> | null>(null);
  let failed = $state(false);

  async function show() {
    if (pageId === 'chat') { document.getElementById('chat-input')?.focus(); return; }
    if (open) return;
    failed = false;
    if (!Sheet) {
      try {
        Sheet = (await import('./ExplainSheet.svelte')).default as Component<{ pageId: string; onClose: () => void }>;
      } catch {
        failed = true;
        return;
      }
    }
    open = true;
  }

  const typing = (t: EventTarget | null) => {
    const el = t as HTMLElement | null;
    return !!el && (el.isContentEditable || ['INPUT', 'TEXTAREA', 'SELECT'].includes(el.tagName));
  };

  function onKeydown(e: KeyboardEvent) {
    if (e.defaultPrevented || open || inert) return;
    if (e.altKey && !e.ctrlKey && !e.metaKey && e.code === 'KeyA') {
      e.preventDefault();
      void show();
    } else if (explainPrefs.questionKey && e.key === '?' && !e.altKey && !e.ctrlKey && !e.metaKey && !typing(e.target)) {
      e.preventDefault();
      void show();
    }
  }
</script>

<svelte:window onkeydown={onKeydown} />

<div class="explain" class:tone-dark={dark} {inert}>
  <button type="button" class="explain-btn" aria-haspopup="dialog" aria-expanded={open} aria-label="RAVEN SI" aria-keyshortcuts="Alt+A" data-nav-last data-testid="raven-si-launcher" onclick={show}>
    <svg class="icon" viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M20 11a8 8 0 0 1-8 8H5l-3 3V11a9 9 0 0 1 18 0ZM7 11h8M7 7h5" /></svg>
    <span class="full">{t('explain.button')}</span>
    <span class="short" aria-hidden="true">{t('explain.short')}</span>
  </button>
  {#if failed}<p role="alert" class="fail">{t('explain.fail')}</p>{/if}
</div>

{#if open && Sheet}
  <Sheet {pageId} onClose={() => (open = false)} />
{/if}

<style>
  .icon {
    flex: none;
    width: var(--icon-size, 1.25rem);
    height: var(--icon-size, 1.25rem);
    fill: none;
    stroke: currentColor;
    stroke-width: 1.5;
    stroke-linecap: round;
    stroke-linejoin: round;
    vector-effect: non-scaling-stroke;
  }
  .explain {
    position: fixed;
    z-index: 45;
    inset-inline-end: max(var(--space-3), env(safe-area-inset-right));
    bottom: max(var(--space-3), env(safe-area-inset-bottom));
    display: grid;
    justify-items: end;
    gap: var(--space-2);
    pointer-events: none;
  }
  .explain-btn,
  .fail {
    pointer-events: auto;
  }
  .explain-btn {
    background: #14243a;
    color: #e2efff;
    border: 1px solid #8ab3db;
    padding: .8rem 1.1rem;
    border-radius: 999px;
    font-weight: 600;
    letter-spacing: .04em;
    box-shadow: 0 4px 24px #0006, 0 0 16px #75b8ff16;
  }
  .short {
    display: none;
  }
  .fail {
    margin: 0;
    max-width: 18rem;
    padding: var(--space-2) var(--space-3);
    background: var(--c-raised);
    border-radius: var(--radius-sm);
    font-size: var(--fs-small);
  }
  /* 10 feet: no floating element until the remote reaches it (it is the last stop of the arrow navigation) */
  :global(html[data-tv='1']) .explain-btn:not(:focus-visible) { opacity: 0; }
  @media print { .explain { display: none !important; } }
</style>
