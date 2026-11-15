<!-- SPDX-License-Identifier: Apache-2.0 -->
<script lang="ts">
  import { withBase } from '../../shell/router';
  import Hero from '../../components/ui/Hero.svelte';
  import Button from '../../components/ui/Button.svelte';
  import MoonStage from './MoonStage.svelte';
  import ravenLogo from '../../assets/media/raven-logo.webp';
  import { lang, t } from '../../i18n/i18n.svelte';
  import { scenarioStore, withScenario, type Scenario } from '../../shell/scenario';

  const base = import.meta.env.BASE_URL;
  const href = (p: string) => withBase(p, base);
  const store = scenarioStore();
  let scenario = $state<Scenario>(store.reload());
  $effect(() => store.subscribe((s) => (scenario = s)));
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
  <p class="hero-credit">{t('home.credit')}</p>
</Hero>

<style>
  .hero-copy { max-inline-size: 48rem; }
  .display { width: min(100%, 22rem); margin: 0 0 var(--space-3); line-height: 0; }
  .display img { display: block; width: 100%; height: auto; mix-blend-mode: screen; }
  .hero-lead { font-size: var(--fs-lead); line-height: 1.33; color: var(--c-text); max-inline-size: 32ch; margin: 0 0 var(--space-2); }
  .hero-support { max-inline-size: 48ch; margin: 0 0 var(--space-5); color: var(--c-text); line-height: 1.45; }
  .hero-actions { display: flex; flex-wrap: wrap; gap: var(--space-3); margin: 0; }
  .hero-credit {
    position: absolute;
    inset-inline-end: var(--gutter);
    inset-block-end: calc(var(--target) + 2 * var(--space-3));
    max-inline-size: min(36rem, 45vw);
    margin: 0;
    padding: 2px 8px;
    border-radius: 6px;
    font-size: var(--fs-micro);
    color: var(--c-text);
    background: var(--scrim-strong);
  }
  @media (max-width: 599px) {
    .hero-credit { position: static; max-inline-size: none; display: inline-block; margin-block-start: var(--space-4); }
  }
  @media (prefers-reduced-motion: no-preference) {
    .hero-copy > :global(*) { animation: horizon 900ms var(--ease-out) both; animation-delay: 1000ms; }
    .hero-copy > .hero-lead { animation-delay: 1150ms; }
    .hero-copy > .hero-actions { animation-delay: 1300ms; }
  }
  @keyframes horizon {
    from { clip-path: inset(0 0 100% 0); transform: translateY(0.5em); }
    to { clip-path: inset(-20% -10% -20% -10%); transform: none; }
  }
</style>
