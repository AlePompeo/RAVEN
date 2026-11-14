<!-- SPDX-License-Identifier: Apache-2.0 -->
<script lang="ts">
  import ravenMark from '../../assets/media/raven-mark.webp?no-inline';
  import { nf, rt } from './reportText';
  import type { CarbonEstimate } from './reportPlanning';
  import type { SimulatedCertificate } from './reportPresentation';

  let { carbon, certificate, certificateError = false }: {
    carbon: CarbonEstimate | null; certificate: SimulatedCertificate | null; certificateError?: boolean;
  } = $props();

  const avoided = $derived(carbon?.document.not_printing_avoided_kg_co2e ?? null);
  const pages = $derived(carbon?.document.compact_pages ?? null);
</script>

<section class="rp-digital-saving" data-testid="report-digital-savings" aria-labelledby="digital-saving-title">
  <h3 id="digital-saving-title">
    <svg class="leaf" viewBox="0 0 24 24" aria-hidden="true">
      <path d="M20.5 3.5C10 3.8 4 8.2 4 15.1c0 3 2 5 5 5 7 0 11.4-6 11.5-16.6Z" />
      <path d="M3 22c3.4-5.7 7.4-9.2 13.2-12.5" />
    </svg>
    {rt('digital.title')}
  </h3>
  {#if avoided !== null && pages !== null}
    <p>{rt('digital.value', { grams: nf(avoided * 1000, { maximumFractionDigits: 1 }), pages: nf(pages) })}</p>
  {:else}
    <p>{rt('digital.unknown')}</p>
  {/if}
  <p class="rp-digital-invitation">{rt('digital.invitation')}</p>
  <p class="rp-digital-scope">{rt('digital.scope')}</p>
</section>

<section class="signature rp-final-certificate" data-testid="report-final-seal" aria-labelledby="final-seal-title">
  <h3 id="final-seal-title">{rt('seal.title')}</h3>
  <div class="raven-seal-mark"><img src={ravenMark} alt="" width="88" height="44" /></div>
  <dl>
    <div><dt>{rt('seal.fingerprint')}</dt>
      <dd class="registry">{#if certificate}{certificate.payload_sha256}{:else}{rt(certificateError ? 'seal.error' : 'seal.pending')}{/if}</dd></div>
    <div><dt>{rt('seal.signature')}</dt><dd>{rt('seal.notIssued')}</dd></div>
    <div><dt>{rt('seal.blockchain')}</dt><dd>{rt('seal.notRegistered')}</dd></div>
    {#if certificate}
      <div><dt>{rt('seal.demoReference')}</dt><dd class="registry">{certificate.simulated_transaction_id}</dd></div>
    {/if}
  </dl>
  <p class="rp-seal-scope">{rt('seal.scope')}</p>
</section>
