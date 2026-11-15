<!-- SPDX-License-Identifier: Apache-2.0 -->
<script lang="ts">
  import { onMount } from 'svelte';
  import { t } from '../../i18n/i18n.svelte';
  import { withBase } from '../../shell/router';
  import { loadLicenses, type LicensesResult } from './api';

  let result = $state<LicensesResult | null>(null);

  onMount(async () => {
    result = await loadLicenses(fetch);
  });
</script>

<div class="doc tile">
  <div class="container">
    <h1>{t('licenses.title')}</h1>
    <p>{t('licenses.intro')}</p>

    <h2>{t('licenses.assetsTitle')}</h2>
    <div class="table-scroll">
      <table>
        <caption>{t('licenses.assetsCaption')}</caption>
        <thead>
          <tr><th scope="col">{t('licenses.resource')}</th><th scope="col">{t('licenses.origin')}</th><th scope="col">{t('licenses.licence')}</th></tr>
        </thead>
        <tbody>
          <tr>
            <th scope="row">{t('licenses.hbSans')}</th>
            <td>{t('licenses.hbSansOrigin')}</td>
            <td>SIL Open Font License 1.1</td>
          </tr>
          <tr>
            <th scope="row">{t('licenses.orbitron')}</th>
            <td>The Orbitron Project Authors</td>
            <td><a href={withBase('/fonts/orbitron-OFL.txt', import.meta.env.BASE_URL)}>{t('licenses.ofl')}</a></td>
          </tr>
          <tr>
            <th scope="row">{t('licenses.earthrise')}</th>
            <td>{t('licenses.earthriseOrigin')}</td>
            <td>{t('licenses.publicDomain')}</td>
          </tr>
        </tbody>
      </table>
    </div>

    <h2>{t('licenses.softwareTitle')}</h2>

    {#if result === null}
      <p role="status">{t('licenses.loading')}</p>
    {:else if result.status === 'ok'}
      <div class="table-scroll">
        <table>
          <caption>{t('licenses.softwareCaption')}</caption>
          <thead>
            <tr><th scope="col">{t('licenses.component')}</th><th scope="col">{t('licenses.version')}</th><th scope="col">{t('licenses.licence')}</th></tr>
          </thead>
          <tbody>
            {#each result.entries as e (e.name + '@' + e.version)}
              <tr><th scope="row">{e.name}</th><td>{e.version}</td><td>{e.license}</td></tr>
            {/each}
          </tbody>
        </table>
      </div>
    {:else if result.status === 'error'}
      <p role="alert">{t('licenses.error')}</p>
    {:else if result.status === 'absent'}
      <p>{t('licenses.absent')}</p>
    {:else}
      <p>{t('licenses.empty')}</p>
    {/if}
  </div>
</div>
