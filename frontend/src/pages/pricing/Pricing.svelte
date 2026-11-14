<!-- SPDX-License-Identifier: Apache-2.0 -->
<script lang="ts">
  import { t } from '../../i18n/i18n.svelte';
  import { BASE } from '../../registry';
  import { withBase } from '../../shell/router';
  import { checkoutUrl } from './checkout';

  import type { MessageKey } from '../../i18n/i18n.svelte';
  import { GROUPS, type PlanId } from './plans';

  const K = (k: string) => k as MessageKey;

  const names: Record<PlanId, string> = { free: 'Free', premium: 'Premium', enterprise: 'Enterprise' };
  const plans = [
    { id: 'free', url: null },
    { id: 'premium', url: checkoutUrl(import.meta.env.VITE_PREMIUM_CHECKOUT_URL) },
    { id: 'enterprise', url: checkoutUrl(import.meta.env.VITE_ENTERPRISE_CHECKOUT_URL) },
  ] as const satisfies readonly { id: PlanId; url: string | null }[];
</script>

<div class="pricing-page">
  <section class="hero">
    <div class="container container--wide">
      <p class="eyebrow">{t('pricing.eyebrow')}</p>
      <h1>{t('pricing.heading')}</h1>
      <p class="intro">{t('pricing.intro')}</p>
      <a class="hero-link" href="#plans">{t('pricing.seePlans')} <span aria-hidden="true">↗</span></a>
    </div>
  </section>

  <section class="container container--wide strategy" aria-labelledby="strategy-title">
    <p class="eyebrow">{t('pricing.strategyEyebrow')}</p>
    <h2 id="strategy-title">{t('pricing.strategyTitle')}</h2>
    <p class="section-intro">{t('pricing.strategyIntro')}</p>
    <div class="pillars">
      <article><span>01</span><h3>{t('pricing.pillar1Title')}</h3><p>{t('pricing.pillar1')}</p></article>
      <article><span>02</span><h3>{t('pricing.pillar2Title')}</h3><p>{t('pricing.pillar2')}</p></article>
      <article><span>03</span><h3>{t('pricing.pillar3Title')}</h3><p>{t('pricing.pillar3')}</p></article>
    </div>
  </section>

  <section id="plans" class="container container--wide plans-section" aria-labelledby="plans-title">
    <p class="eyebrow">{t('pricing.plansEyebrow')}</p>
    <h2 id="plans-title">{t('pricing.plansTitle')}</h2>
    <p class="section-intro">{t('pricing.plansNote')}</p>
    <div class="plans">
      {#each plans as plan (plan.id)}
        <article class:featured={plan.id === 'premium'} class="plan">
          <div>
            <p class="plan-number">{plan.id === 'free' ? t('pricing.available') : t('pricing.proposed')}</p>
            <h3>{names[plan.id]}</h3>
            <p class="price">{t(K(`pricing.${plan.id}.price`))}</p>
            <p class="audience">{t(K(`pricing.${plan.id}.audience`))}</p>
            <ul>
              {#each ['f1', 'f2', 'f3'] as f}<li>{t(K(`pricing.${plan.id}.${f}`))}</li>{/each}
            </ul>
          </div>
          {#if plan.id === 'free'}
            <a class="plan-action" href={withBase('/mission-planner', BASE)}>{t('pricing.tryCommunity')}</a>
          {:else if plan.url}
            <a class="plan-action" href={plan.url} target="_blank" rel="noopener noreferrer">{t('pricing.checkout')}</a>
          {:else}
            <p class="unavailable">{t('pricing.unavailable')}</p>
          {/if}
        </article>
      {/each}
    </div>
    <p class="disclaimer">{t('pricing.disclaimer')}</p>
    <p><a href={withBase('/terms', BASE)}>{t('title.terms')}</a> · <a href={withBase('/privacy', BASE)}>{t('title.privacy')}</a> · <a href={withBase('/contacts', BASE)}>{t('trust.support.link')}</a></p>
  </section>

  <section class="container container--wide compare" aria-labelledby="compare-title">
    <h2 id="compare-title">{t('pricing.table.title')}</h2>
    <p class="section-intro">{t('pricing.table.intro')}</p>
    <!-- svelte-ignore a11y_no_noninteractive_tabindex -->
    <div class="table-wrap" role="region" aria-label={t('pricing.table.label')} tabindex="0">
      <table>
        <caption class="sr">{t('pricing.table.caption')}</caption>
        <thead>
          <tr>
            <th scope="col">{t('pricing.table.feature')}</th>
            {#each plans as plan (plan.id)}<th scope="col">{names[plan.id]}</th>{/each}
          </tr>
        </thead>
        {#each GROUPS as group (group.id)}
          <tbody>
            <tr class="group"><th scope="colgroup" colspan="4">{t(K(`pricing.group.${group.id}`))}</th></tr>
            {#each group.rows as row (row.id)}
              <tr>
                <th scope="row">
                  {t(K(`pricing.row.${row.id}`))}
                  {#if row.planned}<span class="planned">{t('pricing.table.planned')}</span>{/if}
                </th>
                {#each row.in as on}
                  <td class={on ? 'yes' : 'no'}>
                    <span aria-hidden="true">{on ? '✓' : '✕'}</span>
                    <span class="sr">{on ? t('pricing.table.included') : t('pricing.table.notIncluded')}</span>
                  </td>
                {/each}
              </tr>
            {/each}
          </tbody>
        {/each}
      </table>
    </div>
    <p class="disclaimer">{t('pricing.table.note')}</p>
  </section>
</div>

<style>
  .pricing-page { color: #eef5ff; padding-bottom: 6rem; }
  .hero { padding: clamp(5rem, 11vw, 9rem) 0; background: radial-gradient(ellipse at 75% 15%, #204471 0, transparent 42%), linear-gradient(130deg, #070d18, #101c30 60%, #080e19); border-bottom: 1px solid #35465e; }
  .eyebrow { color: #91c9ff; text-transform: uppercase; letter-spacing: 0.18em; font-size: 0.75rem; font-weight: 700; }
  h1 { max-width: 13ch; font-size: clamp(2.8rem, 7vw, 6rem); line-height: 1.03; margin: 1rem 0 1.5rem; }
  .intro, .section-intro { max-width: 65ch; color: #c3d1e1; font-size: 1.1rem; line-height: 1.7; }
  .hero-link { display: inline-flex; gap: 1rem; align-items: center; margin-top: 1.5rem; color: #e6f4ff; text-decoration: none; border-bottom: 1px solid #8ccaff; padding-bottom: 0.5rem; }
  .strategy, .plans-section { padding-top: clamp(4rem, 8vw, 7rem); }
  h2 { font-size: clamp(2rem, 4vw, 3.2rem); margin: 1rem 0; }
  .pillars, .plans { display: grid; gap: 1rem; margin-top: 2rem; }
  .pillars { grid-template-columns: repeat(auto-fit, minmax(min(100%, 16rem), 1fr)); }
  .pillars article, .plan { border: 1px solid #344960; border-radius: 0.75rem; background: linear-gradient(145deg, #111e30, #0b1422); padding: 1.6rem; }
  .pillars span, .plan-number { color: #9dc9f2; font-size: 0.78rem; letter-spacing: 0.1em; text-transform: uppercase; }
  .pillars h3, .plan h3 { margin: 1rem 0 0.6rem; }
  .pillars p, .audience, .disclaimer { color: #bccbdb; line-height: 1.6; }
  .plans { grid-template-columns: repeat(auto-fit, minmax(min(100%, 18rem), 1fr)); }
  .plan { display: flex; flex-direction: column; justify-content: space-between; gap: 2rem; }
  .featured { border-color: #83bdf3; box-shadow: 0 0 35px rgb(65 139 220 / 0.12); }
  .price { color: #fff; font-size: 1.35rem; font-weight: 700; }
  .plan ul { color: #d3deeb; padding-inline-start: 1.2rem; line-height: 1.6; }
  .plan li + li { margin-top: 0.5rem; }
  .plan-action { display: block; padding: 0.85rem 1rem; color: #071321; background: #add9ff; border-radius: 0.4rem; text-align: center; font-weight: 700; text-decoration: none; }
  .plan-action:hover { background: #d1eaff; }
  .unavailable { color: #c2cedb; border: 1px solid #53667c; padding: 0.85rem 1rem; border-radius: 0.4rem; text-align: center; margin: 0; }
  .compare { padding-top: clamp(3rem, 6vw, 5rem); }
  .sr { position: absolute; inline-size: 1px; block-size: 1px; overflow: hidden; clip-path: inset(50%); white-space: nowrap; }
  .table-wrap { position: relative; margin-top: 1.5rem; max-height: 70vh; overflow: auto; border: 1px solid #344960; border-radius: 0.75rem; background: #0b1422; }
  .table-wrap:focus-visible { outline: 3px solid #add9ff; outline-offset: 2px; }
  table { border-collapse: separate; border-spacing: 0; inline-size: 100%; min-inline-size: 34rem; color: #d3deeb; }
  thead th { position: sticky; top: 0; z-index: 2; background: #14243a; color: #fff; text-align: center; padding: 0.8rem 0.9rem; border-bottom: 1px solid #53667c; }
  thead th:first-child, tbody th[scope='row'] { position: sticky; left: 0; text-align: start; background: #0f1b2d; }
  thead th:first-child { z-index: 3; background: #14243a; }
  tbody th[scope='row'] { z-index: 1; font-weight: 500; padding: 0.7rem 0.9rem; min-inline-size: 11rem; border-bottom: 1px solid #243449; }
  tbody td { text-align: center; padding: 0.7rem 0.9rem; border-bottom: 1px solid #243449; font-size: 1.1rem; font-weight: 700; }
  tr.group th { text-align: start; background: #182a43; color: #9dc9f2; font-size: 0.8rem; letter-spacing: 0.1em; text-transform: uppercase; padding: 0.6rem 0.9rem; position: static; }
  td.yes { color: #8be9ae; }
  td.no { color: #ffa3a3; }
  .planned { display: inline-block; margin-inline-start: 0.5rem; padding: 0.05rem 0.5rem; border: 1px solid #e8c36a; border-radius: 999px; color: #f3d98f; font-size: 0.72rem; font-weight: 700; letter-spacing: 0.04em; text-transform: uppercase; white-space: nowrap; }
  .disclaimer { max-width: 85ch; font-size: 0.9rem; margin-top: 2rem; }
</style>
