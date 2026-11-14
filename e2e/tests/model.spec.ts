// SPDX-License-Identifier: Apache-2.0
// Pagina "Modello e validazione" con il backend reale: stadi e stati uguali a /api/raven/model, filtro dei parametri
// per tag, stati 503, axe in entrambe le modalità, nessun overflow a 390.
import AxeBuilder from '@axe-core/playwright';
import { test, expect, type Page } from '@playwright/test';

const TAGS = ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa'];
const RANK: Record<string, number> = { unknown: 0, not_validated: 1, plausibility_only: 2, verified: 3 };

interface Entry { id: string; stage: string; status: string; phrase: string; not_validated?: string }
interface ModelBody { stages: { stage: string }[]; validation: { stages: Entry[] } }
interface Param { tag: string }

async function api(page: Page): Promise<{ model: ModelBody; params: Param[] }> {
  const model = (await (await page.request.get('/api/raven/model')).json()) as ModelBody;
  const params = ((await (await page.request.get('/api/raven/parameters')).json()) as { parameters: Param[] }).parameters;
  return { model, params };
}
const worst = (es: Entry[]) => (es.length ? es.reduce((a, e) => (RANK[e.status]! < RANK[a]! ? e.status : a), 'verified') : 'unknown');

async function open(page: Page, mode: 'avanzato' | 'learning', hash = ''): Promise<void> {
  await page.goto(`/model?mode=${mode}${hash}`);
  await expect(page.getByRole('heading', { level: 1, name: 'Modello e validazione' })).toBeVisible({ timeout: 20_000 });
  await expect(page.getByTestId('model-version')).toBeVisible({ timeout: 20_000 });
}
async function axe(page: Page, label: string): Promise<void> {
  const r = await new AxeBuilder({ page }).withTags(TAGS).analyze();
  expect(r.violations.map((v) => ({ id: v.id, nodes: v.nodes.map((n) => n.target.join(' ')) })), label).toEqual([]);
}

