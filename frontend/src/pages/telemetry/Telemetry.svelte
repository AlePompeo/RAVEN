<!-- SPDX-License-Identifier: Apache-2.0 -->
<script lang="ts">
  import { onMount, onDestroy } from 'svelte';
  import type { Telemetry } from '../../contracts/telemetry';
  import type { LineChart } from '../../charts/lineChart';
  import SubNav from '../../components/ui/SubNav.svelte';
  import LinkCsv from './LinkCsv.svelte';
  import { createTelemetryClient, statusText, type ConnectionStatus } from './client';
  import { buildTable, pushSample, toChartData } from './table';
  import { modeNow } from '../../shell/modeState.svelte';
  import { setPageContext, clearPageContext } from '../../shell/pageContext.svelte';
  import { sanitizeParams } from '../chat/assistant';
  import { t } from '../../i18n/i18n.svelte';

  /**
   * Learning | Avanzato: stessi campioni. Learning mostra i valori correnti e il grafico con una frase semplice;
   * gli azimut di Sole e Terra sono in Avanzato; la tabella resta in entrambe (equivalente testuale del grafico).
   */
  const STR = {
    learn: 'i campioni del collegamento ricevuti dal flusso: potenza e margine del segnale verso la Terra. Sopra 0 dB il collegamento funziona.',
  } as const;

  let samples = $state<Telemetry[]>([]);
  let status = $state<ConnectionStatus>({ kind: 'connecting' });
  let chartEl: HTMLElement | undefined = $state();
  let chartError = $state(false);
  let linkContext = $state.raw<Record<string, string | number> | null>(null);
  let chart: LineChart | null = null;

  const table = $derived(buildTable(samples));
  const last = $derived(samples.at(-1));
  const pill = $derived(status.kind === 'open' ? 'ok' : status.kind === 'reconnecting' ? 'warn' : 'idle');
  const fmt = (v: number | undefined, d = 1) => (v === undefined ? '—' : v.toFixed(d));

  function updateLinkContext(params: Record<string, string | number> | null) {
    linkContext = params;
  }

  $effect(() => {
    const data = toChartData(samples);
    chart?.setData(data.time, [data.power_w, data.link_margin_db]);
  });

  $effect(() => {
    setPageContext({
      params: sanitizeParams({
        ...linkContext,
        stato_flusso: status.kind,
        provenienza: 'non specificata',
        istante_utc: last?.t_utc,
        sito: last?.site_id,
        potenza_w: last?.power_w,
        margine_db: last?.link_margin_db,
        elevazione_sole_gradi: last?.sun?.el_deg,
        elevazione_terra_gradi: last?.earth?.el_deg,
      }),
    });
  });
  onDestroy(clearPageContext);

  onMount(() => {
    let alive = true;
    const client = createTelemetryClient({
      onSample: (s) => (samples = pushSample(samples, s)),
      onStatus: (s) => (status = s),
    });
    client.start();

    /** Colori dai token (cambiano con lo schema): il grafico si ricrea al cambio di schema. */
    const build = () => {
      if (!chartEl) return;
      const el = chartEl;
      const css = getComputedStyle(el);
      const v = (name: string, fallback: string) => css.getPropertyValue(name).trim() || fallback;
      void import('../../charts/lineChart')
        .then(({ createLineChart }) =>
          createLineChart(el, {
            series: [
              { label: 'Potenza (W)', stroke: v('--c-power', '#b25000'), scale: 'w' },
              { label: 'Margine di link (dB)', stroke: v('--c-uplink', '#0066cc'), scale: 'db' },
            ],
            axisLabels: { w: 'W', db: 'dB' },
            axisStroke: v('--c-muted', '#6e6e73'),
            gridStroke: v('--c-hairline', '#d2d2d7'),
            font: `13px ${css.fontFamily || 'system-ui'}`,
          }),
        )
        .then((c) => {
          if (!alive) {
            c.destroy();
            return;
          }
          chart?.destroy();
          chart = c;
          const d = toChartData(samples);
          c.setData(d.time, [d.power_w, d.link_margin_db]);
        })
        .catch(() => (chartError = true));
    };
    build();
    const scheme = typeof window.matchMedia === 'function' ? window.matchMedia('(prefers-color-scheme: dark)') : null;
    scheme?.addEventListener('change', build);

    return () => {
      alive = false;
      scheme?.removeEventListener('change', build);
      client.stop();
      chart?.destroy();
      chart = null;
    };
  });
</script>

