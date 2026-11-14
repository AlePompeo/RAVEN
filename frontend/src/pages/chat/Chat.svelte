<!-- SPDX-License-Identifier: Apache-2.0 -->
<script lang="ts">
  import { tick } from 'svelte';
  import { lang, t } from '../../i18n/i18n.svelte';
  import { fetchStatus, fetchSuggestions, LEVELS, MAX_MESSAGE_CHARS, type AssistantMode } from './assistant';
  import { conversation, conversationContext, conversationSession as session } from './conversation.svelte';
  import type { Turn } from './session.svelte';
  import AssistantTurn from './AssistantTurn.svelte';
  import SourcePanel from './SourcePanel.svelte';
  import ModeBadge from './ModeBadge.svelte';
  import PrivacyNote from './PrivacyNote.svelte';
  import SiteFinder from '../../shell/finder/SiteFinder.svelte';
  import { isSiteSearch } from './intent';
  import { explainPrefs } from '../../shell/pageContext.svelte';

  let { pageId = 'chat', embedded = false, onClose }: { pageId?: string; embedded?: boolean; onClose?: () => void } = $props();
  let input = $state('');
  let starters = $state<string[]>([]);
  let statusMode = $state<AssistantMode | 'checking' | null>('checking');
  let statusProvider = $state('');
  let statusExternal = $state<boolean | null>(null);
  let unreachable = $state(false);
  let suggestionsFailed = $state(false);
  let panel = $state<{ id: string; anchor: string; trigger: HTMLElement } | null>(null);
  let copyNote = $state('');
  let inputEl: HTMLTextAreaElement | undefined = $state();
  let viewport: HTMLDivElement | undefined = $state();
  let following = $state(true);
  let retry = $state(0);
  // a request to FIND sites is not answered with prose: it opens the site search card (the brief to check, then the job); a question goes to the assistant
  let finders = $state<{ id: number; text: string }[]>([]);
  let finderSeq = 0;
  const mode = $derived<AssistantMode | 'checking' | null>(session.mode ??
    (conversation.allowExternal ? 'llm' : statusMode === 'llm' && statusExternal !== false ? 'extractive' : statusMode));
  const provider = $derived(session.mode ? session.provider : conversation.allowExternal && conversation.cloudAvailable ? 'groq' :
    statusExternal ? 'assistant-extractive' : statusProvider);
  const privacyMode = $derived(unreachable ? null : conversation.cloudAvailable || statusExternal === true ? 'llm' : statusMode);
  const privacyExternal = $derived(conversation.cloudAvailable || statusExternal === true ? true : statusExternal);
  const sharedContext = $derived(conversationContext());

  $effect(() => { conversation.pageId = pageId; });
  $effect(() => {
    retry;
    const language = lang.current;
    const page = pageId;
    const ctrl = new AbortController();
    unreachable = false; suggestionsFailed = false; statusMode = 'checking';
    void fetchStatus(fetch, ctrl.signal).then((s) => {
      if (ctrl.signal.aborted) return;
      statusMode = s.mode; statusProvider = s.provider; statusExternal = s.external;
      conversation.cloudAvailable = s.cloudAvailable;
      if (!s.cloudAvailable && s.external !== true) conversation.allowExternal = false;
    }, () => {
      if (!ctrl.signal.aborted) {
        statusMode = null; statusProvider = ''; statusExternal = null; unreachable = true;
        conversation.cloudAvailable = false; conversation.allowExternal = false;
      }
    });
    void fetchSuggestions(fetch, page, language, ctrl.signal).then((items) => {
      starters = items.map((item) => item.question);
    }, () => { if (!ctrl.signal.aborted) suggestionsFailed = true; });
    return () => ctrl.abort();
  });
  $effect(() => {
    session.turns.at(-1)?.content;
    if (following) void tick().then(() => { if (viewport) viewport.scrollTop = viewport.scrollHeight; });
  });

  async function ask(question: string) {
    if (session.busy) return;
    copyNote = ''; following = true;
    if (isSiteSearch(question)) { finders = [...finders, { id: ++finderSeq, text: question }]; input = ''; return; }
    const succeeded = await session.send(question);
    if (succeeded) input = '';
  }
  function fresh() {
    session.reset(); input = ''; copyNote = ''; panel = null; following = true; finders = [];
    inputEl?.focus();
  }
  function changeOnline(e: Event) {
    const checked = (e.currentTarget as HTMLInputElement).checked;
    fresh();
    conversation.allowExternal = checked;
  }
  function onKey(e: KeyboardEvent) {
    if (e.key === 'Enter' && !e.shiftKey && !e.isComposing && !e.ctrlKey && !e.metaKey && !e.altKey) {
      e.preventDefault();
      (e.currentTarget as HTMLTextAreaElement).form?.requestSubmit();
    }
  }
  async function copy(turn: Turn) {
    try { await navigator.clipboard.writeText(turn.content); copyNote = t('si.copied'); }
    catch { copyNote = t('si.copyFailed'); }
  }
