<!-- SPDX-License-Identifier: Apache-2.0 -->
<script lang="ts">
  import { onMount } from 'svelte';
  import { withBase } from '../../shell/router';
  import { loadLicenses, type LicensesResult } from './api';

  let result = $state<LicensesResult | null>(null);

  onMount(async () => {
    result = await loadLicenses(fetch);
  });
</script>

<div class="doc tile">
  <div class="container">
    <h1>Licenze</h1>
    <p>Questo progetto e distribuito con licenza Apache-2.0. Qui sono elencate le componenti di terze parti incluse.</p>

    <h2>Carattere e immagini</h2>
    <div class="table-scroll">
      <table>
        <caption>Risorse grafiche incluse nell'interfaccia</caption>
        <thead>
          <tr><th scope="col">Risorsa</th><th scope="col">Origine</th><th scope="col">Licenza</th></tr>
        </thead>
        <tbody>
          <tr>
            <th scope="row">Carattere HB Sans</th>
            <td>Sottoinsieme latino di Mona Sans (The Mona Sans Project Authors), rinominato come richiesto dalla licenza</td>
            <td>SIL Open Font License 1.1</td>
          </tr>
          <tr>
            <th scope="row">Carattere Orbitron</th>
            <td>The Orbitron Project Authors</td>
            <td><a href={withBase('/fonts/orbitron-OFL.txt', import.meta.env.BASE_URL)}>SIL Open Font License 1.1</a></td>
          </tr>
          <tr>
            <th scope="row">Foto della Terra che sorge</th>
            <td>NASA, missione Apollo 8, 24 dicembre 1968 (AS08-14-2383)</td>
            <td>Pubblico dominio</td>
          </tr>
        </tbody>
      </table>
    </div>

    <h2>Componenti software</h2>

    {#if result === null}
      <p role="status">Caricamento...</p>
    {:else if result.status === 'ok'}
      <div class="table-scroll">
        <table>
          <caption>Componenti di terze parti e relative licenze</caption>
          <thead>
            <tr><th scope="col">Componente</th><th scope="col">Versione</th><th scope="col">Licenza</th></tr>
          </thead>
          <tbody>
            {#each result.entries as e (e.name + '@' + e.version)}
              <tr><th scope="row">{e.name}</th><td>{e.version}</td><td>{e.license}</td></tr>
            {/each}
          </tbody>
        </table>
      </div>
    {:else if result.status === 'error'}
      <p role="alert">Impossibile leggere l'elenco delle licenze (errore di rete o file non valido). Riprova piu tardi.</p>
    {:else if result.status === 'absent'}
      <p>
        L'elenco delle licenze di terze parti non e ancora disponibile: viene generato automaticamente durante la
        compilazione del progetto (CI).
      </p>
    {:else}
      <p>L'elenco delle licenze e stato letto ma non contiene componenti di terze parti.</p>
    {/if}
  </div>
</div>
