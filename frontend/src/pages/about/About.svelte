<!-- SPDX-License-Identifier: Apache-2.0 -->
<script lang="ts">
  import { t } from '../../i18n/i18n.svelte';
  import { BASE } from '../../registry';
  import { withBase } from '../../shell/router';
  const sources = [
    { id: 'de440', title: 'Park et al. (2021), The JPL Planetary and Lunar Ephemerides DE440 and DE441', url: 'https://doi.org/10.3847/1538-3881/abd414' },
    { id: 'spice', title: 'Acton (1996), Ancillary data services of NASA’s Navigation and Ancillary Information Facility', url: 'https://doi.org/10.1016/0032-0633(95)00107-7' },
    { id: 'horizons', title: 'NASA/JPL Horizons', url: 'https://ssd.jpl.nasa.gov/horizons/' },
    { id: 'lola', title: 'NASA LRO / LOLA — PDS Geosciences', url: 'https://pds-geosciences.wustl.edu/missions/lro/lola.htm' },
    { id: 'illumination', title: 'Mazarico et al. (2011), Illumination conditions of the lunar polar regions using LOLA topography', url: 'https://ntrs.nasa.gov/citations/20120010094' },
    { id: 'solarMap', title: 'NASA PGDA 69 — Lunar polar illumination products', url: 'https://pgda.gsfc.nasa.gov/products/69' },
    { id: 'gazetteer', title: 'IAU / USGS Gazetteer of Planetary Nomenclature', url: 'https://planetarynames.wr.usgs.gov/' },
    { id: 'diffraction', title: 'ITU-R P.526-9 (2005), Propagation by diffraction', url: 'https://www.itu.int/rec/R-REC-P.526-9-200508-S/en' },
    { id: 'dsn', title: 'DSN 810-005, Module 104, Rev. Q', url: 'https://deepspace.jpl.nasa.gov/dsndocs/810-005/104/104Q.pdf' },
    { id: 'dsnCoordinates', title: 'DSN 810-005, Module 301, Rev. P', url: 'https://deepspace.jpl.nasa.gov/dsndocs/810-005/301/301P.pdf' },
    { id: 'surveyor', title: 'NASA CR-69102 — Surveyor reference report (1966)', url: 'https://ntrs.nasa.gov/citations/19660005264' },
    { id: 'surface', title: 'Simpson & Tyler, NASA CR-119032 (1971)', url: 'https://ntrs.nasa.gov/citations/19710019588' },
    { id: 'lander', title: 'NASA/TP-2019-220391, NASA Lunar Lander Reference Design', url: 'https://www.lpi.usra.edu/lunar/strategies/NASA-TP-2019-220391.pdf' },
    { id: 'power', title: 'NASA Small Spacecraft Technology State-of-the-Art (2022), Power', url: 'https://www.nasa.gov/wp-content/uploads/2023/05/3.-soa-power-2022.pdf' },
  ] as const;
</script>