<SubNav title="Telemetria" learn={STR.learn}>
  {#snippet aside()}
    <p id="telemetry-status" class="status-pill" role="status" data-state={pill}>{statusText(status)}</p>
  {/snippet}
</SubNav>

<div class="workspace tile tile--alt">
  <div class="container container--wide grid">
    <p class="muted small" data-testid="telemetry-provenance">{t('telemetry.provenance')}</p>
    <LinkCsv onContext={updateLinkContext} />
    <section class="panel readouts-panel" aria-labelledby="now-h">
      <h2 id="now-h" class="visually-hidden">Ultimo campione</h2>
      <dl class="readouts">
        <div>
          <dt>Potenza</dt>
          <dd><span class="value num">{fmt(last?.power_w)}</span> <span class="unit">W</span></dd>
        </div>
        <div>
          <dt>Margine di link</dt>
          <dd><span class="value num">{fmt(last?.link_margin_db)}</span> <span class="unit">dB</span></dd>
        </div>
        <div>
          <dt>Sole</dt>
          <dd>
            <span class="value num">{fmt(last?.sun?.el_deg, 0)}</span><span class="unit">° alt.</span>
            {#if modeNow.advanced}<span class="sub num">az. {fmt(last?.sun?.az_deg, 0)}°</span>{/if}
          </dd>
        </div>
        <div>
          <dt>Terra</dt>
          <dd>
            <span class="value num">{fmt(last?.earth?.el_deg, 0)}</span><span class="unit">° alt.</span>
            {#if modeNow.advanced}<span class="sub num">az. {fmt(last?.earth?.az_deg, 0)}°</span>{/if}
          </dd>
        </div>
        <div>
          <dt>Sito</dt>
          <dd><span class="site">{last?.site_id ?? '—'}</span></dd>
        </div>
      </dl>
    </section>

    <section class="panel" aria-labelledby="chart-h">
      <h2 id="chart-h">Andamento</h2>
      <p class="legend small muted">
        <span class="key key--power" aria-hidden="true"></span>Potenza (W, asse sinistro)
        <span class="key key--link" aria-hidden="true"></span>Margine di link (dB, asse destro)
      </p>
      <div
        bind:this={chartEl}
        class="chart"
        role="group"
        aria-label="Grafico di potenza e margine di link nel tempo"
        aria-describedby={table.rows.length ? 'telemetry-table-caption' : undefined}
      ></div>
      {#if chartError}<p role="alert">Impossibile caricare il grafico: usa la tabella.</p>{/if}
    </section>

    <section class="panel" aria-labelledby="table-h">
      <h2 id="table-h">Ultimi campioni</h2>
      {#if table.rows.length === 0}
        <p class="muted">Nessun campione ricevuto. La tabella si riempie appena arriva il primo dato.</p>
      {:else}
        <div class="table-scroll">
          <table>
            <caption id="telemetry-table-caption"
              >{table.caption}. Equivalente testuale del grafico: potenza in W e margine di link in dB.</caption
            >
            <thead>
              <tr>{#each table.headers as h (h)}<th scope="col">{h}</th>{/each}</tr>
            </thead>
            <tbody>
              {#each table.rows as row, r (r)}
                <tr>
                  <th scope="row">{row[0]}</th>
                  {#each row.slice(1) as cell, i (i)}<td>{cell}</td>{/each}
                </tr>
              {/each}
            </tbody>
          </table>
        </div>
      {/if}
    </section>
  </div>
</div>

<style>
  .workspace {
    padding-block: var(--space-5) var(--space-7);
  }
  .grid {
    display: grid;
    /* minmax(0, 1fr): la traccia non si allarga al min-content del canvas uPlot (larghezza fissa in px) */
    grid-template-columns: minmax(0, 1fr);
    gap: var(--space-4);
  }
  .readouts {
    display: grid;
    grid-template-columns: repeat(5, minmax(0, 1fr));
    gap: var(--space-4);
    margin: 0;
  }
  dt {
    font-size: var(--fs-small);
    color: var(--c-muted);
  }
  dd {
    margin: var(--space-1) 0 0;
  }
  .value {
    font-size: var(--fs-readout);
    font-weight: 300;
    letter-spacing: -0.02em;
    line-height: 1.1;
  }
  .unit {
    color: var(--c-muted);
    margin-left: 0.15em;
  }
  .sub {
    display: block;
    font-size: var(--fs-small);
    color: var(--c-muted);
  }
  .site {
    display: inline-block;
    font-size: var(--fs-h3);
    font-weight: 600;
    margin-top: 0.6rem;
    overflow-wrap: anywhere;
  }
  .legend {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: var(--space-1) var(--space-2);
  }
  .key {
    display: inline-block;
    width: 1.25rem;
    height: 3px;
    border-radius: 2px;
    margin-left: var(--space-2);
  }
  .key:first-child {
    margin-left: 0;
  }
  .key--power {
    background: var(--c-power);
  }
  .key--link {
    background: var(--c-uplink);
  }
  .chart {
    min-height: 280px;
    width: 100%;
    min-width: 0;
    overflow: hidden;
  }
  /* la legenda interna di uPlot duplica quella sopra: nascosta */
  .chart :global(.u-legend) {
    display: none;
  }
  @media (max-width: 1067px) {
    .readouts {
      grid-template-columns: repeat(3, minmax(0, 1fr));
    }
  }
  @media (max-width: 639px) {
    .readouts {
      grid-template-columns: repeat(2, minmax(0, 1fr));
    }
  }
</style>
