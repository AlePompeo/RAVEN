<!-- SPDX-License-Identifier: Apache-2.0 -->
<!--
  Scheda di un membro. Il membro viene rivalidato qui (parseMember) oltre che in Contacts: ogni valore è mostrato
  come testo (mai {@html}); il link LinkedIn esiste solo se l'URL passa safeLinkedin; la foto solo se è un file
  locale sotto /team/. Senza foto: avatar con le iniziali, disegnato con i token (nessuna immagine esterna).
-->
<script lang="ts">
  import { withBase } from '../../shell/router';
  import { parseMember, fullName, initials, isPlaceholder, type TeamMember } from './team';

  let { member }: { member: TeamMember } = $props();

  const m = $derived(parseMember(member));
  const name = $derived(m ? fullName(m) : '');
  const placeholder = $derived(m ? isPlaceholder(m) : false);
  let broken = $state(false);
  const photo = $derived(m?.photo && !broken ? withBase(m.photo, import.meta.env.BASE_URL) : null);
</script>

{#if m}
  <article class="member" aria-labelledby={`m-${m.id}-name`} data-testid="member" data-placeholder={placeholder ? '1' : undefined}>
    <div class="photo">
      {#if photo}
        <img
          src={photo}
          alt={`Foto di ${name}`}
          width="512"
          height="512"
          loading="lazy"
          decoding="async"
          referrerpolicy="no-referrer"
          onerror={() => (broken = true)}
        />
      {:else}
        <div class="avatar" role="img" aria-label={`Avatar con le iniziali di ${name}`} data-testid="avatar">
          <span aria-hidden="true">{initials(m.firstName, m.lastName)}</span>
        </div>
      {/if}
    </div>
    <div class="info">
      <h2 id={`m-${m.id}-name`}>{name}</h2>
      {#if m.role}<p class="role">{m.role}</p>{/if}
      {#if placeholder}
        <p class="todo" data-testid="todo">Profilo da completare</p>
      {/if}
      {#if m.bio}<p class="bio">{m.bio}</p>{/if}
      {#if m.linkedin}
        <a
          class="btn btn--ghost li"
          href={m.linkedin}
          target="_blank"
          rel="noopener noreferrer"
          aria-label={`Profilo LinkedIn di ${name} (si apre in una nuova scheda)`}
        >
          <svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true" focusable="false">
            <rect x="3" y="3" width="18" height="18" rx="4" />
            <circle cx="8" cy="8.2" r="0.6" />
            <path d="M8 11v6M12 17v-6M12 13.5a2.5 2.5 0 0 1 5 0V17" />
          </svg>
          LinkedIn
        </a>
      {/if}
    </div>
  </article>
{/if}

<style>
  .member {
    display: flex;
    flex-direction: column;
    gap: var(--space-4);
    padding: var(--space-4);
    background: linear-gradient(145deg, #19293d, var(--c-raised) 70%);
    border: 1px solid var(--c-hairline);
    border-radius: var(--radius-lg);
    box-shadow: 0 16px 38px rgb(0 0 0 / 0.2);
    min-width: 0;
  }
  .photo {
    aspect-ratio: 1 / 1;
    width: 100%;
    max-width: 22rem;
    margin-inline: auto;
    border-radius: var(--radius-lg);
    overflow: hidden;
    background: var(--c-bg-alt);
  }
  .photo img {
    display: block;
    width: 100%;
    height: 100%;
    object-fit: cover;
  }
  .avatar {
    width: 100%;
    height: 100%;
    display: grid;
    place-items: center;
    background: radial-gradient(circle at 50% 35%, #294e72, #0c1523 72%);
    border: 1px solid var(--c-hairline);
    border-radius: var(--radius-lg);
    box-sizing: border-box;
    color: var(--c-text);
    font-size: clamp(3rem, 12vw, 5.5rem);
    font-weight: 300;
    font-stretch: var(--wdth-heading);
    letter-spacing: 0.02em;
    user-select: none;
  }
  .info {
    display: flex;
    flex-direction: column;
    align-items: flex-start;
    gap: var(--space-2);
    min-width: 0;
  }
  h2 {
    margin: 0;
    font-size: var(--fs-h2);
    font-size: clamp(1.75rem, 1.35rem + 1.2vw, 2.5rem);
    line-height: var(--lh-heading);
    overflow-wrap: anywhere;
  }
  .role {
    margin: 0;
    font-size: var(--fs-small);
    color: var(--c-muted);
  }
  .todo {
    margin: 0;
    font-size: var(--fs-small);
    color: var(--c-text);
    border: 1px solid var(--c-control);
    border-radius: var(--radius-pill);
    padding: 0.125rem 0.75rem;
  }
  .bio {
    margin: var(--space-2) 0 var(--space-2);
    max-width: var(--measure);
    overflow-wrap: anywhere;
    white-space: pre-line;
  }
  .li svg {
    flex: none;
    fill: none;
    stroke: currentColor;
    stroke-width: 1.5;
    stroke-linecap: round;
    stroke-linejoin: round;
    width: var(--icon-size, 1.25rem);
    height: var(--icon-size, 1.25rem);
  }
  .li svg circle {
    fill: currentColor;
  }
  .li {
    margin-top: auto;
  }
</style>
