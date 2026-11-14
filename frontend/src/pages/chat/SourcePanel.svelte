<!-- SPDX-License-Identifier: Apache-2.0 -->
<!--
  Pannello fonte: finestra modale (pannello laterale da 640px in su, foglio dal basso sotto) che carica
  /api/assistant/knowledge/{id} e mostra titolo, tipo, sintesi e, per le formule, espressione, variabili,
  ipotesi, limiti, esempio svolto, derivazione, fonti e data di verifica. Focus intrappolato, Esc chiude,
  il focus torna al chip che l'ha aperto.
-->
<script lang="ts">
  import { onMount, onDestroy } from 'svelte';
  import { modal } from '../../shell/modal';
  import { fetchKnowledgeDoc, knowledgeKind, type DocResult, type KnowledgeDoc } from './assistant';
  import { t } from '../../i18n/i18n.svelte';
  import Answer from './Answer.svelte';

  let { id, anchor = '', trigger = null, onClose }: { id: string; anchor?: string; trigger?: HTMLElement | null; onClose: () => void } = $props();

  let result = $state<DocResult | null>(null);
  let ctrl: AbortController | null = null;

  async function load() {
    ctrl?.abort();
    ctrl = new AbortController();
    result = null;
    const r = await fetchKnowledgeDoc(fetch, id, ctrl.signal);
    if (r.ok === false && r.reason === 'aborted') return;
    result = r;
  }
  onMount(() => {
    void load();
  });
  onDestroy(() => ctrl?.abort());

  const fmt = (v: string | number) => String(v);
  const isUrl = (s: string) => /^https?:\/\/[^\s]+$/.test(s);
  /** [testo](kb:id) -> testo: i collegamenti interni del corpo non sono ancora navigabili qui. */
  const cleanBody = (b: string) => b.replace(/\[([^\]]+)\]\(kb:[^)]+\)/g, '$1');
  const heading = (d: KnowledgeDoc) => d.anchors.find((a) => a.anchor === anchor)?.heading ?? '';
</script>

