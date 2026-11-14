<!-- SPDX-License-Identifier: Apache-2.0 -->
<!--
  Selettore della lingua (docs/design/grazinglink-ux.md "Lingue", docs/i18n.md): pulsante con il nome della lingua
  corrente nella propria scrittura (globo + nome + freccia), bersaglio da 44 px. Apre la listbox di LanguageMenu.svelte,
  chunk lazy caricato al primo clic o alla freccia giù/su: nel bundle iniziale resta solo il pulsante.
  Nella barra a destra su schermi larghi; sotto 834 px in fondo al pannello del menu.
-->
<script lang="ts">
  import { tick, type Component } from 'svelte';
  import { LANGS, LANG_META } from '../i18n/locales';
  import { lang, t } from '../i18n/i18n.svelte';

  type MenuProps = { id: string; start: number; root: HTMLElement | undefined; onclose: (restoreFocus: boolean) => void };
  let { id = 'lang-switch' }: { id?: string } = $props();

  let open = $state(false);
  let opening = $state(false);
  let request = 0;
  let start = $state(0);
  let Menu = $state<Component<MenuProps> | null>(null);
  let root: HTMLElement | undefined = $state();
  let btn: HTMLButtonElement | undefined = $state();

  const meta = $derived(LANG_META[lang.current]);

  async function show(at = LANGS.indexOf(lang.current)) {
    const current = ++request;
    opening = true;
    try {
      Menu ??= (await import('./LanguageMenu.svelte')).default as Component<MenuProps>;
    } catch (error) {
      console.error('Unable to load language menu', error);
      return;
    } finally {
      if (current === request) opening = false;
    }
    if (current !== request) return;
    start = at;
    open = true;
    await tick();
  }

  function close(restore: boolean) {
    ++request;
    opening = false;
    open = false;
    if (restore) btn?.focus();
  }

  function onKey(e: KeyboardEvent) {
    if (e.key === 'Escape' && (open || opening)) {
      e.preventDefault();
      e.stopPropagation();
      close(true);
      return;
    }
    if (e.key !== 'ArrowDown' && e.key !== 'ArrowUp') return;
    e.preventDefault();
    e.stopPropagation();
    const i = LANGS.indexOf(lang.current);
    void show(e.key === 'ArrowUp' ? i - 1 : i);
  }
</script>

<svelte:document onpointerdown={(e) => {
  if (opening && root && e.target instanceof Node && !root.contains(e.target)) close(false);
}} />

<div class="lang-switch" bind:this={root} data-testid="lang-switch">
  <button
    bind:this={btn}
    type="button"
    class="lang-btn"
    aria-haspopup="listbox"
    aria-expanded={open}
    aria-controls={open ? `${id}-list` : undefined}
    onclick={() => (open || opening ? close(true) : void show())}
    onkeydown={onKey}
  >
    <svg class="globe" viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18ZM3 12h18M12 3c2.5 2.6 3.7 5.6 3.7 9s-1.2 6.4-3.7 9c-2.5-2.6-3.7-5.6-3.7-9S9.5 5.6 12 3Z" /></svg>
    <span class="visually-hidden">{t('lang.label')}</span>
    <span lang={meta.tag} dir={meta.dir}>{meta.native}</span>
    <span class="chev" aria-hidden="true"></span>
  </button>
  {#if open && Menu}<Menu {id} {start} {root} onclose={close} />{/if}
</div>

<style>
  .lang-switch {
    position: relative;
    flex: none;
  }
  .lang-btn {
    display: inline-flex;
    align-items: center;
    gap: 0.4rem;
    min-block-size: var(--target);
    min-inline-size: var(--target);
    margin: 0;
    padding-block: 0;
    padding-inline: 0.6rem;
    border: 0;
    background: transparent;
    color: #cccccc;
    font-size: var(--fs-small);
    white-space: nowrap;
  }
  .lang-btn:hover,
  .lang-btn[aria-expanded='true'] {
    color: var(--c-text);
  }
  .lang-btn:focus-visible {
    outline-offset: -4px;
  }
  .globe {
    inline-size: 1rem;
    block-size: 1rem;
    fill: none;
    stroke: currentColor;
    stroke-width: 1.5;
  }
  .chev {
    inline-size: 0.4rem;
    block-size: 0.4rem;
    /* freccia "giù": non direzionale, non si specchia */
    border-right: 1.5px solid currentColor;
    border-bottom: 1.5px solid currentColor;
    transform: translateY(-2px) rotate(45deg);
  }
  @media (max-width: 833px) {
    .lang-switch {
      margin-block-start: var(--space-4);
      padding-block-start: var(--space-3);
      border-block-start: 1px solid var(--c-hairline);
    }
    .lang-btn {
      padding-inline: 0;
      color: var(--c-text);
    }
  }
</style>
