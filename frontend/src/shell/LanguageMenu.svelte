<!-- SPDX-License-Identifier: Apache-2.0 -->
<!--
  Listbox del selettore della lingua (chunk lazy, caricato alla prima apertura da LanguageSwitch.svelte).
  Frecce su/giù, Home/Fine, Invio/Spazio sceglie, Esc chiude e ridà il focus al pulsante, Tab o un clic fuori chiudono.
  Ogni opzione porta il proprio `lang`/`dir`. Il cambio si annuncia nella regione #announcer, nella nuova lingua.
-->
<script lang="ts">
  import { onMount } from 'svelte';
  import { LANGS, LANG_META, type Lang } from '../i18n/locales';
  import { lang, setLang, t } from '../i18n/i18n.svelte';
  import { announce } from './a11y';

  let {
    id,
    start,
    root,
    onclose,
  }: { id: string; start: number; root: HTMLElement | undefined; onclose: (restoreFocus: boolean) => void } = $props();

  let active = $state(0);
  let list: HTMLUListElement | undefined = $state();

  function focusOpt(i: number) {
    active = (i + LANGS.length) % LANGS.length;
    list?.querySelectorAll<HTMLElement>('[role="option"]')[active]?.focus();
  }
  onMount(() => focusOpt(start));

  async function choose(l: Lang) {
    onclose(true);
    if (l === lang.current) return;
    if (await setLang(l)) announce(t('lang.changed', { language: LANG_META[l].native }));
  }

  function onKey(e: KeyboardEvent) {
    if (e.key === 'Tab') return onclose(false);
    const step: Record<string, () => void> = {
      ArrowDown: () => focusOpt(active + 1),
      ArrowUp: () => focusOpt(active - 1),
      Home: () => focusOpt(0),
      End: () => focusOpt(LANGS.length - 1),
      Enter: () => void choose(LANGS[active]!),
      ' ': () => void choose(LANGS[active]!),
      Escape: () => onclose(true),
    };
    const f = step[e.key];
    if (!f) return;
    e.preventDefault();
    e.stopPropagation(); // Esc non chiude anche il menu mobile; le frecce non arrivano alla navigazione TV
    f();
  }

  const outside = (n: EventTarget | null) => !!root && !!n && !root.contains(n as Node);
</script>

<svelte:document onpointerdown={(e) => outside(e.target) && onclose(false)} onfocusin={(e) => outside(e.target) && onclose(false)} />

<!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
<ul id={`${id}-list`} class="lang-list" role="listbox" aria-label={t('lang.menu')} bind:this={list} onkeydown={onKey}>
  {#each LANGS as l, i (l)}
    {@const m = LANG_META[l]}
    <!-- svelte-ignore a11y_click_events_have_key_events -->
    <li role="option" aria-selected={l === lang.current} tabindex={i === active ? 0 : -1} lang={m.tag} dir={m.dir} data-lang={l} onclick={() => void choose(l)}>
      <span class="name">{m.native}</span>
    </li>
  {/each}
</ul>

<style>
  .lang-list {
    position: absolute;
    z-index: 110;
    inset-block-start: calc(100% + 4px);
    inset-inline-end: 0;
    min-inline-size: 15rem;
    margin: 0;
    padding: var(--space-1);
    list-style: none;
    background: var(--c-raised, #1d1d1f);
    color: var(--c-text);
    border: 1px solid var(--c-hairline);
    border-radius: var(--radius-sm, 8px);
    box-shadow: 0 8px 28px rgb(0 0 0 / 0.4);
  }
  [role='option'] {
    display: flex;
    flex-direction: column;
    justify-content: center;
    min-block-size: var(--target);
    padding-block: 0.35rem;
    padding-inline: 0.75rem;
    border-radius: var(--radius-sm, 8px);
    cursor: pointer;
    text-align: start;
    font-size: var(--fs-small);
  }
  [role='option']:hover {
    background: rgb(255 255 255 / 0.08);
  }
  [role='option']:focus-visible {
    outline-offset: -2px;
  }
  [aria-selected='true'] .name {
    font-weight: 600;
  }
  [aria-selected='true'] .name::after {
    content: ' ✓' / '';
  }
  @media (max-width: 833px) {
    /* dentro il pannello del menu: in flusso, a tutta larghezza */
    .lang-list {
      position: static;
      min-inline-size: 0;
      margin-block-start: var(--space-2);
      box-shadow: none;
    }
  }
</style>