<div class="source-overlay" role="dialog" aria-modal="true" aria-labelledby="src-title" use:modal={{ onClose, returnTo: trigger }}>
<div class="scrim" role="presentation" onclick={onClose}></div>
<div class="panel-wrap">
  <header class="head">
    <div class="head-text">
      <p class="eyebrow">{t('si.source')}</p>
      <h2 id="src-title">{result && result.ok ? result.doc.title : t('si.source')}</h2>
    </div>
    <button type="button" class="close" data-autofocus onclick={onClose} aria-label={t('si.closeSource')}>{t('si.close')}</button>
  </header>

  <div class="content">
    {#if result === null}
      <p role="status" class="muted">{t('si.sourceLoading')}</p>
    {:else if result.ok === false}
      <p role="alert" class="err">{result.message}</p>
      {#if result.reason === 'error'}<p><button type="button" onclick={() => void load()}>{t('shell.retry')}</button></p>{/if}
    {:else}
      {@const d = result.doc}
      <p class="meta">
        <span class="badge" data-kind={d.kind}>{knowledgeKind(d.kind)}</span>
        {#if d.level}<span class="muted">{t('si.documentLevel')} {d.level}</span>{/if}
        {#if d.last_verified}<span class="muted">{t('si.verified')} <time datetime={d.last_verified}>{d.last_verified}</time></span>{/if}
      </p>
      {#if anchor && heading(d)}<p class="small muted">{t('si.passage')}: {heading(d)}</p>{/if}
      {#if d.summary}<p class="summary">{d.summary}</p>{/if}

      {#if d.kind === 'formula' && d.expression}
        <section aria-labelledby="src-expr">
          <h3 id="src-expr">Formula</h3>
          <p class="formula"><code>{d.expression}</code></p>
        </section>
      {/if}

      {#if d.variables.length}
        <section aria-labelledby="src-vars">
          <h3 id="src-vars">{t('si.variables')}</h3>
          <!-- svelte-ignore a11y_no_noninteractive_tabindex -->
          <div class="table-scroll" tabindex="0" role="region" aria-label={t('si.variables')}>
            <table>
              <thead><tr><th scope="col">{t('si.symbol')}</th><th scope="col">{t('si.name')}</th><th scope="col">{t('si.unit')}</th><th scope="col">{t('si.range')}</th></tr></thead>
              <tbody>
                {#each d.variables as v, i (i)}
                  <tr><th scope="row"><code>{v.symbol}</code></th><td>{v.name}</td><td class="mono">{v.unit}</td><td>{v.range}</td></tr>
                {/each}
              </tbody>
            </table>
          </div>
        </section>
      {/if}

      {#if d.assumptions.length}
        <section aria-labelledby="src-ass">
          <h3 id="src-ass">{t('si.assumptions')}</h3>
          <ul>{#each d.assumptions as a, i (i)}<li>{a}</li>{/each}</ul>
        </section>
      {/if}
      {#if d.limits.length}
        <section aria-labelledby="src-lim">
          <h3 id="src-lim">{t('si.limits')}</h3>
          <ul>{#each d.limits as a, i (i)}<li>{a}</li>{/each}</ul>
        </section>
      {/if}

      {#if d.worked_example}
        {@const w = d.worked_example}
        <section aria-labelledby="src-ex">
          <h3 id="src-ex">{t('si.example')}</h3>
          <table>
            <caption class="visually-hidden">{t('si.example')}</caption>
            <thead><tr><th scope="col">{t('si.item')}</th><th scope="col">{t('si.value')}</th></tr></thead>
            <tbody>
              {#each Object.entries(w.inputs) as [k, v] (k)}<tr><th scope="row"><code>{k}</code> <span class="muted">{t('si.input')}</span></th><td class="mono num">{fmt(v)}</td></tr>{/each}
              {#each Object.entries(w.outputs) as [k, v] (k)}<tr><th scope="row"><code>{k}</code> <span class="muted">{t('si.output')}</span></th><td class="mono num">{fmt(v)}</td></tr>{/each}
            </tbody>
          </table>
          {#if w.note}<p class="small muted">{w.note}</p>{/if}
        </section>
      {/if}

      {#if d.derivation.length}
        <section aria-labelledby="src-der">
          <h3 id="src-der">{t('si.derivation')}</h3>
          <ol>{#each d.derivation as s, i (i)}<li>{s}</li>{/each}</ol>
        </section>
      {/if}

      {#if d.body.trim()}
        <details open={d.kind !== 'formula'}>
          <summary>{t('si.fullText')}</summary>
          <Answer text={cleanBody(d.body)} onCite={() => {}} />
        </details>
      {/if}

      <section aria-labelledby="src-src">
        <h3 id="src-src">{t('si.documentation')}</h3>
        {#if d.sources.length === 0}
          <p class="muted">{t('si.noSources')}</p>
        {:else}
          <ul class="sources">
            {#each d.sources as s, i (i)}
              <li>
                {#if isUrl(s.ref)}<a href={s.ref} target="_blank" rel="noopener noreferrer">{s.ref}<span class="visually-hidden"> ({t('si.newTab')})</span></a>{:else}<code>{s.ref}</code> <span class="muted">({t('si.repoFile')})</span>{/if}
                {#if s.supports}<br /><span class="small muted">{s.supports}</span>{/if}
              </li>
            {/each}
          </ul>
        {/if}
      </section>
    {/if}
  </div>
</div>
</div>

<style>
  .source-overlay { position: fixed; inset: 0; z-index: 200; }
  @media print { .source-overlay { display: none; } }
  .scrim {
    position: fixed;
    inset: 0;
    z-index: 190;
    background: var(--scrim-min);
    animation: fade var(--dur-ui) var(--ease-out);
  }
  .panel-wrap {
    position: fixed;
    z-index: 200;
    top: 0;
    right: 0;
    bottom: 0;
    width: min(34rem, 100vw);
    display: flex;
    flex-direction: column;
    background: var(--c-bg);
    color: var(--c-text);
    border-left: 1px solid var(--c-hairline);
    box-shadow: -8px 0 40px rgb(0 0 0 / 0.25);
    animation: slide-in var(--dur-ui) var(--ease-out);
  }
  .panel-wrap:focus {
    outline: none;
  }
  .head {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: var(--space-3);
    padding: var(--space-4) var(--space-4) var(--space-3);
    border-bottom: 1px solid var(--c-hairline);
  }
  .head-text {
    min-width: 0;
  }
  .eyebrow {
    margin: 0;
    font-size: var(--fs-micro);
    letter-spacing: 0.06em;
    text-transform: uppercase;
    color: var(--c-muted);
  }
  h2 {
    margin: 0;
    font-size: var(--fs-h3);
    font-stretch: 100%;
    overflow-wrap: anywhere;
  }
  h3 {
    margin: var(--space-4) 0 var(--space-2);
    font-size: 1rem;
    font-stretch: 100%;
  }
  .close {
    flex: none;
  }
  .content {
    flex: 1;
    overflow-y: auto;
    padding: var(--space-3) var(--space-4) var(--space-5);
    overscroll-behavior: contain;
  }
  .meta {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: var(--space-1) var(--space-3);
    margin: 0 0 var(--space-3);
    font-size: var(--fs-small);
  }
  .badge {
    padding: 0.1rem 0.7rem;
    border: 1px solid var(--c-link);
    border-radius: var(--radius-pill);
    color: var(--c-link);
    font-weight: 600;
  }
  .summary {
    margin: 0 0 var(--space-3);
  }
  .formula {
    margin: 0;
    padding: var(--space-3);
    background: var(--c-bg-alt);
    border-left: 3px solid var(--c-link);
    border-radius: var(--radius-sm);
    overflow-x: auto;
  }
  code,
  .mono {
    font-family: ui-monospace, 'SF Mono', Menlo, Consolas, 'Liberation Mono', monospace;
    font-variant-numeric: tabular-nums;
    font-size: 0.92em;
  }
  ul,
  ol {
    margin: 0;
    padding-left: 1.4em;
  }
  li + li {
    margin-top: var(--space-1);
  }
  .sources {
    list-style: none;
    padding: 0;
  }
  .sources li {
    overflow-wrap: anywhere;
  }
  details {
    margin-top: var(--space-4);
  }
  summary {
    cursor: pointer;
    min-height: var(--target);
    display: flex;
    align-items: center;
    font-weight: 600;
  }
  .err {
    margin-top: 0;
  }
  @keyframes slide-in {
    from {
      transform: translateX(2rem);
      opacity: 0;
    }
  }
  @keyframes slide-up {
    from {
      transform: translateY(2rem);
      opacity: 0;
    }
  }
  @keyframes fade {
    from {
      opacity: 0;
    }
  }
  /* telefono: foglio dal basso */
  @media (max-width: 639px) {
    .panel-wrap {
      top: auto;
      width: 100%;
      max-height: 88dvh;
      border-left: 0;
      border-top: 1px solid var(--c-hairline);
      border-radius: var(--radius-lg) var(--radius-lg) 0 0;
      box-shadow: 0 -8px 40px rgb(0 0 0 / 0.25);
      animation-name: slide-up;
    }
  }
</style>
