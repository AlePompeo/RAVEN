<!-- SPDX-License-Identifier: Apache-2.0 -->
<!--
  Indicatore grande del margine (semicerchio da -20 a +40 dB: rosso sotto 0, ambra 0-3 dB, verde sopra) con lo stato
  del link in parola + simbolo + colore, e accanto l'indicatore di validità con il perché. Mai il solo colore.
-->
<script lang="ts">
  import type { LinkState, ValidityLevel } from './linkModel';
  import { STR as S } from './simState';
  import { formatNumber, t } from '../../i18n/i18n.svelte';

  let {
    margin,
    state,
    validity,
    reasons,
    sentence,
  }: { margin: number; state: LinkState; validity: ValidityLevel; reasons: string[]; sentence: string } = $props();

  const fmt = (n: number, digits = 1) => formatNumber(n, { minimumFractionDigits: digits, maximumFractionDigits: digits });
  const STR = $derived({
    meter: t('sim.gauge.meter'),
    unit: 'dB',
    validity: t('sim.gauge.validity'),
  });
  const LO = -20;
  const HI = 40;
  const R = 90;
  const CX = 110;
  const CY = 104;
  const ang = (v: number) => Math.PI * (1 - (Math.min(HI, Math.max(LO, v)) - LO) / (HI - LO));
  const pt = (v: number, r = R): [number, number] => [CX + r * Math.cos(ang(v)), CY - r * Math.sin(ang(v))];
  function arc(a: number, b: number): string {
    const [x1, y1] = pt(a);
    const [x2, y2] = pt(b);
    return `M ${x1.toFixed(2)} ${y1.toFixed(2)} A ${R} ${R} 0 0 1 ${x2.toFixed(2)} ${y2.toFixed(2)}`;
  }
  const needle = $derived(pt(margin, R - 14));
  const st = $derived({ symbol: S.state[state].symbol, word: t(`sim.gauge.state.${state}`) });
  const va = $derived({
    symbol: S.validity[validity].symbol,
    word: t(`sim.gauge.validity.${validity}`),
    hint: t(`sim.gauge.hint.${validity}`),
  });
</script>

<div class="gauge" data-testid="gauge" data-state={state} data-margin={margin.toFixed(2)}>
  <div class="dial">
    <svg viewBox="0 0 220 112" aria-hidden="true" focusable="false">
      <path d={arc(LO, 0)} class="z z-red" />
      <path d={arc(0, 3)} class="z z-amber" />
      <path d={arc(3, HI)} class="z z-green" />
      <line x1={CX} y1={CY} x2={needle[0]} y2={needle[1]} class="needle" />
      <circle cx={CX} cy={CY} r="6" class="hub" />
    </svg>
    <div
      class="read"
      role="meter"
      aria-label={STR.meter}
      aria-valuemin={LO}
      aria-valuemax={HI}
      aria-valuenow={Math.round(Math.min(HI, Math.max(LO, margin)) * 10) / 10}
      aria-valuetext="{fmt(margin, 1)} dB, {st.word}"
    >
      <span class="big" dir="ltr" data-testid="gauge-margin">{margin >= 0 ? '+' : ''}{fmt(margin, 1)}</span><span class="u">{STR.unit}</span>
    </div>
    <p class="state" data-state={state} data-testid="gauge-state"><span aria-hidden="true">{st.symbol}</span> {st.word}</p>
  </div>
  <p class="sentence" data-testid="sentence">{sentence}</p>
  <div class="validity" data-level={validity} data-testid="validity">
    <p class="v-head"><span aria-hidden="true" class="v-sym">{va.symbol}</span> <strong>{STR.validity}: {va.word}</strong></p>
    {#if reasons.length}
      <ul data-testid="validity-reasons">{#each reasons as r (r)}<li>{r}</li>{/each}</ul>
    {:else}
      <p class="small">{va.hint}.</p>
    {/if}
  </div>
</div>

<style>
  .gauge {
    --c-warn: #a35200;
    display: grid;
    gap: var(--space-2);
  }
  @media (prefers-color-scheme: dark) {
    .gauge {
      --c-warn: #ffb340;
    }
  }
  :global(.tone-dark) .gauge {
    --c-warn: #ffb340;
  }
  .dial {
    position: relative;
    display: grid;
    justify-items: center;
  }
  svg {
    inline-size: min(100%, 22rem);
    block-size: auto;
  }
  .z {
    fill: none;
    stroke-width: 18;
  }
  .z-red {
    stroke: var(--c-danger);
  }
  .z-amber {
    stroke: var(--c-warn);
  }
  .z-green {
    stroke: var(--c-success);
  }
  .needle {
    stroke: var(--c-text);
    stroke-width: 4;
    stroke-linecap: round;
  }
  .hub {
    fill: var(--c-text);
  }
  .read {
    margin-block-start: -0.4rem;
    display: flex;
    align-items: baseline;
    gap: var(--space-1);
  }
  .big {
    font-size: clamp(2.6rem, 6vw, 3.6rem);
    font-weight: 700;
    line-height: 1;
    font-variant-numeric: tabular-nums;
  }
  .u {
    font-size: var(--fs-lead, 1.25rem);
    color: var(--c-muted);
  }
  .state {
    margin: var(--space-1) 0 0;
    font-size: var(--fs-h3, 1.4rem);
    font-weight: 700;
  }
  .state[data-state='open'] span {
    color: var(--c-success);
  }
  .state[data-state='transition'] span {
    color: var(--c-warn);
  }
  .state[data-state='blocked'] span {
    color: var(--c-danger);
  }
  .sentence {
    margin: 0;
    font-size: var(--fs-lead, 1.2rem);
    text-align: center;
  }
  .validity {
    border-inline-start: 6px solid var(--c-success);
    padding-inline-start: var(--space-3);
  }
  .validity[data-level='uncertain'] {
    border-inline-start-style: dashed;
    border-inline-start-color: var(--c-warn);
  }
  .validity[data-level='outside'] {
    border-inline-start-style: double;
    border-inline-start-color: var(--c-danger);
  }
  .v-head {
    margin: 0;
  }
  .validity ul,
  .validity .small {
    margin: var(--space-1) 0 0;
    padding-inline-start: var(--space-4);
    font-size: var(--fs-small, 0.9rem);
  }
  .validity .small {
    padding-inline-start: 0;
    color: var(--c-muted);
  }
</style>
