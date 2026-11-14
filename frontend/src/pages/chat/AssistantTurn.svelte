<!-- SPDX-License-Identifier: Apache-2.0 -->
<!--
  Un turno dell'assistente: risposta (o scheda di rifiuto), elenco Fonti, avvisi, domande di approfondimento
  e azione Copia. Il testo in streaming NON sta in una regione live: l'annuncio arriva solo a fine risposta.
-->
<script lang="ts">
  import Answer from './Answer.svelte';
  import type { Turn } from './session.svelte';
  import { t } from '../../i18n/i18n.svelte';
  import { knowledgeKind } from './assistant';

  let {
    turn,
    starters = [],
    busy = false,
    onOpenSource,
    onAsk,
    onCopy,
  }: {
    turn: Turn;
    starters?: string[];
    busy?: boolean;
    onOpenSource: (id: string, anchor: string, trigger: HTMLElement) => void;
    onAsk: (q: string) => void;
    onCopy: (turn: Turn) => void;
  } = $props();

  // durante lo streaming valgono i documenti recuperati (meta); a fine risposta solo quelli davvero citati
  const known = $derived(new Set(turn.citations ? turn.citations.map((c) => c.id) : turn.retrieved));
  const titles = $derived(Object.fromEntries((turn.citations ?? []).map((c) => [c.id, c.title])));
  const anchorOf = (id: string) => turn.citations?.find((c) => c.id === id)?.anchor ?? '';
  const more = $derived(turn.followups.length ? turn.followups : turn.refused ? starters.slice(0, 3) : []);
</script>

<div class="turn" data-streaming={turn.streaming ? '1' : undefined}>
  <p class="who">RAVEN SI</p>

  {#if turn.refused && !turn.streaming}
    <div class="refusal" data-testid="refusal">
      <h3>{t('si.refusal')}</h3>
      <p>{t('si.refusalBody')}</p>
    </div>
  {:else if turn.content === '' && turn.streaming}
    <p class="muted" aria-hidden="true">{t('si.searching')}</p>
  {:else}
    <Answer text={turn.content} {known} {titles} onCite={(id, el) => onOpenSource(id, anchorOf(id), el)} />
    {#if turn.interrupted}<p class="small muted note">{t('si.partial')}</p>{/if}
  {/if}

  {#if turn.warnings.length}
    <ul class="warnings" aria-label={t('si.warnings')}>
      {#each turn.warnings as w, i (i)}<li data-code={w.code}>{w.text}</li>{/each}
    </ul>
  {/if}

  {#if turn.citations && turn.citations.length}
    <section class="sources" aria-label={t('si.sources')}>
      <p class="label">{t('si.sources')}</p>
      <ul>
        {#each turn.citations as c (c.id)}
          <li>
            <button type="button" class="src" aria-haspopup="dialog" onclick={(e) => onOpenSource(c.id, c.anchor, e.currentTarget)}>
              <span class="src-title">{c.title}</span>
              {#if c.kind}<span class="src-kind">{knowledgeKind(c.kind).toLocaleLowerCase()}</span>{/if}
            </button>
          </li>
        {/each}
      </ul>
    </section>
  {/if}

  {#if !turn.streaming && more.length}
    <ul class="chips" aria-label={t('si.followups')}>
      {#each more as q, i (i)}<li><button type="button" class="chip" aria-disabled={busy ? 'true' : undefined} onclick={() => !busy && onAsk(q)}>{q}</button></li>{/each}
    </ul>
  {/if}

  {#if !turn.streaming && turn.content && !turn.refused}
    <p class="actions"><button type="button" class="small-btn" onclick={() => onCopy(turn)}>{t('si.copy')}</button></p>
  {/if}
</div>

<style>
  .turn {
    display: grid;
    grid-template-columns: minmax(0, 1fr);
    gap: var(--space-3);
  }
  .turn > :global(*) {
    margin-block: 0;
  }
  .who {
    font-size: var(--fs-small);
    font-weight: 600;
  }
  .refusal {
    padding: var(--space-3) var(--space-4);
    border: 1px solid var(--c-hairline);
    border-left: 3px solid var(--c-muted);
    border-radius: var(--radius-md);
    background: var(--c-bg);
  }
  .refusal h3 {
    margin: 0 0 var(--space-2);
    font-size: 1.0625rem;
    font-stretch: 100%;
  }
  .refusal p {
    margin: 0 0 var(--space-2);
  }
  .warnings {
    list-style: none;
    margin: 0;
    padding: var(--space-2) var(--space-3);
    border-left: 3px solid var(--c-power);
    background: var(--c-bg);
    border-radius: 0 var(--radius-sm) var(--radius-sm) 0;
    font-size: var(--fs-small);
  }
  .warnings li + li {
    margin-top: var(--space-1);
  }
  .note {
    margin: 0;
  }
  .label {
    margin: 0 0 var(--space-1);
    font-size: var(--fs-small);
    font-weight: 600;
    color: var(--c-muted);
  }
  .sources ul,
  .chips {
    list-style: none;
    margin: 0;
    padding: 0;
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-2);
  }
  .src {
    max-width: 100%;
    padding: 0.35rem 1rem;
    text-align: left;
    gap: var(--space-2);
    border-radius: var(--radius-md);
    font-size: var(--fs-small);
  }
  .src-title {
    overflow-wrap: anywhere;
  }
  .src-kind {
    flex: none;
    font-size: var(--fs-micro);
    letter-spacing: 0.04em;
    text-transform: uppercase;
    color: var(--c-muted);
  }
  .chip {
    padding: 0.4rem 1rem;
    border-radius: var(--radius-md);
    font-size: var(--fs-small);
    text-align: left;
  }
  .chip[aria-disabled='true'] {
    opacity: 0.6;
  }
  .actions {
    margin: 0;
  }
  .small-btn {
    font-size: var(--fs-small);
  }
</style>