</script>

<div class="si-workspace" class:embedded data-testid="raven-si">
  <aside class="rail">
    <span class="monogram" aria-hidden="true">R</span>
    <strong>RAVEN SI</strong>
    <p>{t('si.tagline')}</p>
    <div class="conversation-label"><span class="dot"></span>{session.turns.find((turn) => turn.role === 'user')?.content.slice(0, 76) || t('si.new')}</div>
    <p class="rail-note">{t('si.memory')}</p>
    <p class="rail-note">{t('si.engineNotice')}</p>
  </aside>
  <section class="workspace" aria-label="RAVEN SI">
    <header class="head">
      <div>
        {#if embedded}<h2 id="raven-si-title">RAVEN SI</h2>{:else}<h1 id="raven-si-title">RAVEN SI</h1>{/if}
        <ModeBadge {mode} {provider} model={session.mode ? session.model : ''} />
      </div>
      <div class="head-actions">
        <button type="button" class="quiet" onclick={fresh} aria-label={t('si.new')}>＋ <span>{t('si.new')}</span></button>
        <details class="settings">
          <summary aria-label={t('si.settings')}>☷</summary>
          <div class="settings-panel">
            <label for="chat-level">{t('si.level')}</label>
            <select id="chat-level" bind:value={conversation.level}>
              {#each LEVELS as level}<option value={level}>{t(level === 'principiante' ? 'si.beginner' : level === 'tecnico' ? 'si.technical' : 'si.intermediate')}</option>{/each}
            </select>
            <label for="chat-lang">{t('si.language')}</label>
            <select id="chat-lang" bind:value={conversation.language}>
              <option value="auto">{t('si.auto')}</option><option value="it">Italiano</option><option value="en">English</option>
            </select>
            <label class="check"><input type="checkbox" bind:checked={conversation.includeContext} />{t('si.includeContext')}</label>
            <p>{t('si.contextScope')}</p>
            <label class="check"><input type="checkbox" bind:checked={explainPrefs.questionKey} />{t('si.questionShortcut')}</label>
          </div>
        </details>
        {#if onClose}<button type="button" class="quiet minimize" onclick={onClose} aria-label={t('si.minimize')}>—</button>{/if}
      </div>
    </header>
    <div class="messages" bind:this={viewport} onscroll={() => { if (viewport) following = viewport.scrollHeight - viewport.scrollTop - viewport.clientHeight < 80; }}>
      {#if unreachable}<p class="notice" data-testid="assistant-unreachable">{t('si.unreachable')} <button type="button" onclick={() => retry++}>{t('shell.retry')}</button></p>{/if}
      {#if !session.turns.length && !finders.length}
        <section class="welcome">
          <span class="welcome-mark" aria-hidden="true">R</span>
          <h2>{t('si.welcome')}</h2>
          <p>{t('si.intro')}</p>
          {#if starters.length}<ul class="starters" aria-label={t('si.suggestions')}>
            {#each starters.slice(0, 4) as question}<li><button type="button" onclick={() => ask(question)}>{question}<span aria-hidden="true">↗</span></button></li>{/each}
          </ul>{/if}
          {#if suggestionsFailed}<p class="muted">{t('si.suggestionsFailed')}</p>{/if}
        </section>
      {/if}
      <ol class="history" aria-label={t('si.conversation')}>
        {#each session.turns as turn (turn.id)}
          <li class="message" data-role={turn.role} id="turn-{turn.id}">
            {#if turn.role === 'user'}<p class="user-text">{turn.content}</p>
            {:else}<AssistantTurn {turn} {starters} busy={session.busy}
              onOpenSource={(id, anchor, trigger) => panel = { id, anchor, trigger }}
              onAsk={ask} onCopy={copy} />{/if}
          </li>
        {/each}
      </ol>
      {#each finders as f (f.id)}
        <section class="finder-turn" data-testid="chat-finder"><p class="user-text">{f.text}</p><SiteFinder initialText={f.text} autoRead /></section>
      {/each}
      {#if session.error}<p role="alert" class="notice">{session.error}</p>{/if}
      {#if copyNote}<p class="muted" aria-hidden="true">{copyNote}</p>{/if}
    </div>
    <div class="composer-wrap">
      <details class="context" data-testid="explain-context" open={conversation.includeContext}>
        <summary>{t('si.page', { page: pageId })}</summary>
        {#if sharedContext.simulation_id}<p>{sharedContext.simulation_id}</p>{/if}
        <div class="context-values">{#each Object.entries(sharedContext.params ?? {}) as [key, value] (key)}<span>{key} = {value}</span>{/each}</div>
      </details>
      {#if !following && session.turns.length}<button type="button" class="latest" onclick={() => { following = true; if (viewport) viewport.scrollTop = viewport.scrollHeight; }}>{t('si.latest')} ↓</button>{/if}
      <div class="connection">
        <label class="check"><input type="checkbox" checked={conversation.allowExternal} disabled={session.busy || unreachable || (!conversation.cloudAvailable && statusExternal !== true)} onchange={changeOnline} />{t('si.online')}</label>
        <span>{t(conversation.cloudAvailable || statusExternal === true ? 'si.switchNotice' : 'si.notConfigured')}</span>
      </div>
      <PrivacyNote mode={privacyMode} provider={statusProvider} external={privacyExternal} id="chat-notice" />
      <form class="composer" onsubmit={(e) => { e.preventDefault(); if (input.trim()) void ask(input); }}>
        <label class="visually-hidden" for="chat-input">{t('si.question')}</label>
        <textarea id="chat-input" rows="2" maxlength={MAX_MESSAGE_CHARS} autocomplete="off" bind:value={input} data-autofocus
          bind:this={inputEl} onkeydown={onKey} placeholder={t('si.placeholder')} aria-describedby="chat-hint"></textarea>
        <div class="composer-actions">
          <span class="counter">{input.length}/{MAX_MESSAGE_CHARS}</span>
          <button type="button" class="quiet" aria-disabled={!session.busy ? 'true' : undefined} onclick={() => session.busy && session.stop()}>{t('si.stop')}</button>
          <button type="submit" class="send" aria-disabled={session.busy ? 'true' : undefined}>{t(session.busy ? 'si.generating' : 'si.send')} <span aria-hidden="true">↑</span></button>
        </div>
      </form>
      <p class="hint" id="chat-hint">{t('si.hint')}</p>
      <p role="status" class="visually-hidden" data-testid="assistant-status">{session.status}{copyNote ? ` ${copyNote}` : ''}</p>
    </div>
  </section>
</div>
{#if panel}<SourcePanel id={panel.id} anchor={panel.anchor} trigger={panel.trigger} onClose={() => panel = null} />{/if}

<style>
  .composer-wrap .context { font-size: .78rem; color: #b7c8db; max-block-size: 6rem; overflow: auto; margin-bottom: .45rem; }
  .context summary { cursor: pointer; font-size: .78rem; } .context p { margin: .25rem 0; }
  .context-values { display: flex; flex-wrap: wrap; gap: .3rem 1rem; padding: .3rem 0; overflow-wrap: anywhere; }
  .si-workspace { --c-bg: #101725; --c-bg-alt: #151e2f; --c-raised: #1b283c; --c-text: #e8edf5; --c-muted: #a9b8cb; --c-hairline: #334157; --c-link: #b6d6f4; color: var(--c-text); background: var(--c-bg); display: grid; grid-template-columns: 13.5rem minmax(0, 1fr); height: min(54rem, calc(100dvh - var(--nav-h, 80px) - 2rem)); min-height: 32rem; overflow: hidden; max-width: 90rem; margin-inline: auto; }
  .si-workspace.embedded { height: 100%; min-height: 0; border-radius: inherit; }
  .rail { padding: 2rem 1.25rem; display: flex; flex-direction: column; gap: .75rem; background: #0b111d; border-inline-end: 1px solid #29374a; font-size: .85rem; }
  .rail p { color: #a9b8cb; line-height: 1.6; margin: 0; }
  .rail-note { font-size: .75rem; } .conversation-label { margin-block: 2rem auto; padding: .8rem; border: 1px solid #334157; border-radius: .75rem; overflow-wrap: anywhere; }
  .dot { display: inline-block; width: .45rem; height: .45rem; background: #b6d6f4; border-radius: 50%; margin-inline-end: .5rem; }
  .monogram, .welcome-mark { display: grid; place-items: center; width: 2.5rem; height: 2.5rem; background: linear-gradient(140deg, #263d58, #132134); color: #c9e6ff; border: 1px solid #54718f; border-radius: .8rem; font: 600 1.3rem Orbitron, sans-serif; }
  .workspace { min-width: 0; min-height: 0; display: flex; flex-direction: column; position: relative; }
  .head { padding: 1rem 1.5rem; border-bottom: 1px solid #29374a; display: flex; justify-content: space-between; gap: .5rem; align-items: center; }
  .head :global(h1), .head :global(h2) { font: 600 1.15rem Orbitron, sans-serif; margin: 0 0 .4rem; }
  .head :global(.status-pill) { margin: 0; font-size: .72rem; color: #b9c9dc; }
  .head-actions, .composer-actions { display: flex; align-items: center; gap: .4rem; }
  button, summary { min-height: 44px; cursor: pointer; } button { font: inherit; border-radius: .7rem; }
  .quiet, summary { background: transparent; color: #c0cede; border: 1px solid transparent; padding: .5rem .7rem; min-width: 44px; }
  .quiet:hover, summary:hover { background: #26364c; border-color: #47607c; }
  .settings { position: relative; } summary { list-style: none; font-size: 1.5rem; } summary::-webkit-details-marker { display: none; }
  .settings-panel { position: absolute; z-index: 3; inset-inline-end: 0; top: 100%; width: min(19rem, calc(100vw - 3rem)); padding: 1rem; border: 1px solid #54718f; background: #172235; box-shadow: 0 8px 30px #0008; border-radius: 1rem; font-size: .85rem; }
  .settings-panel > label { display: block; margin-block: .6rem; } .settings-panel p { color: #b8c5d6; }
  select { width: 100%; min-height: 44px; background: #0e1726; color: #e8edf5; border: 1px solid #5a7391; padding: .5rem; border-radius: .5rem; }
  .messages { min-height: 0; flex: 1; overflow-y: auto; overscroll-behavior: contain; padding: 1.5rem clamp(1rem, 4vw, 3rem); scrollbar-gutter: stable; }
  .welcome { max-width: 42rem; margin: 1rem auto 2rem; } .welcome-mark { width: 3rem; height: 3rem; margin-block-end: 1.25rem; }
  .welcome h2 { font: 500 clamp(1.4rem, 2.5vw, 2rem)/1.3 var(--font-sans, sans-serif); margin: 0 0 .8rem; }
  .welcome p { color: #b1c0d3; line-height: 1.65; } .context { font-size: .8rem; }
  .starters { padding: 0; list-style: none; display: grid; grid-template-columns: 1fr 1fr; gap: .7rem; margin-block-start: 1.5rem; }
  .starters button { background: #162237; border: 1px solid #374d68; color: #dce8f7; width: 100%; height: 100%; text-align: start; padding: .85rem; display: flex; justify-content: space-between; gap: .75rem; font-size: .85rem; }
  .starters button:hover { background: #21334c; border-color: #a5c9e9; }
  .history { list-style: none; padding: 0; margin: 0 auto; max-width: 48rem; display: grid; gap: 1.5rem; }
  .message { min-width: 0; } .message[data-role='user'] { justify-self: end; max-width: 88%; background: #263a53; border: 1px solid #3d5571; border-radius: 1.25rem 1.25rem .25rem 1.25rem; padding: .75rem 1.1rem; }
  .user-text { white-space: pre-wrap; overflow-wrap: anywhere; margin: 0; line-height: 1.6; }
  .composer-wrap { flex: none; padding: .6rem clamp(1rem, 4vw, 3rem) .8rem; background: linear-gradient(#101725ee, #101725); }
  .composer { max-width: 48rem; margin-inline: auto; border: 1px solid #536d8b; background: #19263a; border-radius: 1.2rem; padding: .7rem; box-shadow: 0 5px 25px #0003; }
  .composer:focus-within { border-color: #b6d6f4; box-shadow: 0 0 0 2px #8ac1f133; }
  textarea { display: block; box-sizing: border-box; width: 100%; resize: vertical; min-height: 3.5rem; max-height: 10rem; border: 0; background: transparent; color: #edf4ff; font: inherit; line-height: 1.5; padding: .4rem; }
  textarea::placeholder { color: #a8b9cf; } textarea:focus { outline: none; }
  .composer-actions { justify-content: flex-end; } .counter { margin-inline-end: auto; font-size: .7rem; color: #a9b8cb; }
  .send { color: #102037; background: #cae4ff; border: 1px solid #cae4ff; padding: .5rem .9rem; font-weight: 600; }
  [aria-disabled='true'] { opacity: .55; } .hint { margin: .5rem auto 0; max-width: 48rem; font-size: .7rem; color: #a9b8cb; text-align: center; }
  .connection { display: flex; flex-wrap: wrap; gap: .35rem 1rem; align-items: center; max-width: 48rem; margin: 0 auto .6rem; font-size: .72rem; color: #b3c4d9; }
  .check { display: inline-flex; gap: .5rem; align-items: center; min-height: var(--target, 28px); } input[type='checkbox'] { accent-color: #b6d6f4; }
  .notice { border-inline-start: 3px solid #d6ba7c; padding: .75rem; background: #263148; } .muted { color: #b1c0d3; font-size: .85rem; }
  .latest { display: block; margin: -.5rem auto .5rem; padding: .3rem .8rem; color: #dcecff; background: #263c58; border: 1px solid #7396b7; box-shadow: 0 2px 8px #0006; }
  @media (max-width: 850px) { .si-workspace { grid-template-columns: minmax(0, 1fr); } .rail { display: none; } }
  @media (max-width: 540px) { .head { padding: .75rem; } .head-actions .quiet span { display: none; } .head :global(.status-pill) { max-width: 13rem; overflow-wrap: anywhere; } .messages { padding: 1rem; } .starters { grid-template-columns: 1fr; } .composer-wrap { padding: .5rem .65rem max(.5rem, env(safe-area-inset-bottom)); } .connection { font-size: .68rem; } .hint { font-size: .65rem; } }
</style>
