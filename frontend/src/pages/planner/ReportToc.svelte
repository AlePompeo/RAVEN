<!-- SPDX-License-Identifier: Apache-2.0 -->
<script lang="ts">
  import { rt } from './reportText';
  import type { TocEntry } from './reportToc';
  let { entries }: { entries: TocEntry[] } = $props();
</script>

{#if entries.length}
  <nav class="report-toc" data-toc-skip aria-labelledby="report-toc-title" data-testid="report-toc">
    <h3 id="report-toc-title" data-toc-skip>{rt('toc')}</h3>
    <ol>
      {#each entries as entry (entry.id)}
        <li class={`toc-level-${entry.level}`}><a href={`#${entry.id}`}>{entry.text}</a></li>
      {/each}
    </ol>
  </nav>
{/if}

<style>
  .report-toc { margin-block: 4mm; }
  .report-toc h3 { margin: 0 0 2mm; }
  .report-toc ol { list-style: none; margin: 0; padding: 0; }
  .report-toc li { margin: .6mm 0; }
  .report-toc li.toc-level-2 { padding-inline-start: 5mm; font-size: .92em; }
  .report-toc a { color: inherit; text-decoration: none; }
  .report-toc a:hover { text-decoration: underline; }
</style>
