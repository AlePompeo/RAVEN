<!-- SPDX-License-Identifier: Apache-2.0 -->
<!--
  Laboratorio: strumenti per chi vuole andare a fondo (Telemetria, Simulazioni). Learning: una riga per strumento;
  Avanzato: anche cosa c'è sotto (sorgenti, contratti, limiti).
-->
<script lang="ts">
  import SubNav from '../../components/ui/SubNav.svelte';
  import Button from '../../components/ui/Button.svelte';
  import ModeOnly from '../../shell/ModeOnly.svelte';
  import { withBase } from '../../shell/router';
  import { t } from '../../i18n/i18n.svelte';

  const tools = [
    { id: 'telemetry', path: '/telemetry', name: 'title.telemetry', text: 'lab.telemetry.text', detail: 'lab.telemetry.detail', open: 'lab.telemetry.open' },
    { id: 'sims', path: '/sims', name: 'title.sims', text: 'lab.sims.text', detail: 'lab.sims.detail', open: 'lab.sims.open' },
  ] as const;
  const base = import.meta.env.BASE_URL;
</script>

<SubNav title={t('title.lab')} learn={t('lab.learn')} />

<div class="workspace tile tile--alt">
  <div class="container container--wide">
    <p class="lead">{t('lab.lead')}</p>
    <ul class="cards">
      {#each tools as tool (tool.id)}
        <li class="panel card" data-testid="lab-{tool.id}">
          <h2>{t(tool.name)}</h2>
          <p>{t(tool.text)}</p>
          <ModeOnly mode="avanzato"><p class="detail">{t(tool.detail)}</p></ModeOnly>
          <Button href={withBase(tool.path, base)}>{t(tool.open)}</Button>
        </li>
      {/each}
    </ul>
  </div>
</div>

<style>
  .workspace {
    padding-block: var(--space-5) var(--space-7, 4rem);
  }
  .lead {
    margin-block: 0 var(--space-4);
    max-inline-size: var(--measure);
  }
  .cards {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(min(100%, 20rem), 1fr));
    gap: var(--space-4);
    list-style: none;
    margin: 0;
    padding: 0;
  }
  .card {
    display: flex;
    flex-direction: column;
    align-items: flex-start;
    gap: var(--space-2);
  }
  .card h2 {
    margin: 0;
    font-size: var(--fs-h3);
  }
  .card p {
    margin: 0;
  }
  .detail {
    color: var(--c-muted);
    font-size: var(--fs-small);
  }
</style>
