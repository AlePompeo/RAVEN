<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- Etichetta V (fonte primaria), D (derivato), I (illustrativo): lettera + forma del bordo, mai il solo colore. -->
<script lang="ts">
  const LONG: Record<string, string> = {
    V: 'valore letto in una fonte primaria',
    D: 'derivato con formula ripetibile',
    I: 'illustrativo, nessuna fonte',
  };
  let { status }: { status: string } = $props();
</script>

<span class="badge" data-status={status}>{status}<span class="visually-hidden"> ({LONG[status] ?? status})</span></span>

<style>
  .badge {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    min-width: 1.5rem;
    height: 1.5rem;
    padding: 0 0.35rem;
    border-radius: var(--radius-xs);
    border: 1.5px solid var(--c-text);
    font-size: var(--fs-micro);
    font-weight: 700;
    line-height: 1;
    color: var(--c-text);
    vertical-align: middle;
  }
  .badge[data-status='V'] {
    background: var(--c-text);
    color: var(--c-bg);
  }
  .badge[data-status='D'] {
    border-style: double;
    border-width: 4px;
  }
  .badge[data-status='I'] {
    border-style: dashed;
  }
</style>
