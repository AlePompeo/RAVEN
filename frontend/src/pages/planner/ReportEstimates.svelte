<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- Part 3, last block: quantities the model needs but no site provides, estimated by the RAVEN engine (tag I): the regolith
     permittivity for the multipath term and the soft-landing transfer probability. An interval with its source; a bound with no
     public source is "unknown", never zero. Not a measurement at the site and not a forecast. Table layout (the PDF engine has no CSS grid). -->
<script lang="ts">
  import { onMount } from 'svelte';
  import { nf, rt } from './reportText';
  import { raven, type RavenFresnelEstimate, type RavenLandingEstimate } from '../../shell/ravenApi';
  import RangeChart from './RangeChart.svelte';
  import type { RangeRow } from './rangeRow';
  let { expert = true }: { expert?: boolean } = $props();

  let fresnel = $state.raw<RavenFresnelEstimate | null>(null);
  let landing = $state.raw<RavenLandingEstimate | null>(null);
  let failed = $state(false);
  onMount(() => {
    const ctl = new AbortController();
    void Promise.all([raven.fresnelEstimate({ signal: ctl.signal }), raven.landingEstimate({ signal: ctl.signal })]).then(([f, l]) => {
      if (ctl.signal.aborted) return;
      if (f.ok) fresnel = f.data;
      if (l.ok) landing = l.data;
      failed = !f.ok || !l.ok;
    });
    return () => ctl.abort();
  });

  const epsRows = $derived<RangeRow[]>(fresnel ? [
    { label: rt('est.row.epsReal'), min: fresnel.eps_real.min, typical: fresnel.eps_real.typical, max: fresnel.eps_real.max },
    { label: rt('est.row.epsImag'), min: fresnel.eps_imag.min, typical: fresnel.eps_imag.typical, max: fresnel.eps_imag.max },
  ] : []);
  const pct = (v: number | null) => (v === null ? null : v * 100);
  const landRows = $derived<RangeRow[]>(landing ? [
    { label: rt('est.row.success'), min: pct(landing.landing_success.min), typical: pct(landing.landing_success.typical), max: pct(landing.landing_success.max), highlight: true },
    { label: rt('est.row.failure'), min: pct(landing.landing_failure.min), typical: pct(landing.landing_failure.typical), max: pct(landing.landing_failure.max) },
  ] : []);
</script>

<div class="rp-est" data-testid="report-estimates">
  <h4 class="rp-means">{rt('est.title')}</h4>
  <p class="rp-how">{rt(expert ? 'est.intro' : 'est.intro.short')}</p>
  {#if failed}<p role="status" class="rp-how">{rt('est.failed')}</p>{/if}
  {#if fresnel}
    <RangeChart title={rt('est.q.fresnel')} unit={rt('est.unit.eps')} description={rt('est.d.fresnel')} rows={epsRows} digits={2} compact={!expert} />
    <p class="rp-how">{rt('est.rough')} {#if expert}{fresnel.eps_real.source} {fresnel.limits}{/if}</p>
  {/if}
  {#if landing}
    <RangeChart title={rt('est.q.landing')} unit="%" description={rt('est.d.landing')} rows={landRows} compact={!expert} />
    <p class="rp-how">{rt('est.landing.n', { n: nf(landing.attempts), ok: nf(landing.successes), amb: nf(landing.ambiguous) })} {rt('est.parts')}</p>
    {#if expert}<p class="rp-how">{landing.interval}. {landing.source}. {landing.limits}</p>{/if}
  {/if}
</div>
