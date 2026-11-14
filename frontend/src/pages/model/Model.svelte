<!-- SPDX-License-Identifier: Apache-2.0 -->
<!--
  Modello e validazione: stadi S0-S7, stato di validazione, prove, parametri, riproduzione.
  Tutto il contenuto di stato viene da GET /api/raven/model (che include la matrice) e /api/raven/parameters;
  le frasi esplicative e le domande sono nel catalogo (en/it). Senza server non si mostra nulla di inventato.
-->
<script lang="ts">
  import { onMount } from 'svelte';
  import SubNav from '../../components/ui/SubNav.svelte';
  import { t, lang } from '../../i18n/i18n.svelte';
  import type { MessageKey } from '../../i18n/i18n.svelte';
  import { BASE } from '../../registry';
  import { withBase } from '../../shell/router';
  import { modeNow } from '../../shell/modeState.svelte';
  import { FORMULAS, VARS, plainLine, stageStatus, varMeaning } from '../planner/reportFormulas';
  const STATUS_OF = { verified: 'verified', plausible: 'plausibility_only', notvalidated: 'not_validated', unknown: 'unknown' } as const;
  const formulaStatus = (stages: readonly string[]): Status => STATUS_OF[stageStatus(info?.validation ?? null, stages)];
  import { rt } from '../planner/reportText';
  import EngineEstimates from './EngineEstimates.svelte';
  import {
    STAGES, STATUSES, STATUS_ICON, STATUS_LIGHT, countByStatus, entriesFor, exportMatrix,
    filterParams, isStatus, rangeText, worstStatus,
    type ModelInfo, type Parameters, type Status,
  } from './model';

  let info = $state.raw<ModelInfo | null>(null);
  let params = $state.raw<Parameters | null>(null);
  let failure = $state<{ status: number; invalid?: boolean } | null>(null);
  let loading = $state(true);
  let paramFail = $state(false);
  let stageOpen = $state<Record<string, boolean>>({});
  let fStage = $state('');
  let fTag = $state('');
  let fText = $state('');

  const advanced = $derived(modeNow.current === 'avanzato');
  const copyLang = $derived(lang.current);
  const K = (k: string) => k as MessageKey;

  async function load() {
    loading = true;
    failure = null;
    try {
      const r = await fetch('/api/raven/model');
      if (!r.ok) throw { status: r.status };
      const body = (await r.json()) as ModelInfo;
      if (!Array.isArray(body?.stages) || !Array.isArray(body?.validation?.stages)
        || !body.validation.stages.length
        || body.validation.stages.some((e) => !e || !isStatus(e.status))) {
        info = null;
        failure = { status: r.status, invalid: true };
      } else {
        info = body;
        if (params && (params.registry_sha256 !== body.registry_sha256
          || params.model_version !== body.model_version)) params = null;
        paramFail = false;
      }
    } catch (e) {
      info = null;
      failure = { status: typeof (e as { status?: number })?.status === 'number' ? (e as { status: number }).status : 503, invalid: e instanceof SyntaxError };
    }
    loading = false;
  }
  async function loadParams() {
    paramFail = false;
    const requestedModel = info;
    try {
      const r = await fetch('/api/raven/parameters');
      if (!r.ok) throw new Error(String(r.status));
      const body = (await r.json()) as Parameters;
      if (requestedModel !== info) return;
      if (!info || body.model_version !== info.model_version || body.registry_sha256 !== info.registry_sha256) {
        throw new Error('Parameter/model identity mismatch');
      }
      params = body;
    } catch {
      if (requestedModel === info) paramFail = true;
    }
  }
  onMount(() => {
    void load();
    const refresh = () => { if (!loading) void load(); };
    window.addEventListener('focus', refresh);
    return () => window.removeEventListener('focus', refresh);
  });
  $effect(() => {
    if (advanced && info && !params && !paramFail) void loadParams();
  });

  const val = $derived(info?.validation ?? null);
  const counts = $derived(val ? countByStatus(val) : null);
  const reads = $derived.by(() => {
    const m: Record<string, string[]> = {};
    for (const s of info?.stages ?? []) m[s.stage] = s.reads;
    return m;
  });
  const readBy = (id: string) => (info?.stages ?? []).filter((s) => s.reads.includes(id)).map((s) => s.stage);
  const shown = $derived(params ? filterParams(params.parameters, { stage: fStage, tag: fTag, text: fText }) : []);
  const sid = (s: string) => s.toUpperCase();
  const stageList = $derived(val && entriesFor(val, 'time').length ? [...STAGES, 'time'] : [...STAGES]);

  function download() {
    if (!val || !info) return;
    const blob = new Blob([exportMatrix(val, info.model_version)], { type: 'application/json' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = t('model.exportFile');
    a.click();
    URL.revokeObjectURL(a.href);
  }
  const groupCount = (stage: string, tag: string) =>
    val?.parameter_groups.find((g) => g.stage === stage && g.tag === tag)?.n_parameters ?? 0;

  const COMMANDS: { key: string; cmd: string }[] = [
    { key: 'model.repro.install', cmd: './install.sh   # Windows: .\\install.ps1' },
    { key: 'model.repro.backend', cmd: '.venv/bin/python -m pytest tests/backend/domain/raven' },
    { key: 'model.repro.frontend', cmd: 'cd frontend && npm run check && npm test && npm run check:bundle' },
    { key: 'model.repro.golden', cmd: '.venv/bin/python scripts/raven_golden.py --set all' },
    { key: 'model.repro.arbiter', cmd: '.venv/bin/python -m scripts.solar_horizon_arbiter --mode api' },
    { key: 'model.repro.d4', cmd: '.venv/bin/python scripts/raven_d4_measure.py' },
  ];
  const statuses: readonly Status[] = STATUSES;
</script>

{#snippet chip(s: Status)}
  <span class="chip chip--{STATUS_LIGHT[s]}" data-status={s}><span class="ic" aria-hidden="true">{STATUS_ICON[s]}</span>{t(K('model.status.' + s))}</span>
{/snippet}

<SubNav title={t('title.model')} learn={t('model.learn')} />
<div class="workspace tile tile--alt">
  <div class="container container--wide">
    <p class="lead" lang={copyLang}>{t('model.intro')}</p>

    {#if loading}
      <p role="status" class="state">{t('model.loading')}</p>
    {:else if failure}
      <div role="alert" class="state state--bad">
        <p>{failure.invalid ? t('model.errorInvalid') : failure.status === 503 ? t('model.error503') : t('model.errorOther', { status: failure.status })}</p>
        <button type="button" class="btn" onclick={load}>{t('model.retry')}</button>
      </div>
    {:else if val && info}
      <p class="muted" data-testid="model-version">{t('model.version', { version: info.model_version, hash: info.registry_sha256.slice(0, 12) })}</p>
      <button type="button" class="btn" onclick={load}>{t('model.refresh')}</button>

      <section aria-labelledby="light-h" class="block">
        <h2 id="light-h">{t('model.light.title')}</h2>
        <p>{t('model.light.intro')}</p>
        <ul class="legend" aria-label={t('model.light.legend')}>
          {#each statuses as s (s)}
            <li data-status={s}>{@render chip(s)} <strong data-testid="count-{s}">{counts?.[s]}</strong>
              <span class="muted small">{t(K('model.statusHelp.' + s))}</span></li>
          {/each}
        </ul>
      </section>

      <section aria-labelledby="pipe-h" class="block">
        <h2 id="pipe-h">{t('model.pipeline.title')}</h2>
        <p>{t('model.pipeline.intro')}</p>
        <ol class="stages">
          {#each stageList as id (id)}
            {@const es = entriesFor(val, id)}
            {@const worst = es.length ? worstStatus(es) : 'unknown'}
            <li>
              <details id="stage-{id}" class="stage" data-stage={id} bind:open={stageOpen[id]}>
                <summary>
                  <span class="sname">{id === 'time' ? t('model.crossCutting') : sid(id)} <span class="muted">{t(K(`model.stage.${id}.name`))}</span></span>
                  {@render chip(worst)}
                </summary>
                <div class="body">
                  {#if !advanced}<p lang={copyLang}><strong>{t('model.plain')}.</strong> {t(K(`model.stage.${id}.plain`))}</p>{/if}
                  {#if advanced}<p lang={copyLang}><strong>{t('model.what')}.</strong> {t(K(`model.stage.${id}.what`))}</p>{/if}
                  {#if id !== 'time'}
                    <p class="small"><strong>{t('model.reads')}:</strong> {(reads[id] ?? []).map(sid).join(', ') || t('model.nobody')}
                      &nbsp;&middot;&nbsp;<strong>{t('model.readBy')}:</strong> {readBy(id).map(sid).join(', ') || t('model.nobody')}</p>
                    {#if advanced}<p class="small muted">{t('model.paramGroups', { V: groupCount(id, 'V'), D: groupCount(id, 'D'), I: groupCount(id, 'I') })}</p>{/if}
                  {/if}
                  <p class="small" data-testid="evidence-progress-{id}">{t('model.evidenceProgress', {
                    verified: es.filter((e) => e.status === 'verified').length, total: es.length,
                  })}</p>
                  {#if worst === 'verified'}
                    <p class="small" data-testid="stage-verified-{id}">{t('model.stageVerified')}</p>
                  {:else if ['s2', 's3', 's4', 's5'].includes(id)}
                    <p class="small" data-testid="validation-gate-{id}"><strong>{t('model.nextEvidence')}:</strong>
                      {t(K(`model.gate.${id}`))}</p>
                  {/if}
                  <h3>{t('model.checks')}</h3>
                  {#if !es.length}
                    <p>{t('model.noChecks')}</p>
                  {:else}
                    <ul class="checks">
                      {#each es as e (e.id)}
                        <li data-entry={e.id}>
                          {@render chip(e.status)}
                          <p class="phrase"><strong>{t('model.f.phrase')}:</strong> {e.phrase}</p>
                          {#if advanced}
                            <dl>
                              <dt>{t('model.f.what')}</dt><dd>{e.what}</dd>
                              <dt>{t('model.f.against')}</dt><dd>{e.against}</dd>
                              <dt>{t('model.f.residual')}</dt><dd>{e.residual}</dd>
                              <dt>{t('model.f.notCovered')}</dt><dd>{e.not_validated || '—'}</dd>
                              <dt>{t('model.f.evidence')}</dt>
                              <dd><ul class="paths">{#each e.evidence as p (p)}<li><code>{p}</code></li>{/each}</ul></dd>
                            </dl>
                          {:else}
                            <p class="small muted">{e.what}</p>
                          {/if}
                        </li>
                      {/each}
                    </ul>
                  {/if}
                </div>
              </details>
            </li>
          {/each}
        </ol>
        <h3>{t('model.limits')}</h3>
        <ul class="plain">{#each info.declared_limits as l (l)}<li>{l}</li>{/each}</ul>
      </section>

      <section aria-labelledby="formulas-h" class="block" data-testid="formulas-section">
        <h2 id="formulas-h">{t('model.formulas.title')}</h2>
        <p>{t('model.formulas.intro')}</p>
        <ul class="plain formulas" lang="en">
          {#each FORMULAS as f (f.id)}
            <li data-formula={f.id}>
              <details>
                <summary><span class="sname">{rt(`f.${f.id}`)}</span>
                  <span><span class="tag tag-{f.tag}" title={t('model.formulas.tag', { tag: f.tag })}>{f.tag}</span> {@render chip(formulaStatus(f.stages))}</span></summary>
                <p class="flines">{#each f.lines as line (line)}<code>{plainLine(line)}</code>{/each}</p>
                <h3>{t('model.formulas.vars')}</h3>
                <dl>{#each f.vars as v (v)}<dt><code>{v}</code> {#if VARS[v].unit}<span class="muted">[{VARS[v].unit}]</span>{/if}</dt><dd>{varMeaning(v)}</dd>{/each}</dl>
              </details>
            </li>
          {/each}
        </ul>
      </section>

      {#if advanced}
        <section aria-labelledby="params-h" class="block" data-testid="params-section">
          <h2 id="params-h">{t('model.params.title')}</h2>
          <p>{t('model.params.intro')}</p>
          {#if paramFail}
            <p role="alert" class="state state--bad">{t('model.errorOther', { status: 'parameters' })} <button type="button" class="btn" onclick={loadParams}>{t('model.retry')}</button></p>
          {:else if !params}
            <p role="status">{t('model.loading')}</p>
          {:else}
            <div class="filters">
              <label>{t('model.params.stage')}
                <select bind:value={fStage}>
                  <option value="">{t('model.params.all')}</option>
                  {#each STAGES as s (s)}<option value={s}>{sid(s)}</option>{/each}
                </select></label>
              <label>{t('model.params.tag')}
                <select bind:value={fTag}>
                  <option value="">{t('model.params.all')}</option>
                  {#each ['V', 'D', 'I'] as g (g)}<option value={g}>{g}</option>{/each}
                </select></label>
              <label>{t('model.params.search')}<input type="search" bind:value={fText} /></label>
            </div>
            <p role="status" data-testid="params-count">{t('model.params.count', { shown: shown.length, total: params.parameters.length })}</p>
            <!-- svelte-ignore a11y_no_noninteractive_tabindex -->
            <div class="tablewrap" tabindex="0" role="region" aria-label={t('model.params.caption')}>
              <table>
                <caption class="visually-hidden">{t('model.params.caption')}</caption>
                <thead><tr>
                  <th scope="col">{t('model.params.name')}</th><th scope="col">{t('model.params.stage')}</th><th scope="col">{t('model.params.tag')}</th>
                  <th scope="col">{t('model.params.default')}</th><th scope="col">{t('model.params.unit')}</th><th scope="col">{t('model.params.range')}</th>
                  <th scope="col">{t('model.params.source')}</th>
                </tr></thead>
                <tbody>
                  {#each shown as p (p.key)}
                    <tr data-tag={p.tag}>
                      <th scope="row"><code>{p.key}</code></th><td>{sid(p.stage)}</td><td><span class="tag tag-{p.tag}">{p.tag}</span></td>
                      <td>{String(p.default)}</td><td>{p.unit}</td><td>{rangeText(p)}</td><td class="src">{p.source}</td>
                    </tr>
                  {:else}
                    <tr><td colspan="7">{t('model.params.none')}</td></tr>
                  {/each}
                </tbody>
              </table>
            </div>
          {/if}
        </section>
      {/if}
    {/if}


    <section aria-labelledby="rep-h" class="block">
      <h2 id="rep-h">{t('model.repro.title')}</h2>
      <p>{t('model.repro.intro')}</p>
      <dl class="cmds">
        {#each COMMANDS as c (c.key)}
          <dt>{t(K(c.key))}</dt><dd><pre><code>{c.cmd}</code></pre></dd>
        {/each}
      </dl>
      {#if advanced && val && info}
        <p>
          <button type="button" class="btn" onclick={download}>{t('model.export')}</button>
          <a href="/api/raven/validation">{t('model.apiLink')}</a>
        </p>
      {/if}
    </section>

    <EngineEstimates />

    <section aria-labelledby="open-h" class="block">
      <h2 id="open-h">{t('model.open.title')}</h2>
      <ul class="plain">
        {#each [1, 2, 3, 4, 5] as n (n)}<li>{t(K(`model.open.${n}`))}</li>{/each}
      </ul>
      <p class="page-links">
        <a href={withBase('/about', BASE)}>{t('about.title')}</a>
      </p>
    </section>
  </div>
</div>

<style>
  .workspace { padding-block: var(--space-5) var(--space-7, 4rem); }
  .lead { max-inline-size: var(--measure); margin-block: 0 var(--space-4); font-size: 1.0625rem; color: var(--c-text); }
  .block { margin-block: var(--space-6, 3rem) 0; }
  .block h2 { font-size: var(--fs-h3); margin-block: 0 var(--space-2); }
  .muted { color: var(--c-muted); }
  .small { font-size: var(--fs-small); }
  .state { padding: var(--space-4); border: 1px solid var(--c-hairline); border-radius: 12px; }
  .state--bad { border-color: var(--c-danger); }
  .btn { min-block-size: var(--target); padding-inline: var(--space-4); border: 1px solid var(--c-action); background: var(--c-action); color: var(--c-on-action); border-radius: 999px; cursor: pointer; font: inherit; }
  .chip { display: inline-flex; align-items: center; gap: 0.4em; padding: 0.15rem 0.6rem; border-radius: 999px; border: 2px solid; font-size: var(--fs-small); background: var(--c-raised); color: var(--c-text); white-space: nowrap; }
  .chip .ic { font-weight: 700; }
  .chip--green { border-color: var(--c-success); } .chip--green .ic { color: var(--c-success); }
  .chip--amber { border-color: var(--c-power); } .chip--amber .ic { color: var(--c-power); }
  .chip--red { border-color: var(--c-danger); } .chip--red .ic { color: var(--c-danger); }
  .chip--grey { border-color: var(--c-control); border-style: dashed; } .chip--grey .ic { color: var(--c-muted); }
  .legend, .plain, .stages, .checks, .paths { list-style: none; margin: 0; padding: 0; }
  .legend li { display: flex; flex-wrap: wrap; align-items: center; gap: var(--space-2); padding-block: 0.25rem; }
  .plain { list-style: disc; padding-inline-start: 1.25rem; }
  .plain li { margin-block: 0.25rem; max-inline-size: var(--measure); }
  .stages { display: grid; grid-template-columns: repeat(auto-fill, minmax(min(100%, 16rem), 1fr)); gap: var(--space-3); counter-reset: st; }
  .stage { border: 1px solid var(--c-hairline); border-radius: 12px; background: var(--c-raised); padding: var(--space-3); }
  .stages li:has(> details[open]) { grid-column: 1 / -1; }
  summary { cursor: pointer; display: flex; flex-wrap: wrap; justify-content: space-between; align-items: center; gap: var(--space-2); min-block-size: var(--target); }
  summary:focus-visible { outline: 3px solid var(--c-focus); outline-offset: 2px; }
  .sname { font-weight: 600; }
  .body { margin-block-start: var(--space-3); }
  .body h3 { font-size: 1rem; margin-block: var(--space-3) var(--space-2); }
  .checks > li { border-top: 1px solid var(--c-hairline); padding-block: var(--space-3); }
  .phrase { margin-block: var(--space-2); }
  dl { margin: 0; }
  dt { font-weight: 600; margin-block-start: var(--space-2); font-size: var(--fs-small); }
  dd { margin: 0; overflow-wrap: anywhere; }
  .paths li { margin-block: 0.15rem; }
  code { overflow-wrap: anywhere; }
  .filters { display: flex; flex-wrap: wrap; gap: var(--space-3); margin-block: var(--space-3); }
  .filters label { display: flex; flex-direction: column; gap: 0.25rem; font-size: var(--fs-small); }
  .filters select, .filters input { min-block-size: var(--target); font: inherit; padding-inline: 0.5rem; background: var(--c-raised); color: var(--c-text); border: 1px solid var(--c-control); border-radius: 8px; }
  .tablewrap { overflow-x: auto; border: 1px solid var(--c-hairline); border-radius: 12px; max-block-size: 70vh; }
  .tablewrap:focus-visible { outline: 3px solid var(--c-focus); }
  table { border-collapse: collapse; inline-size: 100%; font-size: var(--fs-small); }
  th, td { text-align: start; padding: 0.4rem 0.6rem; border-bottom: 1px solid var(--c-hairline); vertical-align: top; }
  thead th { position: sticky; inset-block-start: 0; background: var(--c-bg-alt); }
  .src { min-inline-size: 16rem; }
  .tag { display: inline-block; min-inline-size: 1.6rem; text-align: center; border: 2px solid var(--c-control); border-radius: 6px; font-weight: 700; }
  .tag-V { border-color: var(--c-success); } .tag-D { border-color: var(--c-uplink); } .tag-I { border-color: var(--c-power); }
  .formulas { list-style: none; padding: 0; }
  .formulas > li { border: 1px solid var(--c-hairline); border-radius: 12px; background: var(--c-raised); padding: var(--space-3); margin-block: var(--space-2); max-inline-size: none; }
  .flines code { display: block; margin-block: 0.25rem; padding: 0.25rem 0.5rem; background: var(--c-bg); border-radius: 6px; }
  .cmds dt { margin-block-start: var(--space-3); }
  pre { margin: 0.25rem 0 0; padding: var(--space-3); white-space: pre-wrap; overflow-wrap: anywhere; background: var(--c-bg); border: 1px solid var(--c-hairline); border-radius: 8px; }
  .page-links { display: flex; flex-wrap: wrap; gap: var(--space-3); margin-block-start: var(--space-4); }
  .page-links a { min-block-size: var(--target); display: inline-flex; align-items: center; padding-inline: var(--space-3); border: 1px solid var(--c-control); border-radius: 999px; }
</style>