<div class="doc tile">
  <div class="container container--wide">
    <p class="eyebrow">{t('about.eyebrow')}</p>
    <h1>{t('about.title')}</h1>
    <p class="lead">{t('about.intro')}</p>
    <p class="notice">{t('disclosure.affiliation')}</p>
    <a href="#transparency">{t('disclosure.title')}</a>

    <section aria-labelledby="problem-title">
      <h2 id="problem-title">{t('about.problem.title')}</h2>
      <p>{t('about.problem.text')}</p>
    </section>

    <section aria-labelledby="does-title">
      <h2 id="does-title">{t('about.does.title')}</h2>
      <p>{t('about.does.text')}</p>
      <ul>
        <li>{t('about.does.1')}</li>
        <li>{t('about.does.2')}</li>
        <li>{t('about.does.3')}</li>
      </ul>
    </section>

    <section aria-labelledby="model-title">
      <h2 id="model-title">{t('about.model.title')}</h2>
      <p>{t('about.model.text')}</p>
      <ol class="stages">
        <li><strong>S0</strong> {t('about.model.s0')}</li>
        <li><strong>S1–S3</strong> {t('about.model.s1')}</li>
        <li><strong>S4</strong> {t('about.model.s4')}</li>
        <li><strong>S5</strong> {t('about.model.s5')}</li>
        <li><strong>S6–S7</strong> {t('about.model.s6')}</li>
      </ol>
    </section>

    <section aria-labelledby="data-title">
      <h2 id="data-title">{t('about.data.title')}</h2>
      <p>{t('about.data.text')}</p>
      <ul>
        <li>{t('about.data.1')}</li>
        <li>{t('about.data.2')}</li>
        <li>{t('about.data.3')}</li>
      </ul>
    </section>

    <section aria-labelledby="validation-title">
      <h2 id="validation-title">{t('about.validation.title')}</h2>
      <p>{t('about.validation.text')}</p>
      <p class="notice">{t('about.validation.notice')}</p>
    </section>

    <section aria-labelledby="limits-title">
      <h2 id="limits-title">{t('about.limits.title')}</h2>
      <p>{t('about.limits.text')}</p>
    </section>

    <section aria-labelledby="team-title">
      <h2 id="team-title">{t('about.team.title')}</h2>
      <p>{t('about.team.text')}</p>
    </section>

    <section aria-labelledby="license-title">
      <h2 id="license-title">{t('about.license.title')}</h2>
      <p>{t('about.license.text')}</p>
    </section>

    <section id="transparency" aria-labelledby="transparency-title">
      <h2 id="transparency-title">{t('disclosure.title')}</h2>
      <h3>{t('disclosure.terminologyTitle')}</h3>
      <p>{t('disclosure.terminology')}</p>
      <p><a href="https://www.whitehouse.gov/presidential-actions/2026/09/inaugurating-the-era-of-super-intelligence/" target="_blank" rel="noopener noreferrer">Executive Order 14434 — 29 September 2026</a></p>
      <p><a href="https://www.nist.gov/super-intelligence" target="_blank" rel="noopener noreferrer">{t('disclosure.nist')}</a></p>
      <h3>{t('disclosure.contributionsTitle')}</h3>
      <p>{t('disclosure.contributions')}</p>
      <p class="notice">{t('disclosure.responsibility')}</p>
    </section>

    <section id="references" aria-labelledby="references-title">
      <h2 id="references-title">{t('disclosure.referencesTitle')}</h2>
      <p>{t('disclosure.legend')}</p>
      <p>{t('disclosure.validation')}</p>
      <dl class="references">
        {#each sources as source (source.id)}
          <dt><a href={source.url} target="_blank" rel="noopener noreferrer">{source.title}</a></dt>
          <dd>{t(`disclosure.source.${source.id}`)}</dd>
        {/each}
      </dl>
    </section>

    <nav class="links" aria-label={t('about.linksLabel')}>
      <a href={withBase('/contacts', BASE)}>{t('about.contactsLink')}</a>
      <a href={withBase('/licenses', BASE)}>{t('about.licensesLink')}</a>
    </nav>
  </div>
</div>

<style>
  .doc { padding-block: var(--space-5) var(--space-7, 4rem); }
  .eyebrow { color: #8fc7ff; font: 600 0.75rem 'Orbitron', var(--font-sans); letter-spacing: 0.14em; text-transform: uppercase; }
  h1 { max-inline-size: 15ch; margin-block: var(--space-2) var(--space-3); }
  .lead { max-inline-size: 70ch; font-size: var(--fs-lead); color: var(--c-text); }
  section { max-inline-size: 72ch; margin-block-start: var(--space-6); }
  h2 { margin-block: 0 var(--space-2); font-size: var(--fs-h3); }
  p, li { color: var(--c-muted); line-height: 1.65; }
  ul, .stages { padding-inline-start: 1.3rem; }
  li + li { margin-block-start: 0.45rem; }
  .stages { display: grid; gap: var(--space-2); }
  .stages strong { color: var(--c-text); font-family: 'Orbitron', var(--font-sans); font-size: var(--fs-small); }
  .notice { padding: var(--space-3); border-inline-start: 3px solid var(--c-power); background: var(--c-raised); }
  .links { display: flex; flex-wrap: wrap; gap: var(--space-3); margin-block-start: var(--space-6); }
  .links a { min-block-size: var(--target); display: inline-flex; align-items: center; padding-inline: var(--space-3); border: 1px solid var(--c-control); border-radius: 999px; }
  #transparency, #references { scroll-margin-block-start: 7rem; }
  .references dt { margin-block-start: 1.5rem; overflow-wrap: anywhere; }
  .references a { display: inline-flex; align-items: center; min-block-size: var(--target); }
  .references dd { margin: .3rem 0 0; color: var(--c-muted); line-height: 1.65; }
</style>
