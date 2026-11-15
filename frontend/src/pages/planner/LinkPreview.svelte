<!-- SPDX-License-Identifier: Apache-2.0 -->
<script lang="ts">
  import { onMount } from 'svelte';
  import { formatNumber, t, type MessageKey } from '../../i18n/i18n.svelte';
  import Gauge from '../simula/Gauge.svelte';
  import ValidityMap from '../simula/ValidityMap.svelte';
  import { computeLink, DEFAULT_INPUT, parseCompTable, validityHeat, type CompTable, type FlagCode, type LinkInput } from '../simula/linkModel';
  import { sentence } from '../simula/simState';

  let { radio }: { radio: { station: 'dsn34' | 'dsn18'; gain: number | null; rate: number | null; mast: number | null }; } = $props();
  let elevation = $state(1.5);
  let ridge = $state(33);
  let table = $state.raw<CompTable | null>(null);
  let tableFailed = $state(false);
  const validRadio = $derived(
    radio.gain !== null && Number.isFinite(radio.gain) && radio.gain >= -10 && radio.gain <= 45 &&
    radio.rate !== null && Number.isFinite(radio.rate) && radio.rate > 0 &&
    radio.mast !== null && Number.isFinite(radio.mast) && radio.mast >= 0.1 && radio.mast <= 100,
  );
  const input = $derived<LinkInput>({
    ...DEFAULT_INPUT,
    earthElDeg: elevation,
    ridgeHeightM: ridge,
    ...(validRadio ? { station: radio.station, gainDbi: radio.gain!, rateBps: radio.rate!, mastM: radio.mast! } : {}),
  });
  const result = $derived(computeLink(input, table));
  const heat = $derived.by(() => {
    const { earthElDeg: _el, ridgeHeightM: _ridge, ...rest } = input;
    const start = performance.now();
    const map = validityHeat(rest, table);
    return { map, ms: performance.now() - start };
  });
  const flags: Record<FlagCode, MessageKey> = {
    invalid_input: 'sim.state.flag.invalidInput',
    earth_below_horizon: 'sim.state.flag.earthBelowHorizon',
    paraxial: 'sim.state.flag.paraxial',
    nu_outside_table: 'sim.state.flag.nuOutsideTable',
    fresnel_oscillation: 'sim.state.flag.fresnelOscillation',
    d1_outside_table: 'sim.state.flag.d1OutsideTable',
    radius_unresolved: 'sim.state.flag.radiusUnresolved',
    reflection_beyond_ridge: 'sim.state.flag.reflectionBeyondRidge',
    correction_unavailable: 'sim.state.flag.correctionUnavailable',
  };
  const reasons = $derived(result.validity.reasons.map((code) => t(flags[code])));
  const said = $derived(sentence(result, {
    below: t('sim.state.sentence.below'),
    open: (margin, rate) => t('sim.state.sentence.open', { margin, rate }),
    transition: (margin, rate) => t('sim.state.sentence.transition', { margin, rate }),
    blockedSome: (margin, rate, maximum) => t('sim.state.sentence.blockedSome', { margin, rate, maximum }),
    blockedNone: (margin) => t('sim.state.sentence.blockedNone', { margin }),
  }, (value, digits) => formatNumber(value, { minimumFractionDigits: digits, maximumFractionDigits: digits })));

  onMount(() => {
    const controller = new AbortController();
    void fetch('/api/raven/compensation', { signal: controller.signal })
      .then((response) => {
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        return response.json();
      })
      .then((data: unknown) => {
        if (controller.signal.aborted) return;
        table = parseCompTable(data);
        tableFailed = table === null;
      })
      .catch(() => { if (!controller.signal.aborted) tableFailed = true; });
    return () => controller.abort();
  });
</script>

<section class="preview" aria-labelledby="link-preview-title" data-testid="planner-link-preview">
  <h2 id="link-preview-title">{t('planner.linkPreviewTitle')}</h2>
  <p>{t('planner.linkPreviewNote')}</p>
  {#if !validRadio}<p role="status">{t('planner.linkPreviewDefaults')}</p>{/if}
  {#if tableFailed}<p role="status">{t('sim.state.flag.correctionUnavailable')}</p>{/if}
  <div class="charts">
    <Gauge margin={result.marginDb} state={result.state} validity={result.validity.level} {reasons} sentence={said} />
    <ValidityMap heat={heat.map} el={elevation} {ridge} ms={heat.ms} onpick={(el, height) => { elevation = el; ridge = height; }} />
  </div>
</section>

<style>
  .preview { margin-block: var(--space-5); }
  .charts { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 2fr); gap: var(--space-5); align-items: start; }
  @media (max-width: 800px) { .charts { grid-template-columns: minmax(0, 1fr); } }
</style>
