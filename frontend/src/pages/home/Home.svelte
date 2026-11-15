<!-- SPDX-License-Identifier: Apache-2.0 -->
<script lang="ts">
  import { onMount, type Component } from 'svelte';
  import { withBase } from '../../shell/router';
  import Hero from '../../components/ui/Hero.svelte';
  import MediaFrame from '../../components/ui/MediaFrame.svelte';
  import Button from '../../components/ui/Button.svelte';
  import MoonStage from './MoonStage.svelte';
  import earthWide1280 from '../../assets/media/earthrise-wide-1280.webp';
  import earthWide1920 from '../../assets/media/earthrise-wide-1920.webp';
  import earthWideJpg from '../../assets/media/earthrise-wide-1280.jpg';
  import earthPortrait860 from '../../assets/media/earthrise-portrait-860.webp';
  import ravenLogo from '../../assets/media/raven-logo.webp';
  import { formatNumber, lang, t } from '../../i18n/i18n.svelte';
  import { modeNow } from '../../shell/modeState.svelte';
  import { missionStrip, runs, STRIP_DAYS, STRIP_INPUT } from './missionStrip';
  import { scenarioStore, withScenario, type Scenario } from '../../shell/scenario';

  const base = import.meta.env.BASE_URL;
  const href = (p: string) => withBase(p, base);
  const store = scenarioStore();
  let scenario = $state<Scenario>(store.reload());
  $effect(() => store.subscribe((s) => (scenario = s)));

  const STR = $derived({
    storyTitle: t('home.story.title'),
    learn: t('home.story.learn'),
    steps: {
      horizon: {
        title: t('home.story.horizon.title'),
        text: t('home.story.horizon.text'),
        tech: t('home.story.horizon.tech'),
      },
      ridge: {
        title: t('home.story.ridge.title'),
        text: t('home.story.ridge.text'),
        tech: t('home.story.ridge.tech'),
        clear: t('home.story.ridge.clear'),
        bent: t('home.story.ridge.bent'),
      },
      compute: {
        title: t('home.story.compute.title'),
        text: t('home.story.compute.text'),
        tech: t('home.story.compute.tech'),
        loading: t('home.story.compute.loading'),
      },
      mission: {
        title: t('home.story.mission.title'),
        text: t('home.story.mission.text'),
        tech: t('home.story.mission.tech'),
        geo: t('home.story.mission.geo'),
        real: t('home.story.mission.real'),
        gained: t('home.story.mission.gained'),
        hours: (n: number) => t('home.story.mission.hours', { n: formatNumber(n) }),
        summary: (g: number, r: number, days: number) =>
          t('home.story.mission.summary', { g: formatNumber(g), r: formatNumber(r), days: formatNumber(days) }),
        illustrative: t('home.story.mission.illustrative'),
        sites: t('home.story.mission.sites'),
      },
    },
    stackTitle: t('home.story.stackTitle'),
    stack: t('home.story.stack'),
  });
  const ST = $derived(STR.steps);

  // passo 4: un mese illustrativo con lo stesso modello del mini-simulatore (tabella della correzione non caricata: dichiarato)
  const strip = missionStrip(STRIP_INPUT);
  const stripRuns = runs(strip.cells);
  const N = strip.cells.length;

  // mini-simulatore: chunk pigro, caricato quando la sezione si avvicina allo schermo
  let miniHost: HTMLElement | undefined = $state();
  let Mini = $state<Component | null>(null);
  onMount(() => {
    const load = () => void import('./MiniSim.svelte').then((m) => (Mini = m.default));
    if (typeof IntersectionObserver === 'undefined' || !miniHost) {
      load();
      return;
    }
    const io = new IntersectionObserver(
      (es) => {
        if (es.some((e) => e.isIntersecting)) {
          io.disconnect();
          load();
        }
      },
      { rootMargin: '600px 0px' },
    );
    io.observe(miniHost);
    return () => io.disconnect();
  });
</script>

