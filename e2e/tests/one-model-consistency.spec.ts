// SPDX-License-Identifier: Apache-2.0
// Un solo modello: stesso sito, stesso istante, stesso scenario => stessi numeri in Planner, Confronto, Lander/Viewer,
// Simula (sito reale) e pagina Modello, e ogni pagina dichiara la stessa versione. Backend reale (terreno LOLA, efemeridi).
//
// Differenze dichiarate (docs/domain/raven-changes.md): lo specchio TS dei cursori di Simula (modo manuale) non e'
// confrontato qui (ha la sua fixture di parita' a 0,01 dB); per i siti coperti da terreno lontano noto (D4, es. Haworth)
// scena e istantanea possono dare «bloccato» dove la vecchia regola dava «aperto»: il sito scelto qui (Malapert) non lo e'.
import { expect, test, type Page } from '@playwright/test';
import { openSimulationDetails } from './plannerHelpers';

const SITE = 'malapert-massif';
const T0 = '2027-04-07T00:00:00Z';
const WIN = { start_utc: T0, days: 1, step_min: 60 };
interface Ev {
  model_version: string;
  metrics: { useful_hours: number; unknown_hours: number };
  steps: { margin_db: (number | null)[]; rf_state: string[]; lit: (boolean | null)[]; dsn_visible: (boolean | null)[]; useful: (boolean | null)[]; time_unix: number[] };
}

async function reference(page: Page): Promise<Ev> {
  const r = await page.request.post('/api/raven/evaluate', { data: { site_id: SITE, ...WIN, include_steps: true } });
  expect(r.status(), await r.text()).toBe(200);
  return (await r.json()) as Ev;
}

test('Planner, Confronto, scena, istantanea, Simula e pagina Modello mostrano gli stessi numeri e la stessa versione', async ({ page }) => {
  test.setTimeout(240_000);
  const ref = await reference(page);
  const version = ref.model_version;
  const m0 = ref.steps.margin_db[0]!;
  const litHours = ref.steps.lit.filter((x) => x === true).length; // 1 h per passo
  const minMargin = Math.min(...ref.steps.margin_db.filter((x): x is number => x !== null));

  // --- Pagina Modello: la versione dichiarata e quella dell'API
  await page.goto('/model');
  await expect(page.getByTestId('model-version')).toContainText(version, { timeout: 20_000 });

  // --- Planner: la timeline e' la stessa valutazione (ore luce, ore utili, margine) e dichiara la versione
  await page.goto(`/mission-planner?site=${SITE}&t=${T0}&mode=avanzato&mp_step=period`);
  await page.locator('#journey-days').fill('1');
  await page.getByRole('navigation', { name: 'Passaggi della pianificazione' }).getByRole('button', { name: /Simulazione/ }).click();
  const plannerEval = page.waitForResponse((r) => r.url().endsWith('/api/raven/evaluate') && r.request().method() === 'POST');
  await page.getByRole('button', { name: 'Simula i due scenari' }).click();
  const pj = (await (await plannerEval).json()) as Ev;
  expect(pj.model_version).toBe(version);
  expect(pj.metrics.useful_hours).toBeCloseTo(ref.metrics.useful_hours, 9);
  expect(pj.steps.lit.filter((x) => x === true).length).toBe(litHours);
  expect(Math.min(...pj.steps.margin_db.filter((x): x is number => x !== null))).toBeCloseTo(minMargin, 9);
  await openSimulationDetails(page);
  await expect(page.locator('.model-stamp').first()).toContainText(version);

  // --- Confronto: componenti della classifica = metriche della valutazione
  await page.goto(`/compare?mode=avanzato&site=${SITE}&t=${T0}`);
  await expect(page.getByLabel('Durata (giorni)')).toBeVisible({ timeout: 20_000 });
  await page.getByRole('button', { name: 'Nessuno' }).click();
  await page.locator('form[aria-labelledby="g-setup-h"]').getByLabel('Malapert Massif').check();
  await page.getByLabel('Durata (giorni)').fill('1');
  await page.getByLabel('Passo (minuti)').fill('60');
  const cmp = page.waitForResponse((r) => r.url().endsWith('/api/raven/compare'));
  await page.getByRole('button', { name: 'Confronta con RAVEN' }).click();
  const cj = (await (await cmp).json()) as { model_version: string; ranking: { ranking: { site_id: string; components: { useful_hours: number; margin_min_db: number } }[] } };
  expect(cj.model_version).toBe(version);
  const row = cj.ranking.ranking.find((r) => r.site_id === SITE)!;
  expect(row.components.useful_hours).toBeCloseTo(ref.metrics.useful_hours, 9);
  expect(row.components.margin_min_db).toBeCloseTo(minMargin, 9);
  await expect(page.getByTestId('rank-stamp')).toContainText(version);
  await expect(page.locator(`tr[data-site="${SITE}"]`)).toContainText(ref.metrics.useful_hours.toFixed(1));

  // --- Scena (Lander) e istantanea (Viewer): margine, stato e stazione allo stesso istante
  const sc = await page.request.get(`/api/raven/scene?site=${SITE}&t=${encodeURIComponent(T0)}`);
  const sj = (await sc.json()) as { model_version: string; link: { margin_db: number; state: string; station: string } };
  expect(sj.model_version).toBe(version);
  expect(Math.abs(sj.link.margin_db - m0)).toBeLessThan(0.01);
  expect(sj.link.state).toBe(ref.steps.rf_state[0]);
  expect(sj.link.station).toBe('dsn34');
  const sn = await page.request.get(`/api/raven/snapshot?t=${encodeURIComponent(T0)}`);
  const snj = (await sn.json()) as { model_version: string; station: string; sites: { id: string; margin_db: number | null; state: string }[] };
  const snSite = snj.sites.find((s) => s.id === SITE)!;
  expect(snj.model_version).toBe(version);
  expect(snj.station).toBe('dsn34');
  expect(Math.abs((snSite.margin_db ?? Number.NaN) - m0)).toBeLessThan(0.01);
  expect(snSite.state).toBe(ref.steps.rf_state[0]);

  // --- Lander, Viewer e Simula (sito reale): le pagine dichiarano la stessa versione e usano le stesse risposte
  for (const path of [`/simula?site=${SITE}&t=${T0}&tab=scena`, `/siti?site=${SITE}&t=${T0}`, `/simula?site=${SITE}&t=${T0}&real=1`]) {
    await page.goto(path);
    await expect(page.getByTestId('model-stamp').first()).toContainText(version, { timeout: 30_000 });
  }
});
