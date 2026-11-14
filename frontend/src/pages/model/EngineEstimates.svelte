<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- Quantities the model needs but no site provides, estimated by the RAVEN engine: an interval, its source and tag I. A bound
     that has no public source is shown as unknown, never as zero. These are not measurements at the site and not forecasts. -->
<script lang="ts">
  import { onMount } from 'svelte';
  import { t, formatNumber } from '../../i18n/i18n.svelte';
  import { raven, type EstBand, type RavenFresnelEstimate, type RavenLandingEstimate } from '../../shell/ravenApi';

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
  const n = (v: number | null, d = 2) => (v === null ? t('journey.unknown') : formatNumber(v, { maximumFractionDigits: d }));
  const range = (b: EstBand, d = 2, pct = false) => {
    if (b.min === null && b.typical === null && b.max === null) return t('journey.unknown');
    const f = (v: number | null) => (v === null ? t('journey.unknown') : pct ? `${formatNumber(v * 100, { maximumFractionDigits: 0 })} %` : n(v, d));
    return `${f(b.min)} – ${f(b.max)}${b.typical !== null ? ` (${t('est.typical')} ${f(b.typical)})` : ''}`;
  };
</script>

<section aria-labelledby="est-h" class="block" data-testid="engine-estimates">
  <h2 id="est-h">{t('est.title')}</h2>
  <p>{t('est.intro')}</p>
  {#if failed}<p role="alert">{t('est.failed')}</p>{/if}
  {#if fresnel}
    <h3>{t('est.fresnel')}</h3>
    <dl>
      <div><dt>{t('est.epsReal')}</dt><dd>{range(fresnel.eps_real)}</dd></div>
      <div><dt>{t('est.epsImag')}</dt><dd>{range(fresnel.eps_imag, 3)}</dd></div>
      <div><dt>{t('est.rough')}</dt><dd>{range(fresnel.roughness_rms_m)}</dd></div>
    </dl>
    <p class="small">{t('est.tag', { tag: fresnel.tag })} {fresnel.eps_real.source} {fresnel.limits}</p>
  {/if}
  {#if landing}
    <h3>{t('est.landing')}</h3>
    <dl>
      <div><dt>{t('est.attempts')}</dt><dd>{landing.attempts} ({landing.successes} {t('est.ok')}, {landing.ambiguous} {t('est.ambiguous')})</dd></div>
      <div><dt>{t('est.landingOk')}</dt><dd>{range(landing.landing_success, 2, true)}</dd></div>
      <div><dt>{t('est.landingFail')}</dt><dd>{range(landing.landing_failure, 2, true)}</dd></div>
      <div><dt>{t('est.parts')}</dt><dd>{t('journey.unknown')}</dd></div>
    </dl>
    <p class="small">{t('est.tag', { tag: landing.tag })} {landing.interval}. {landing.source}. {landing.limits}</p>
  {/if}
</section>

<style>
  dl { margin: 0 0 .5rem; } dl div { display: flex; flex-wrap: wrap; justify-content: space-between; gap: .75rem; padding-block: .25rem; border-bottom: 1px solid #9bdfff1a; }
  dt { color: var(--c-muted); } dd { margin: 0; font-variant-numeric: tabular-nums; text-align: right; }
  .small { font-size: .85rem; color: var(--c-muted); }
</style>
