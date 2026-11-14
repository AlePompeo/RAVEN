<!-- SPDX-License-Identifier: Apache-2.0 -->
<!--
  Siti personalizzati: coordinate qualsiasi sulla Luna (al massimo 8 per scenario). Campi numerici con messaggi di
  errore, scelta sul globo, elenco con rimozione e, per ogni sito, la stima dei dati di terreno (nessun download
  qui: la conferma viene chiesta alla prima richiesta che li serve). Il terreno fuori da ogni prodotto LOLA e'
  SCONOSCIUTO e resta tale: orizzonte e profilo RF diventano ignoti, geometria, efemeridi, DSN e perdita in spazio
  libero restano validi (mai un orizzonte piatto spacciato per vero).
-->
<script lang="ts">
  import { onMount } from 'svelte';
  import { t, type MessageKey } from '../i18n/i18n.svelte';
  import { raven, type TerrainEstimate, type TerrainEstimateSite } from './ravenApi';
  import { scenarioStore } from './scenario';
  import {
    customSites, makeId, MAX_CUSTOM_SITES, validateForm, type CustomErrors, type CustomSiteDef,
  } from './customSites';
  import ModeOnly from './ModeOnly.svelte';
  import GlobePicker from './GlobePicker.svelte';

  let { onadd }: { onadd?: (id: string) => void } = $props();

  let list = $state<readonly CustomSiteDef[]>(customSites.get());
  let name = $state('');
  let lat = $state('');
  let lon = $state('');
  let panel = $state('');
  let antenna = $state('');
  let errors = $state<CustomErrors>({});
  let picker = $state(false);
  let estimate = $state<TerrainEstimate | null>(null);
  let estState = $state<'idle' | 'loading' | 'ok' | 'invalid' | 'unavailable' | 'error'>('idle');
  let ctrl: AbortController | null = null;

  onMount(() => customSites.subscribe((l) => { list = l; void refresh(); }));

  async function refresh() {
    ctrl?.abort();
    if (list.length === 0) { estimate = null; estState = 'idle'; return; }
    ctrl = new AbortController();
    estState = 'loading';
    const r = await raven.terrainEstimate([...list], { signal: ctrl.signal });
    if (r.ok) { estimate = r.data; estState = 'ok'; }
    else if (r.kind === 'aborted') return;
    else { estimate = null; estState = r.kind === 'invalid' ? 'invalid' : r.kind === 'unavailable' ? 'unavailable' : 'error'; }
  }

  function add(e: Event) {
    e.preventDefault();
    if (list.length >= MAX_CUSTOM_SITES) return;
    const v = validateForm({ name, lat, lon, panel, antenna });
    if (!v.ok) { errors = v.errors; return; }
    errors = {};
    const id = makeId(v.value.name, new Set(list.map((s) => s.id)));
    const site: CustomSiteDef = { id, ...v.value };
    scenarioStore().set({ customSites: [...list, site] });
    scenarioStore().flush();
    name = lat = lon = panel = antenna = '';
    picker = false;
    onadd?.(id);
  }
  let busyId = $state<string | null>(null);
  // scarica ora il terreno di un sito: stessa richiesta (e stessa conferma) che farebbe una pagina
  async function download(id: string) {
    busyId = id;
    await raven.horizon({ site: id, height_m: 2 });
    busyId = null;
    await refresh();
  }
  function remove(id: string) {
    const st = scenarioStore();
    st.set({ customSites: list.filter((s) => s.id !== id), ...(st.get().site === id ? { site: null } : {}) });
    st.flush();
  }
  function picked(la: number, lo: number) { lat = String(la); lon = String(lo); errors = { ...errors, lat: undefined, lon: undefined } as CustomErrors; }

  const row = (id: string): TerrainEstimateSite | undefined => estimate?.sites.find((s) => s.id === id);
  const num = (x: number | null | undefined, d = 0) => (x === null || x === undefined ? '' : x.toFixed(d));
  const msg = (f: keyof CustomErrors) => (errors[f] ? t(`custom.err.${f}.${errors[f]}` as MessageKey) : '');
</script>

