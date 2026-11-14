<!-- SPDX-License-Identifier: Apache-2.0 -->
<script lang="ts">
  import Badge from './Badge.svelte';
  import ExportBar from './ExportBar.svelte';
  import { paramsCsv, toJson, type AnalysisResult } from './grazing';

  let { result, userProfile, syntheticMark }: { result: AnalysisResult; userProfile: boolean; syntheticMark: boolean } = $props();

  const fl = $derived(result.flags);
  const f = (v: number, d = 2) => v.toFixed(d).replace('.', ',');
  const synthetic = $derived(fl.terrain.synthetic || syntheticMark);
  const src = (t: string) => ({ lola: 'LOLA (PDS)', user: 'profilo fornito dall’utente', synthetic: 'profilo sintetico di prova' })[t] ?? t;
  const LIMITS_EXTRA = [
    'ITU-R P.526-9: par. 2.1, 2.7, 4.1, 4.2 verificati sul testo; la correzione della cresta è T(m,n) (eq. 28-32), non misurata.',
  ];
</script>

<h3>Segnalazioni dell’analisi</h3>
<dl class="flags">
  <div>
    <dt>Terreno</dt>
    <dd>
      {src(fl.terrain.source)}{fl.terrain.product_id ? `, prodotto ${fl.terrain.product_id}` : ''}; passo {f(fl.terrain.spacing_m, 1)} m.
      {#if synthetic}<strong class="warn" data-testid="synthetic-warning">Profilo sintetico di prova: non è un dato lunare.</strong>{/if}
      {#if userProfile && !synthetic}Profilo fornito dall’utente, non verificato.{/if}
    </dd>
  </div>
  <div><dt>Geometria della Terra</dt><dd>{fl.geometry_source}</dd></div>
  <div>
    <dt>Raggio della cresta risolto</dt>
    <dd>{fl.radius_resolved ? 'sì' : 'no'} ({(100 * fl.radius_resolved_fraction).toFixed(0)} % dei passi); raggio mediano {fl.ridge_radius_median_m === null ? 'non disponibile' : `${f(fl.ridge_radius_median_m, 1)} m`}. Se non risolto la correzione è una stima.</dd>
  </div>
  <div>
    <dt>Multipath</dt>
    <dd>{fl.multipath.status} ({(100 * fl.multipath.applicable_fraction).toFixed(0)} % dei passi). {fl.multipath.reason_not_applicable}</dd>
  </div>
  <div>
    <dt>Correzione della cresta</dt>
    <dd>{fl.correction.label}; stato «{fl.correction.status}»; anomalie {fl.correction.anomaly_steps}; incertezza massima {f(fl.correction.max_uncertainty_db)} dB.</dd>
  </div>
  <div>
    <dt>Incoerenza (correction_inconsistency)</dt>
    <dd><strong>{result.correction_inconsistency.status.split(':')[0]}</strong>: la tabella split-step arriva a {f(result.correction_inconsistency.table_max_db)} dB, il termine ITU-R P.526-9 T(m,n) (usato) a {f(result.correction_inconsistency.p526_max_db)} dB e JPL 42-226 dichiara {f(result.correction_inconsistency.jpl226_claim_db, 0)} dB. {result.correction_inconsistency.policy ?? ''}</dd>
  </div>
  <div>
    <dt>Geometria estrapolata (geometry_extrapolated_steps)</dt>
    <dd>{fl.correction.geometry_extrapolated_steps} passi fuori dall’intervallo di d1 della tabella.</dd>
  </div>
  <div>
    <dt>Passi bloccati, Terra sotto l’orizzonte</dt>
    <dd>{(100 * fl.blocked_fraction).toFixed(1)} % bloccati dalla cresta; {(100 * fl.earth_below_horizon_fraction).toFixed(1)} % con la Terra sotto l’orizzonte.</dd>
  </div>
</dl>

<h3>Limiti dichiarati</h3>
<ul class="limits" data-testid="declared-limits">
  {#each [...result.declared_limits, ...LIMITS_EXTRA] as l (l)}<li>{l}</li>{/each}
</ul>

<h3>Parametri usati</h3>
<ul class="legend small" aria-label="Legenda delle etichette">
  <li><Badge status="V" /> valore letto in una fonte primaria (con pagina)</li>
  <li><Badge status="D" /> derivato con formula ripetibile</li>
  <li><Badge status="I" /> illustrativo, nessuna fonte</li>
</ul>
<!-- svelte-ignore a11y_no_noninteractive_tabindex -->
<div class="table-scroll" tabindex="0" role="region" aria-label="Tabella dei parametri">
  <table data-testid="params-table">
    <caption>Parametri usati nell’analisi, con etichetta e fonte</caption>
    <thead><tr><th scope="col">Parametro</th><th scope="col">Valore</th><th scope="col">Etichetta</th><th scope="col">Fonte</th></tr></thead>
    <tbody>
      {#each result.parameters as p (p.key)}
        <tr>
          <th scope="row"><code>{p.key}</code></th>
          <td class="num">{p.value} {p.unit === '-' ? '' : p.unit}</td>
          <td><Badge status={p.status} /></td>
          <td class="src">{p.status === 'I' ? 'Illustrativo, senza fonte.' : p.source}</td>
        </tr>
      {/each}
    </tbody>
  </table>
</div>
<ExportBar name="raven-parametri" csv={() => paramsCsv(result.parameters)} json={() => toJson({ parameters: result.parameters, flags: result.flags, declared_limits: result.declared_limits, correction_inconsistency: result.correction_inconsistency })} />

<style>
  h3 {
    font-size: var(--fs-body);
    margin: var(--space-4) 0 var(--space-2);
  }
  .small {
    font-size: var(--fs-small);
  }
  .flags {
    margin: 0;
    display: grid;
    gap: var(--space-2);
    font-size: var(--fs-small);
  }
  .flags div {
    display: grid;
    grid-template-columns: minmax(8rem, 14rem) minmax(0, 1fr);
    gap: var(--space-3);
    border-top: 1px solid var(--c-hairline);
    padding-top: var(--space-2);
  }
  dt {
    font-weight: 600;
  }
  dd {
    margin: 0;
  }
  .warn {
    color: var(--c-danger);
  }
  .limits {
    margin: 0;
    padding-left: 1.2rem;
    display: grid;
    gap: var(--space-1);
    font-size: var(--fs-small);
  }
  .legend {
    list-style: none;
    margin: 0 0 var(--space-2);
    padding: 0;
    display: grid;
    gap: var(--space-1);
  }
  .src {
    font-size: var(--fs-small);
    color: var(--c-muted);
    overflow-wrap: anywhere;
  }
  td,
  th {
    padding-right: var(--space-3);
  }
  @media (max-width: 639px) {
    .flags div {
      grid-template-columns: minmax(0, 1fr);
      gap: var(--space-1);
    }
  }
</style>