test.describe('/model con il backend reale', () => {
  test('stage becomes Verified only after every check closes and reopens on new unknown evidence', async ({ page }) => {
    const { model } = await api(page);
    let phase: 'open' | 'closed' | 'unknown' = 'open';
    // Hypothetical future reports exercise rendering, never promote production evidence.
    await page.route('**/api/raven/model', (route) => {
      const report = structuredClone(model);
      const es = report.validation.stages.filter((e) => e.stage === 's4');
      if (phase === 'closed') {
        for (const e of es) {
          e.status = 'verified';
          e.not_validated = '';
          e.phrase = 'Hypothetical completed check within its declared scope';
        }
      } else if (phase === 'unknown') {
        es[0]!.status = 'unknown';
      }
      return route.fulfill({ json: report });
    });
    await page.addInitScript(() => localStorage.setItem('hb.lang', 'en'));
    await page.goto('/model?mode=learning');
    const chip = page.locator('details[data-stage="s4"] > summary .chip');
    await expect(chip).toHaveAttribute('data-status', 'not_validated');
    await page.locator('details[data-stage="s4"] > summary').click();
    await expect(page.getByTestId('validation-gate-s4')).toBeVisible();
    phase = 'closed';
    await page.getByRole('button', { name: 'Refresh validation' }).click();
    await expect(chip).toHaveAttribute('data-status', 'verified');
    await expect(chip).toHaveText(/Verified/);
    await expect(page.getByTestId('stage-verified-s4')).toContainText('all recorded checks');
    await expect(page.getByTestId('validation-gate-s4')).toHaveCount(0);
    phase = 'unknown';
    await page.evaluate(() => window.dispatchEvent(new Event('focus')));
    await expect(chip).toHaveAttribute('data-status', 'unknown');
    await expect(page.getByTestId('stage-verified-s4')).toHaveCount(0);
    await expect(page.getByTestId('validation-gate-s4')).toBeVisible();
  });

  test('malformed status never produces a Verified card', async ({ page }) => {
    const { model } = await api(page);
    model.validation.stages[0]!.status = 'pending';
    await page.route('**/api/raven/model', (route) => route.fulfill({ json: model }));
    await page.goto('/model?mode=learning');
    await expect(page.getByRole('alert')).toContainText("La matrice di validazione non e' valida");
    await expect(page.locator('details[data-stage]')).toHaveCount(0);
  });

  test('English evidence progress does not promote physical stage validation', async ({ page }) => {
    await page.addInitScript(() => localStorage.setItem('hb.lang', 'en'));
    await page.goto('/model?mode=learning');
    await expect(page.getByTestId('model-version')).toContainText('raven-core-1.4');
    await page.locator('details[data-stage="s4"] > summary').click();
    await expect(page.getByTestId('evidence-progress-s4')).toContainText('1 of 2 checks verified');
    await expect(page.getByTestId('validation-gate-s4')).toContainText('Current hardware defaults remain illustrative');
    await expect(page.locator('details[data-stage="s4"] > summary .chip')).toHaveAttribute('data-status', 'not_validated');
  });

  test('stadi, stati e conteggi coincidono con l\'API; /validation è un alias', async ({ page }) => {
    const { model } = await api(page);
    await page.goto('/validation?mode=avanzato');
    await expect(page).toHaveURL(/\/model\?/);
    await expect(page.getByTestId('model-version')).toBeVisible({ timeout: 20_000 });
    for (const s of ['s0', 's1', 's2', 's3', 's4', 's5', 's6', 's7']) {
      const es = model.validation.stages.filter((e) => e.stage === s);
      await expect(page.locator(`details[data-stage="${s}"] > summary .chip`)).toHaveAttribute('data-status', worst(es));
    }
    for (const st of ['verified', 'plausibility_only', 'not_validated', 'unknown']) {
      const n = model.validation.stages.filter((e) => e.status === st).length;
      await expect(page.getByTestId(`count-${st}`)).toHaveText(String(n));
    }
    for (const s of ['s2', 's3', 's4', 's5']) {
      const es = model.validation.stages.filter((e) => e.stage === s);
      await page.locator(`details[data-stage="${s}"] > summary`).click();
      await expect(page.getByTestId(`evidence-progress-${s}`)).toContainText(
        `${es.filter((e) => e.status === 'verified').length} controlli verificati su ${es.length}`,
      );
      await expect(page.getByTestId(`validation-gate-${s}`)).toContainText('validazione fisica');
      await page.locator(`details[data-stage="${s}"] > summary`).click();
    }
    // frase ammessa e prove nello stadio aperto
    await page.locator('details[data-stage="s5"] > summary').click();
    const e5 = model.validation.stages.find((e) => e.stage === 's5')!;
    await expect(page.locator(`[data-entry="${e5.id}"]`)).toContainText(e5.phrase);
    await expect(page.locator(`[data-entry="${e5.id}"] code`).first()).toBeVisible();
  });

  test('le formule vengono dal registro del report (stesso testo della parte 3)', async ({ page }) => {
    await page.goto('/model?mode=avanzato');
    const section = page.getByTestId('formulas-section');
    await expect(section).toBeVisible({ timeout: 20_000 });
    await expect(section.getByRole('heading', { name: 'Le formule', level: 2 })).toBeVisible();
    await expect(section.locator('li[data-formula]')).toHaveCount(11);
    await section.locator('li[data-formula="margin"] summary').click();
    await expect(section.locator('li[data-formula="margin"]')).toContainText('link_margin_db = tx_power + tx_gain');
    await expect(section.locator('li[data-formula="margin"]')).toContainText('free_space_loss_db');
    await expect(section.locator('li[data-formula="margin"] summary .chip')).toHaveCount(1);
  });

  test('Learning: riassunto in parole semplici, nessuna tabella dei parametri né prove', async ({ page }) => {
    await open(page, 'learning');
    await page.locator('details[data-stage="s2"] > summary').click();
    await expect(page.locator('details[data-stage="s2"]')).toContainText('In parole semplici');
    await expect(page.getByTestId('params-section')).toHaveCount(0);
    await expect(page.locator('details[data-stage="s2"] dl')).toHaveCount(0);
    await expect(page.getByRole('button', { name: /Scarica la matrice/ })).toHaveCount(0);
  });

  test('Avanzato: filtro per tag, per stadio e per testo; esportazione JSON', async ({ page }) => {
    const { params } = await api(page);
    await open(page, 'avanzato');
    const total = params.length;
    await expect(page.getByTestId('params-count')).toContainText(`${total} parametri su ${total}`);
    await page.getByRole('combobox', { name: 'Tag' }).selectOption('I');
    const nI = params.filter((p) => p.tag === 'I').length;
    await expect(page.getByTestId('params-count')).toContainText(`${nI} parametri su ${total}`);
    await expect(page.locator('tbody tr[data-tag="V"]')).toHaveCount(0);
    await expect(page.locator('tbody tr[data-tag="I"]')).toHaveCount(nI);
    await page.getByRole('combobox', { name: 'Stadio' }).selectOption('s1');
    const none = await page.locator('tbody tr[data-tag]').count();
    expect(none).toBeLessThanOrEqual(nI);
    await page.getByRole('combobox', { name: 'Stadio' }).selectOption('');
    await page.getByRole('combobox', { name: 'Tag' }).selectOption('');
    await page.getByLabel('Cerca nome o fonte').fill('zzzz-nessuno');
    await expect(page.getByText('Nessun parametro corrisponde ai filtri.')).toBeVisible();
    const dl = page.waitForEvent('download');
    await page.getByRole('button', { name: /Scarica la matrice/ }).click();
  });


  test('503 onesto: nessuna matrice inventata', async ({ page }) => {
    await page.route('**/api/raven/model', (route) => route.fulfill({ status: 503, json: { detail: 'down' } }));
    await page.goto('/model?mode=avanzato');
    await expect(page.getByRole('alert')).toContainText('503');
    await expect(page.locator('details[data-stage]')).toHaveCount(0);
  });

  for (const mode of ['learning', 'avanzato'] as const) {
    test(`axe pulito (${mode}, tutto aperto)`, async ({ page }) => {
      await open(page, mode);
      for (const s of await page.locator('details[data-stage] > summary').all()) await s.click();
      await axe(page, mode);
    });
    test(`nessun overflow orizzontale a 390 (${mode})`, async ({ page }) => {
      await page.setViewportSize({ width: 390, height: 844 });
      await open(page, mode);
      for (const s of await page.locator('details[data-stage] > summary').all()) await s.click();
      const w = await page.evaluate(() => [document.documentElement.scrollWidth, window.innerWidth]);
      expect(w[0]).toBeLessThanOrEqual(w[1]!);
    });
  }

  test('schermate', async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 1000 });
    await page.emulateMedia({ colorScheme: 'dark' });
    await open(page, 'avanzato');
    await page.locator('details[data-stage="s5"] > summary').click();
    await page.screenshot({ path: 'test-results/model-1440-dark.png', fullPage: false });
    await page.setViewportSize({ width: 390, height: 844 });
    await page.emulateMedia({ colorScheme: 'light' });
    await open(page, 'learning');
    await page.screenshot({ path: 'test-results/model-390-light.png', fullPage: false });
  });
});