<Hero labelledby="home-title" class="home-hero" align="end">
  {#snippet media()}<MoonStage />{/snippet}
  <div class="hero-copy">
    <h1 id="home-title" class="display"><img src={ravenLogo} alt="" width="800" height="550" /><span class="visually-hidden">RAVEN</span></h1>
    <p class="hero-lead">{t('home.question')}</p>
    <p class="hero-support">{t('home.pitch')}</p>
    <p class="hero-actions">
      <Button href={href('/simula')} size="lg">{t('home.try')}</Button>
      <Button href={href(withScenario('/mission-planner', scenario))} size="lg" variant="ghost"><span lang={lang.current}>{t('journey.homePlanner')}</span></Button>
      <Button href={href('/demo')} size="lg" variant="ghost">{t('home.demo')}</Button>
      <Button href={href('/about')} size="lg" variant="ghost">{t('nav.about')}</Button>
    </p>
  </div>
</Hero>

<section id="come-funziona" class="story-intro tile" aria-labelledby="story-h" tabindex="-1">
  <div class="container container--wide">
    <h2 id="story-h" class="chapter-title">{STR.storyTitle}</h2>
    {#if !modeNow.advanced}<p class="learn" data-testid="learn-line"><strong>{t('mode.whatYouSee')}</strong> {STR.learn}</p>{/if}
  </div>
</section>

<!-- Passo 1: foto a tutto schermo, testo sul cielo nero con scrim -->
<section class="earth tone-dark step" aria-labelledby="step-horizon-h" data-testid="step-horizon">
  <MediaFrame
    src={earthWideJpg}
    alt={t('home.story.earthAlt')}
    width={1280}
    height={747}
    sources={[
      { srcset: `${earthPortrait860} 860w`, type: 'image/webp', media: '(max-aspect-ratio: 4/5)' },
      { srcset: `${earthWide1280} 1280w, ${earthWide1920} 1920w`, type: 'image/webp' },
    ]}
    fx="settle"
    class="earth-media"
  />
  <div class="earth-scrim" aria-hidden="true"></div>
  <div class="container container--wide earth-copy">
    <h2 id="step-horizon-h" class="step-title">{ST.horizon.title}</h2>
    <p class="step-text">{ST.horizon.text}</p>
    {#if modeNow.advanced}<p class="step-tech" data-testid="tech-line">{ST.horizon.tech}</p>{/if}
  </div>
  <p class="earth-credit">{t('home.story.earthCredit')}</p>
</section>

<!-- Passo 2: linea di vista contro diffrazione -->
<section class="tile tile--alt step" aria-labelledby="step-ridge-h" data-testid="step-ridge">
  <div class="container container--wide split">
    <div>
      <h2 id="step-ridge-h" class="step-title">{ST.ridge.title}</h2>
      <p class="step-text">{ST.ridge.text}</p>
      {#if modeNow.advanced}<p class="step-tech" data-testid="tech-line">{ST.ridge.tech}</p>{/if}
    </div>
    <div class="duo">
      {#each [false, true] as bent (bent)}
        <figure class="diag">
          <svg viewBox="0 0 240 120" aria-hidden="true" focusable="false">
            <rect width="240" height="120" fill="#000" />
            <path d="M0 104 L80 104 Q120 {bent ? 52 : 74} 160 104 L240 104 L240 120 L0 120 Z" fill="#5b5955" stroke="#a9a59d" stroke-width="1.5" />
            <circle cx="222" cy={bent ? 92 : 30} r="11" fill="#2f6fd1" />
            <rect x="12" y="92" width="14" height="10" fill="#d9b24a" />
            <line x1="19" y1="92" x2="19" y2="84" stroke="#d9b24a" stroke-width="2" />
            {#if bent}
              <line x1="19" y1="84" x2="222" y2="92" stroke="#fff" stroke-width="1.2" stroke-dasharray="5 4" opacity="0.7" />
              <path d="M19 84 L120 78 L222 92" fill="none" stroke="#ffb340" stroke-width="3" stroke-dasharray="8 5" />
            {:else}
              <path d="M19 84 L222 30" fill="none" stroke="#30d158" stroke-width="3" />
            {/if}
          </svg>
          <figcaption>{bent ? ST.ridge.bent : ST.ridge.clear}</figcaption>
        </figure>
      {/each}
    </div>
  </div>
</section>

<!-- Passo 3: cosa calcola, con il mini-simulatore dal vivo -->
<section class="tile step" aria-labelledby="step-compute-h" data-testid="step-compute">
  <div class="container container--wide">
    <h2 id="step-compute-h" class="step-title">{ST.compute.title}</h2>
    <p class="step-text narrow">{ST.compute.text}</p>
    {#if modeNow.advanced}<p class="step-tech narrow" data-testid="tech-line">{ST.compute.tech}</p>{/if}
    <div class="mini-slot" bind:this={miniHost} data-ready={Mini ? '1' : '0'}>
      {#if Mini}<Mini />{:else}<p class="small">{ST.compute.loading}</p>{/if}
    </div>
  </div>
</section>

<!-- Passo 4: finestre di contatto in un mese illustrativo -->
<section class="tile tile--alt step" aria-labelledby="step-mission-h" data-testid="step-mission">
  <div class="container container--wide">
    <h2 id="step-mission-h" class="step-title">{ST.mission.title}</h2>
    <p class="step-text narrow">{ST.mission.text}</p>
    {#if modeNow.advanced}<p class="step-tech narrow" data-testid="tech-line">{ST.mission.tech}</p>{/if}
    <figure class="strip">
      <div class="strip-row">
        <span class="strip-label">{ST.mission.geo}</span>
        <svg viewBox="0 0 {N} 10" preserveAspectRatio="none" aria-hidden="true" focusable="false">
          {#each stripRuns.filter((r) => r.v === 2) as r (r.start)}<rect x={r.start} width={r.len} height="10" class="s-open" />{/each}
        </svg>
        <span class="strip-n" dir="ltr">{ST.mission.hours(strip.geometricHours)}</span>
      </div>
      <div class="strip-row">
        <span class="strip-label">{ST.mission.real}</span>
        <svg viewBox="0 0 {N} 10" preserveAspectRatio="none" aria-hidden="true" focusable="false">
          {#each stripRuns.filter((r) => r.v > 0) as r (r.start)}<rect x={r.start} width={r.len} height="10" class={r.v === 1 ? 's-trans' : 's-open'} />{/each}
        </svg>
        <span class="strip-n" dir="ltr">{ST.mission.hours(strip.realHours)}</span>
      </div>
      <figcaption>
        <p data-testid="strip-summary">{ST.mission.summary(strip.geometricHours, strip.realHours, STRIP_DAYS)}</p>
        <p class="small"><span class="key s-trans-key" aria-hidden="true"></span> +{formatNumber(strip.realHours - strip.geometricHours)} {ST.mission.gained}. {ST.mission.illustrative}</p>
      </figcaption>
    </figure>
    <p class="go"><Button href={href('/siti')} variant="ghost">{ST.mission.sites}</Button></p>
  </div>
</section>

{#if modeNow.advanced}
  <section class="tile step" aria-labelledby="stack-h" data-testid="stack">
    <div class="container container--wide">
      <h2 id="stack-h" class="step-title">{STR.stackTitle}</h2>
      <p class="step-text narrow">{STR.stack}</p>
    </div>
  </section>
{/if}

<style>
  /* ---- palco ---- */
  .hero-copy {
    max-inline-size: 48rem;
  }
  .display {
    width: min(100%, 22rem);
    margin: 0 0 var(--space-3);
    line-height: 0;
  }
  .display img {
    display: block;
    width: 100%;
    height: auto;
    mix-blend-mode: screen;
  }
  .hero-lead {
    font-size: var(--fs-lead);
    line-height: 1.33;
    color: var(--c-text); /* sopra lo scrim solo --c-text: AA garantito anche su pixel chiari */
    max-inline-size: 32ch;
    margin: 0 0 var(--space-2);
  }
  .hero-support {
    max-inline-size: 48ch;
    margin: 0 0 var(--space-5);
    color: var(--c-text);
    line-height: 1.45;
  }
  .hero-actions {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-3);
    margin: 0;
  }
  /* L'unico ingresso orchestrato: la Luna sale dal nero (MoonStage), poi il testo sale dall'orizzonte. */
  @media (prefers-reduced-motion: no-preference) {
    .hero-copy > :global(*) {
      animation: horizon 900ms var(--ease-out) both;
      animation-delay: 1000ms;
    }
    .hero-copy > .hero-lead {
      animation-delay: 1150ms;
    }
    .hero-copy > .hero-actions {
      animation-delay: 1300ms;
    }
  }
  @keyframes horizon {
    from {
      clip-path: inset(0 0 100% 0);
      transform: translateY(0.5em);
    }
    to {
      clip-path: inset(-20% -10% -20% -10%);
      transform: none;
    }
  }

  /* ---- storia ---- */
  .story-intro {
    padding-block: var(--chapter-pad) var(--space-5);
  }
  .story-intro:focus {
    outline: none;
  }
  .learn {
    margin: 0;
    max-inline-size: 60ch;
  }
  .step {
    padding-block: var(--chapter-pad);
  }
  .step-title {
    margin: 0 0 var(--space-3);
    font-size: var(--fs-h2);
    font-stretch: var(--wdth-heading);
    letter-spacing: -0.02em;
    line-height: 1.05;
    max-inline-size: 18ch;
  }
  .step-text {
    margin: 0;
    font-size: var(--fs-lead);
    line-height: 1.4;
    max-inline-size: 38ch;
  }
  .step-tech {
    margin: var(--space-3) 0 0;
    font-size: var(--fs-small);
    color: var(--c-muted);
    max-inline-size: 70ch;
  }
  .narrow {
    max-inline-size: 60ch;
  }
  .small {
    margin: var(--space-2) 0 0;
    font-size: var(--fs-small);
    color: var(--c-muted);
  }
  .go {
    margin: var(--space-5) 0 0;
  }
  .split {
    display: grid;
    grid-template-columns: minmax(0, 2fr) minmax(0, 3fr);
    gap: var(--space-6, 3rem);
    align-items: center;
  }
  .duo {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: var(--space-4);
  }
  .diag {
    margin: 0;
  }
  .diag svg {
    display: block;
    inline-size: 100%;
    block-size: auto;
    border-radius: var(--radius-md, 12px);
  }
  .diag figcaption {
    margin-block-start: var(--space-2);
    font-size: var(--fs-small);
  }
  .mini-slot {
    margin-block-start: var(--space-5);
    min-block-size: 40rem; /* spazio riservato: il chunk si carica prima di arrivare qui, niente salti visibili */
  }
  .mini-slot[data-ready='1'] {
    min-block-size: 0;
  }
  @media (max-width: 899px) {
    .split {
      grid-template-columns: minmax(0, 1fr);
    }
    .mini-slot {
      min-block-size: 70rem;
    }
  }

  /* ---- passo 4: striscia del mese ---- */
  .strip {
    --c-warn: #a35200;
    margin: var(--space-5) 0 0;
    display: grid;
    gap: var(--space-2);
    max-inline-size: 60rem;
  }
  @media (prefers-color-scheme: dark) {
    .strip {
      --c-warn: #ffb340;
    }
  }
  .strip-row {
    display: grid;
    grid-template-columns: minmax(0, 16rem) minmax(0, 1fr) 5rem;
    align-items: center;
    gap: var(--space-3);
  }
  .strip-label {
    font-size: var(--fs-small);
  }
  .strip svg {
    display: block;
    inline-size: 100%;
    block-size: 1.6rem;
    background: color-mix(in srgb, var(--c-text) 10%, transparent);
    border-radius: 4px;
  }
  .s-open {
    fill: var(--c-success);
  }
  .s-trans {
    fill: var(--c-warn);
  }
  .strip-n {
    font-variant-numeric: tabular-nums;
    text-align: end;
  }
  .strip figcaption p {
    margin: var(--space-2) 0 0;
  }
  .key {
    display: inline-block;
    inline-size: 1rem;
    block-size: 0.7rem;
    background: var(--c-warn);
    border-radius: 2px;
  }
  @media (max-width: 599px) {
    .strip-row {
      grid-template-columns: minmax(0, 1fr) auto;
    }
    .strip-row svg {
      grid-column: 1 / -1;
      grid-row: 2;
    }
  }

  /* ---- passo 1: Earthrise a tutto schermo ---- */
  .earth {
    position: relative;
    min-block-size: max(34rem, 100svh);
    background: #000;
    color: var(--c-text);
    overflow: hidden;
    isolation: isolate;
    padding: 0;
  }
  .earth :global(.earth-media) {
    position: absolute;
    inset: 0;
    block-size: 100%;
  }
  .earth :global(.earth-media img) {
    object-position: 62% 40%;
  }
  .earth-scrim {
    position: absolute;
    inset: 0;
    pointer-events: none;
    background:
      linear-gradient(to right, var(--scrim-strong) 0%, var(--scrim-min) 42%, transparent 62%),
      linear-gradient(to top, #000 0%, transparent 28%);
  }
  .earth-copy {
    position: relative;
    padding-block-start: var(--chapter-pad);
  }
  .earth .step-text {
    max-inline-size: 34ch;
  }
  .earth .step-tech {
    color: var(--c-text);
    max-inline-size: 44ch;
  }
  .earth-credit {
    position: absolute;
    inset-inline: var(--gutter);
    inset-block-end: var(--space-3);
    margin: 0;
    text-align: end;
    font-size: var(--fs-micro);
    color: var(--c-text);
  }
  @media (max-width: 833px) {
    .earth-scrim {
      background:
        linear-gradient(to bottom, var(--scrim-strong) 0%, var(--scrim-min) 45%, transparent 62%),
        linear-gradient(to top, #000 0%, transparent 24%);
    }
    .earth .step-title {
      max-inline-size: none;
    }
  }

</style>
