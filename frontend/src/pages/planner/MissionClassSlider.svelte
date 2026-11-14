<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- Mission-class slider: four NAMED positions (not a continuous number). A native range input, so arrow keys, Home and End work.
     It only chooses which class scenario feeds the RAVEN estimates; whatever the user declares always wins. -->
<script lang="ts">
  import { t, type MessageKey } from '../../i18n/i18n.svelte';
  import { DEFAULT_MISSION_CLASS, MISSION_CLASS_IDS, type MissionClassId } from './estimates/missionClass';
  let { value = $bindable() }: { value: MissionClassId | undefined } = $props();
  const current = $derived(value ?? DEFAULT_MISSION_CLASS);
  const index = $derived(MISSION_CLASS_IDS.indexOf(current));
  const name = (id: MissionClassId) => t(`class.${id}` as MessageKey);
</script>

<fieldset class="class-slider" data-testid="mission-class">
  <legend>{t('class.legend')}</legend>
  <p>{t('class.scope')}</p>
  <label for="mission-class-range">{t('class.slider')}: <strong data-testid="mission-class-name">{name(current)}</strong></label>
  <input id="mission-class-range" type="range" min="0" max="3" step="1" value={index}
    aria-valuetext={name(current)}
    oninput={(e) => { value = MISSION_CLASS_IDS[e.currentTarget.valueAsNumber]; }} />
  <ol class="ticks" aria-hidden="true">{#each MISSION_CLASS_IDS as id}<li class:on={id === current}>{name(id)}{id === DEFAULT_MISSION_CLASS ? ` (${t('class.default')})` : ''}</li>{/each}</ol>
</fieldset>

<style>
  .class-slider { margin-block: 1.5rem; border: 1px solid #7b9cb36e; border-radius: .65rem; padding: 1rem; }
  label { display: block; font-weight: 600; margin-block: .5rem; }
  input[type='range'] { width: 100%; min-height: 44px; accent-color: #9bdfff; }
  input[type='range']:focus-visible { outline: 2px solid #b1e6ff; outline-offset: 3px; }
  .ticks { display: grid; grid-template-columns: repeat(4, 1fr); gap: .5rem; list-style: none; margin: 0; padding: 0; font-size: .85rem; }
  .ticks li { opacity: .75; } .ticks li.on { opacity: 1; font-weight: 700; }
  @media (max-width: 650px) { .ticks { grid-template-columns: 1fr 1fr; } }
</style>
