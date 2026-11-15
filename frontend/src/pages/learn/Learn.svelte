<!-- SPDX-License-Identifier: Apache-2.0 -->
<script lang="ts">
  import { tick } from 'svelte';
  import { t, lang, type MessageKey } from '../../i18n/i18n.svelte';
  import { BASE } from '../../registry';
  import { withBase } from '../../shell/router';
  import { scenarioStore, withScenario } from '../../shell/scenario';
  import SubNav from '../../components/ui/SubNav.svelte';
  const lessons = [
    { id: 'mission', correct: 1, path: '/mission-planner?mp_step=mission' },
    { id: 'sites', correct: 1, path: '/mission-planner?mp_step=sites' },
    { id: 'period', correct: 0, path: '/mission-planner?mp_step=period' },
    { id: 'energy', correct: 0, path: '/mission-planner?mp_step=energy' },
    { id: 'radio', correct: 2, path: '/mission-planner?mp_step=radio' },
    { id: 'simulation', correct: 1, path: '/mission-planner?mp_step=compare' },
    { id: 'report', correct: 2, path: '/mission-planner?mp_step=report' },
    { id: 's0', correct: 0, path: null },
    { id: 's1', correct: 1, path: null },
    { id: 's2', correct: 2, path: null },
    { id: 's3', correct: 1, path: null },
    { id: 's4', correct: 2, path: null },
    { id: 's5', correct: 1, path: null },
    { id: 's6', correct: 0, path: null },
    { id: 's7', correct: 2, path: null },
  ] as const;
  const options = ['a', 'b', 'c'] as const;
  const store = scenarioStore();
  let scenario = $state(store.reload());
  $effect(() => store.subscribe((s) => scenario = s));
  let current = $state(0);
  let answers = $state<(number | null)[]>(lessons.map(() => null));
  let passed = $state(lessons.map(() => false));
  let submitted = $state(lessons.map(() => false));
  let heading = $state<HTMLHeadingElement>();
  const lesson = $derived(lessons[current]!);
  const key = (field: 'title' | 'body' | 'example' | 'question' | 'a' | 'b' | 'c' | 'explanation'): MessageKey => `course.${lesson.id}.${field}`;
  const completed = $derived(passed.filter(Boolean).length);
  const unlocked = $derived(passed.findIndex((v) => !v) < 0 ? lessons.length : passed.findIndex((v) => !v));
  // theory: a scrollable PDF reader, the file follows the site language (Italian or English)
  const theory = $derived(withBase(`/learn/Learning_RAVEN_${lang.current === 'it' ? 'IT' : 'EN'}.pdf`, BASE));
  const href = (path: string) => withBase(withScenario(path, scenario), BASE);
  async function go(next: number) { current = next; await tick(); heading?.focus(); }
  function check() { submitted[current] = true; passed[current] = answers[current] === lesson.correct; }
</script>

