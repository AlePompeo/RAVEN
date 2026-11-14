<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- Icona del set unico (icons.ts): sempre decorativa, il nome accessibile sta sul controllo. -->
<script lang="ts">
  import { ICONS, type IconName } from './icons';

  let { name, size = 20 }: { name: IconName; size?: number } = $props();
</script>

<svg class="icon" viewBox="0 0 24 24" width={size} height={size} aria-hidden="true" focusable="false"><path d={ICONS[name]} /></svg>

<style>
  .icon {
    flex: none;
    width: var(--icon-size, 1.25rem);
    height: var(--icon-size, 1.25rem);
    fill: none;
    stroke: currentColor;
    stroke-width: 1.5;
    stroke-linecap: round;
    stroke-linejoin: round;
    vector-effect: non-scaling-stroke;
  }
</style>
