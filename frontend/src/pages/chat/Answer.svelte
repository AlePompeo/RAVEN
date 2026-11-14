<!-- SPDX-License-Identifier: Apache-2.0 -->
<!--
  Risposta dell'assistente: markdown-lite reso con elementi veri (mai {@html}). I marcatori [id] noti
  diventano pulsanti focalizzabili che aprono il pannello fonte; gli id ignoti restano testo.
-->
<script lang="ts">
  import { parseMarkdown, parseInline, type Inline } from './markdown';
  import { t } from '../../i18n/i18n.svelte';

  let {
    text,
    known = new Set<string>(),
    titles = {},
    onCite,
  }: {
    text: string;
    known?: ReadonlySet<string>;
    titles?: Record<string, string>;
    onCite: (id: string, trigger: HTMLElement) => void;
  } = $props();

  const blocks = $derived(parseMarkdown(text, known));
  const cells = (s: string): Inline[] => parseInline(s, known);
</script>

{#snippet inl(nodes: Inline[])}
  {#each nodes as n, i (i)}
    {#if n.t === 'text'}{n.v}{:else if n.t === 'code'}<code>{n.v}</code>{:else if n.t === 'bold'}<strong>{@render inl(n.c)}</strong>{:else}<button
        type="button"
        class="cite"
        aria-label={`${t('si.source')} ${n.id}: ${titles[n.id] ?? n.id}`}
        aria-haspopup="dialog"
        onclick={(e) => onCite(n.id, e.currentTarget)}>{n.id}</button
      >{/if}
  {/each}
{/snippet}

<div class="answer">
  {#each blocks as b, bi (bi)}
    {#if b.t === 'p'}
      <p>
        {#each b.lines as line, li (li)}{#if li > 0}<br />{/if}{@render inl(line)}{/each}
      </p>
    {:else if b.t === 'h'}
      <p class="sub"><strong>{@render inl(b.c)}</strong></p>
    {:else if b.t === 'ul'}
      <ul>
        {#each b.items as it, ii (ii)}<li>{@render inl(it)}</li>{/each}
      </ul>
    {:else if b.t === 'ol'}
      <ol>
        {#each b.items as it, ii (ii)}<li>{@render inl(it)}</li>{/each}
      </ol>
    {:else if b.t === 'pre'}
      <!-- svelte-ignore a11y_no_noninteractive_tabindex -->
      <pre tabindex="0" aria-label={t('si.textBlock')}>{b.v}</pre>
    {:else if b.t === 'formula'}
      <p class="formula"><span class="formula-label">Formula</span><code>{b.v}</code></p>
    {:else if b.t === 'vars'}
      <!-- svelte-ignore a11y_no_noninteractive_tabindex -->
      <div class="table-scroll" tabindex="0" role="region" aria-label={t('si.formulaVariables')}>
        <table class="mono">
          <caption class="visually-hidden">{t('si.variables')}</caption>
          <thead><tr><th scope="col">{t('si.symbol')}</th><th scope="col">{t('si.name')}</th><th scope="col">{t('si.unit')}</th><th scope="col">{t('si.range')}</th></tr></thead>
          <tbody>
            {#each b.rows as r, ri (ri)}
              <tr><th scope="row"><code>{r.symbol}</code></th><td class="plain">{r.name}</td><td>{r.unit}</td><td class="plain">{r.range}</td></tr>
            {/each}
          </tbody>
        </table>
      </div>
    {:else if b.t === 'table'}
      <!-- svelte-ignore a11y_no_noninteractive_tabindex -->
      <div class="table-scroll" tabindex="0" role="region" aria-label={t('si.table')}>
        <table class="mono">
          <thead><tr>{#each b.head as h, hi (hi)}<th scope="col">{h}</th>{/each}</tr></thead>
          <tbody>
            {#each b.rows as r, ri (ri)}
              <tr>{#each r as c, ci (ci)}<td class="plain">{@render inl(cells(c))}</td>{/each}</tr>
            {/each}
          </tbody>
        </table>
      </div>
      {#if b.after}<p>{@render inl(cells(b.after))}</p>{/if}
    {/if}
  {/each}
</div>

<style>
  .answer {
    overflow-wrap: anywhere;
  }
  .answer > :global(*:first-child) {
    margin-top: 0;
  }
  .answer > :global(*:last-child) {
    margin-bottom: 0;
  }
  p,
  ul,
  ol {
    margin: 0 0 var(--space-3);
  }
  ul,
  ol {
    padding-left: 1.4em;
  }
  li + li {
    margin-top: var(--space-1);
  }
  .sub {
    margin-top: var(--space-3);
  }
  code,
  pre {
    font-family: ui-monospace, 'SF Mono', Menlo, Consolas, 'Liberation Mono', monospace;
    font-variant-numeric: tabular-nums;
    font-size: 0.92em;
  }
  pre {
    margin: 0 0 var(--space-3);
    padding: var(--space-3);
    background: var(--c-bg);
    border: 1px solid var(--c-hairline);
    border-radius: var(--radius-sm);
    overflow-x: auto;
    white-space: pre;
  }
  .formula {
    display: grid;
    gap: var(--space-1);
    padding: var(--space-3);
    background: var(--c-bg);
    border: 1px solid var(--c-hairline);
    border-left: 3px solid var(--c-link);
    border-radius: var(--radius-sm);
  }
  .formula-label {
    font-size: var(--fs-micro);
    letter-spacing: 0.06em;
    text-transform: uppercase;
    color: var(--c-muted);
  }
  .formula code {
    font-size: 1.05em;
    overflow-x: auto;
    white-space: pre-wrap;
  }
  .table-scroll {
    margin: 0 0 var(--space-3);
  }
  /* le tabelle scorrono in orizzontale nella loro regione invece di spezzare le parole lettera per lettera */
  table.mono {
    min-width: 30rem;
    overflow-wrap: normal;
    word-break: normal;
  }
  table.mono td,
  table.mono th[scope='row'] {
    font-variant-numeric: tabular-nums;
  }
  table.mono td:not(.plain),
  table.mono code {
    font-family: ui-monospace, 'SF Mono', Menlo, Consolas, 'Liberation Mono', monospace;
  }
  /* chip di citazione: bersaglio nel testo (eccezione WCAG 2.5.8); l'area utile è allargata dal pseudo-elemento */
  .cite {
    position: relative;
    display: inline;
    min-height: 0;
    margin: 0 0.1em;
    padding: 0.05em 0.5em;
    font: inherit;
    font-size: 0.8em;
    font-weight: 600;
    line-height: 1.5;
    letter-spacing: 0;
    color: var(--c-link);
    background: var(--c-bg);
    border: 1px solid var(--c-link);
    border-radius: var(--radius-pill);
    cursor: pointer;
    vertical-align: baseline;
  }
  .cite::after {
    content: '';
    position: absolute;
    inset: -0.7em -0.3em;
  }
  .cite:hover {
    text-decoration: underline;
  }
</style>
