<!-- SPDX-License-Identifier: Apache-2.0 -->
<script lang="ts">
  import { CATEGORIES, grant, revoke, isGranted, isStoredGranted, type Category } from './consent';
  import { t, type MessageKey } from '../i18n/i18n.svelte';

  const LABELS: Record<Category, MessageKey> = {
    analytics: 'trust.consent.analytics',
    media: 'trust.consent.media',
  };
  let granted = $state(Object.fromEntries(CATEGORIES.map((c) => [c, isStoredGranted(c)])) as Record<Category, boolean>);
  let message = $state<MessageKey | null>(null);
  let effective = $state(false);

  function toggle(c: Category, input: HTMLInputElement) {
    const revoking = !input.checked;
    const saved = revoking ? revoke(c) : grant(c);
    granted[c] = isStoredGranted(c); // stato reale, non quello richiesto
    input.checked = granted[c];
    effective = isGranted(c);
    if (!saved && revoking) {
      message = 'trust.consent.revokeFailed';
    } else if (!saved && granted[c]) {
      // valore salvato ancora true (es. revoca precedente non salvata) e anche questa scelta non e stata salvata
      message = 'trust.consent.previousFailed';
    } else if (!saved) {
      message = 'trust.consent.failed';
    } else if (!granted[c]) {
      message = 'trust.consent.revoked';
    } else {
      message = 'trust.consent.saved';
    }
  }
</script>

<fieldset>
  <legend>{t('trust.consent.legend')}</legend>
  {#each CATEGORIES as c (c)}
    <p>
      <label>
        <input type="checkbox" checked={granted[c]} onchange={(e) => toggle(c, e.currentTarget)} />
        {t(LABELS[c])}
      </label>
    </p>
  {/each}
</fieldset>
<p role="status">{message ? t(message, { state: t(effective ? 'trust.consent.allowed' : 'trust.consent.blocked') }) : ''}</p>
