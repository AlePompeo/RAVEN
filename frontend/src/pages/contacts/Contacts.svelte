<!-- SPDX-License-Identifier: Apache-2.0 -->
<!--
  Pagina Contatti: il team, guidata dai dati (src/data/team.json, vedi src/data/README.md). Il JSON è importato solo
  qui, quindi sta nel chunk lazy della pagina. `window.__HB_TEAM__` è un aggancio per i test e2e: passa comunque
  dalla stessa validazione (parseTeam).
-->
<script lang="ts">
  import raw from '../../data/team.json';
  import MemberCard from './MemberCard.svelte';
  import { parseTeam } from './team';
  import { t } from '../../i18n/i18n.svelte';

  const override = (globalThis as { __HB_TEAM__?: unknown }).__HB_TEAM__;
  const members = parseTeam(override ?? raw);
</script>

<div class="doc tile">
  <div class="container container--wide">
    <h1>{t('trust.team.title')}</h1>
    <p class="lead">{t('trust.team.intro')}</p>

    {#if members.length}
      <ul class="team" aria-label={t('trust.team.members')}>
        {#each members as member (member.id)}
          <li><MemberCard {member} /></li>
        {/each}
      </ul>
    {:else}
      <p role="status">{t('trust.team.empty')}</p>
    {/if}

  </div>
</div>

<style>
  .lead {
    font-size: var(--fs-lead);
    margin-bottom: var(--space-5);
  }
  .team {
    list-style: none;
    margin: 0 0 var(--space-5);
    padding: 0;
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(min(100%, 20rem), 1fr));
    gap: var(--space-4);
  }
  .team li {
    display: flex;
    min-width: 0;
  }
  .team li > :global(.member) {
    flex: 1;
  }
  @media (min-width: 760px) {
    .team {
      grid-template-columns: repeat(2, minmax(0, 1fr));
    }
  }
</style>