<section class="custom" aria-labelledby="custom-title" data-testid="custom-panel">
  <h3 id="custom-title">{t('custom.title')}</h3>
  <p>{t('custom.intro')}</p>

  {#if list.length > 0}
    <ul class="sites" data-testid="custom-list">
      {#each list as s (s.id)}
        {@const r = row(s.id)}
        <li>
          <strong>{s.name}</strong>
          <span class="coords">{s.lat_deg.toFixed(4)}°, {s.lon_deg_east.toFixed(4)}°</span>
          <button type="button" onclick={() => remove(s.id)} aria-label={`${t('custom.remove')}: ${s.name}`}>{t('custom.remove')}</button>
          <div class="terrain" aria-live="polite">
            {#if estState === 'loading'}{t('custom.terrain.loading')}
            {:else if estState === 'invalid'}{t('custom.terrain.invalid')}
            {:else if estState === 'unavailable'}{t('custom.terrain.unavailable')}
            {:else if estState === 'error'}{t('custom.terrain.error')}
            {:else if r && r.terrain_available}
              {#if r.tiles_to_download > 0}
                {t('custom.terrain.needs').replace('{mb}', num(r.mb_to_download, 1)).replace('{res}', num(r.resolution_m))}
                <button type="button" onclick={() => download(s.id)} disabled={busyId !== null} data-testid="custom-download">{busyId === s.id ? t('custom.downloading') : t('custom.download')}</button>
              {:else}
                {t('custom.terrain.cached').replace('{res}', num(r.resolution_m))}
              {/if}
              {#if r.range_km !== null && r.range_km < 200}<span> {t('custom.terrain.range').replace('{km}', num(r.range_km))}</span>{/if}
            {:else if r}
              <strong>{t('custom.terrain.unknown')}</strong>
              <ModeOnly mode="learning"><span> {t('custom.terrain.unknownLearn')}</span></ModeOnly>
              <ModeOnly mode="avanzato"><span> {t(r.status === 'exceeds_site_cap' ? 'custom.terrain.unknownCap' : 'custom.terrain.unknownAdv')}</span></ModeOnly>
            {/if}
          </div>
        </li>
      {/each}
    </ul>
    <p class="count">{t('custom.count').replace('{n}', String(list.length)).replace('{max}', String(MAX_CUSTOM_SITES))}</p>
  {/if}

  {#if list.length >= MAX_CUSTOM_SITES}
    <p role="status">{t('custom.limit')}</p>
  {:else}
    <form onsubmit={add} novalidate class="form">
      <label for="cs-name">{t('custom.name')}</label>
      <input id="cs-name" bind:value={name} maxlength="40" autocomplete="off" aria-invalid={errors.name ? 'true' : 'false'} aria-describedby="cs-name-err" />
      <p id="cs-name-err" class="err" role="alert">{msg('name')}</p>

      <label for="cs-lat">{t('custom.lat')}</label>
      <input id="cs-lat" bind:value={lat} inputmode="decimal" autocomplete="off" aria-invalid={errors.lat ? 'true' : 'false'} aria-describedby="cs-lat-err" />
      <p id="cs-lat-err" class="err" role="alert">{msg('lat')}</p>

      <label for="cs-lon">{t('custom.lon')}</label>
      <input id="cs-lon" bind:value={lon} inputmode="decimal" autocomplete="off" aria-invalid={errors.lon ? 'true' : 'false'} aria-describedby="cs-lon-err" />
      <p id="cs-lon-err" class="err" role="alert">{msg('lon')}</p>

      <label for="cs-panel">{t('custom.panel')}</label>
      <input id="cs-panel" bind:value={panel} inputmode="decimal" placeholder="2" autocomplete="off" aria-invalid={errors.panel ? 'true' : 'false'} aria-describedby="cs-panel-err" />
      <p id="cs-panel-err" class="err" role="alert">{msg('panel')}</p>

      <label for="cs-antenna">{t('custom.antenna')}</label>
      <input id="cs-antenna" bind:value={antenna} inputmode="decimal" placeholder="2" autocomplete="off" aria-invalid={errors.antenna ? 'true' : 'false'} aria-describedby="cs-antenna-err" />
      <p id="cs-antenna-err" class="err" role="alert">{msg('antenna')}</p>

      <div class="buttons">
        <button type="button" onclick={() => (picker = !picker)} aria-expanded={picker}>{t('custom.pick')}</button>
        <button type="submit" data-testid="custom-add">{t('custom.add')}</button>
      </div>
      {#if picker}
        <GlobePicker lat={Number.isFinite(Number(lat)) && lat !== '' ? Number(lat) : null} lon={Number.isFinite(Number(lon)) && lon !== '' ? Number(lon) : null} onpick={picked} />
      {/if}
    </form>
    <p class="basis">{t('custom.basis')}</p>
  {/if}
</section>

<style>
  .custom { display: grid; gap: 0.5rem; }
  .sites { list-style: none; margin: 0; padding: 0; display: grid; gap: 0.6rem; }
  .sites li { display: grid; gap: 0.15rem; }
  .coords { font-variant-numeric: tabular-nums; }
  .terrain { font-size: 0.9em; }
  .form { display: grid; gap: 0.2rem; max-width: 24rem; }
  .err { margin: 0; min-height: 1.1em; color: #b00020; font-size: 0.85em; }
  .buttons { display: flex; gap: 0.5rem; flex-wrap: wrap; margin-top: 0.3rem; }
  .basis, .count { margin: 0; font-size: 0.85em; }
</style>
