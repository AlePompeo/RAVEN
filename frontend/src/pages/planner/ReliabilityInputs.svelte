<!-- SPDX-License-Identifier: Apache-2.0 -->
<script lang="ts">
  import { t } from '../../i18n/i18n.svelte';
  import { COMPONENT_FIELDS, PROFILE_FIELDS, PROTECTIONS, componentFields, profileFields, illustrativeReliability, type ReliabilityProfile } from './reliability';
  let { profile = $bindable() }: { profile: ReliabilityProfile } = $props();
</script>

<section class="reliability-inputs" data-testid="reliability-inputs">
  <h3>{t('rel.title')}</h3>
  <label class="check"><input id="rel-enabled" type="checkbox" bind:checked={profile.enabled} />{t('rel.enable')}</label>
  <button type="button" onclick={() => profile = illustrativeReliability(t('rel.exampleBasis'))}>{t('rel.example')}</button>
  <p class="note">{t('rel.noDefaults')}</p>
  {#if profile.enabled}
    <label for="rel-basis">{t('rel.basis')}</label>
    <textarea id="rel-basis" rows="2" maxlength="1000" bind:value={profile.basis}></textarea>
    <p>{t('rel.fractions')}</p>
    <div class="fields">
      {#each profileFields as key}
        {@const bounds = PROFILE_FIELDS[key]}
        <div><label for={`rel-${key}`}>{t(`rel.field.${key}`)} ({bounds[2]})</label>
          <input id={`rel-${key}`} type="number" min={bounds[0]} max={bounds[1]} step="any"
            value={profile[key] ?? ''} placeholder={t('report.notProvided')}
            oninput={(e) => profile[key] = e.currentTarget.value === '' ? null : e.currentTarget.valueAsNumber} />
        </div>
      {/each}
    </div>
    <label class="check"><input id="rel-apply-power" type="checkbox" bind:checked={profile.apply_thermal_load} />{t('rel.applyPower')}</label>
    {#each profile.components as component}
      <details>
        <summary>{t(`rel.component.${component.id}`)}</summary>
        <label for={`rel-${component.id}-protection`}>{t('rel.protection')}</label>
        <select id={`rel-${component.id}-protection`} bind:value={component.protection}>
          {#each PROTECTIONS as protection}<option value={protection}>{t(`rel.protection.${protection}`)}</option>{/each}
        </select>
        <div class="fields">
          {#each componentFields as key}
            {@const bounds = COMPONENT_FIELDS[key]}
            <div><label for={`rel-${component.id}-${key}`}>{t(`rel.field.${key}`)} ({bounds[2]})</label>
              <input id={`rel-${component.id}-${key}`} type="number" min={bounds[0]} max={bounds[1]} step="any"
                value={component[key] ?? ''} placeholder={t('report.notProvided')}
                oninput={(e) => component[key] = e.currentTarget.value === '' ? null : e.currentTarget.valueAsNumber} />
            </div>
          {/each}
        </div>
      </details>
    {/each}
  {/if}
</section>

<style>
  .reliability-inputs { margin-block: 2rem; padding: 1.2rem; border: 1px solid #7499b64d; border-radius: .8rem; }
  h3 { margin-top: 0; } p { line-height: 1.6; } .note { color: var(--c-muted); font-size: .85rem; }
  label { display: block; font-weight: 600; margin-block: 1rem .5rem; }
  .check { display: flex; align-items: center; gap: .75rem; }
  input:not([type='checkbox']), textarea, select { box-sizing: border-box; width: 100%; min-height: 44px; padding: .7rem; color: inherit; background: #081426; border: 1px solid #7b9cb36e; border-radius: .65rem; }
  input[type='checkbox'] { width: 1.2rem; height: 1.2rem; flex-shrink: 0; accent-color: #9bdfff; }
  .fields { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: .5rem 1rem; }
  details { margin-top: 1rem; border-top: 1px solid #7499b64d; padding-top: .5rem; }
  summary { min-height: 44px; cursor: pointer; font-weight: 600; align-content: center; }
  button { min-height: 44px; padding: .7rem 1rem; color: inherit; background: #11263c; border: 1px solid #7693aa69; border-radius: .5rem; }
  button:focus-visible, input:focus-visible, textarea:focus-visible, select:focus-visible, summary:focus-visible { outline: 2px solid #b1e6ff; outline-offset: 3px; }
  @media (max-width: 650px) { .fields { grid-template-columns: 1fr; } }
</style>