<SubNav title="Learn" mode={false} />
<div class="workspace tile tile--alt">
 <div class="container container--wide">
  <section class="theory" aria-labelledby="learn-theory-h" data-testid="learn-theory">
    <h2 id="learn-theory-h">{t('learn.theory.title')}</h2>
    {#key theory}<iframe src={theory} title={t('learn.theory.title')} loading="lazy"></iframe>{/key}
    <p><a href={theory} target="_blank" rel="noopener">{t('learn.theory.open')}</a></p>
  </section>
  <section class="lessons" aria-labelledby="lessons-title" data-testid="learn-lessons">
    <h2 id="lessons-title">{t('lessons.title')}</h2>
    <p>{t('lessons.intro')}</p>
    <p role="status">{t('lessons.progress', { count: completed, total: lessons.length })}</p>
    <nav aria-label={t('lessons.navigation')}>
      {#each lessons as item, i}
        <button type="button" disabled={i > unlocked} aria-current={current === i ? 'step' : undefined} onclick={() => go(i)}>
          {i + 1}. {t(`course.${item.id}.title`)}
        </button>
      {/each}
    </nav>
    <article class="lesson-card" aria-labelledby="lesson-heading">
    <p class="phase">{t(current < 7 ? 'course.plannerPhase' : 'course.enginePhase')}</p>
    <h3 id="lesson-heading" bind:this={heading} tabindex="-1">{t(key('title'))}</h3>
    <p>{t(key('body'))}</p>
    <div class="example"><strong>{t('course.example')}</strong><p>{t(key('example'))}</p></div>
    {#if lesson.path}
      <p class="practice">{t('course.toolNote')}</p>
      <a class="tool" href={href(lesson.path)} target="_blank" rel="noopener noreferrer">{t('course.openPlanner')}</a>
    {/if}
    <fieldset>
      <legend>{t(key('question'))}</legend>
      {#each options as option, i}
        <label><input type="radio" name={`lesson-${current}`} checked={answers[current] === i}
          onchange={() => { answers[current] = i; passed[current] = false; submitted[current] = false; }} /> {t(key(option))}</label>
      {/each}
    </fieldset>
    <button type="button" disabled={answers[current] === null} onclick={check}>{t('lessons.check')}</button>
    {#if submitted[current]}
      <div class="feedback" role="status"><strong>{t(passed[current] ? 'lessons.correct' : 'lessons.retry')}</strong> {t(key('explanation'))}</div>
    {/if}
    <div class="actions">
      {#if current > 0}<button type="button" onclick={() => go(current - 1)}>{t('lessons.back')}</button>{/if}
      {#if current < lessons.length - 1}<button type="button" disabled={!passed[current]} onclick={() => go(current + 1)}>{t('lessons.next')}</button>{/if}
    </div>
    </article>
    {#if completed === lessons.length}
      <div class="complete" role="status"><h3>{t('lessons.complete')}</h3><p>{t('lessons.practice')}</p>
        <a href={href('/mission-planner')}>{t('lessons.start')}</a>
      </div>
    {/if}
  </section>
 </div>
</div>

<style>
  .workspace { padding-block: var(--space-5) var(--space-7, 4rem); }
  .lessons { min-width: 0; margin-bottom: 2rem; }
  .lesson-card { border: 1px solid var(--c-hairline); border-radius: 1rem; padding: clamp(1rem, 3vw, 2rem); margin-top: 1.5rem; }
  .lessons p { max-width: 75ch; }
  nav { display: flex; gap: .5rem; padding: .35rem; margin-block: 1.5rem; overflow-x: auto; }
  nav button { flex: 0 0 11rem; text-align: start; }
  .phase { color: var(--c-uplink); font-weight: 600; }
  .example { padding: 1rem; background: var(--c-raised); border-radius: .5rem; margin-block: 1rem; }
  .example p { margin-bottom: 0; }
  .practice { color: var(--c-muted); font-size: var(--fs-small); }
  button, a { min-height: 44px; }
  button[aria-current="step"] { outline: 2px solid #a4dfff; outline-offset: 2px; }
  fieldset { margin-block: 1.5rem; padding: 1rem; border: 1px solid var(--c-hairline); border-radius: .5rem; }
  legend { padding-inline: .5rem; }
  label { display: flex; align-items: center; gap: .75rem; min-height: 44px; padding-block: .5rem; }
  input { flex-shrink: 0; }
  .actions { display: flex; gap: 1rem; margin-block: 1rem; }
  a { display: inline-flex; align-items: center; }
  .feedback, .complete { padding: 1rem; margin-block: 1rem; border-inline-start: 3px solid #a4dfff; }
  .theory { margin-bottom: 3rem; }
  .theory h2 { text-align: center; }
  .theory iframe { width: 100%; height: 80vh; min-height: 32rem; border: 1px solid #9bdfff33; border-radius: .5rem; background: #fff; }
</style>
