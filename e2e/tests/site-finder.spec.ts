// SPDX-License-Identifier: Apache-2.0
import { expect, test } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';

// The automatic site search on the Sites page: the prompt is read by the real rules endpoint into an editable brief; the search job is
// stubbed (a real search takes about a minute) with a canned result of the real shape.
const raster = () => {
  const b = Buffer.alloc(384 * 384);
  for (let y = 100; y < 280; y++) for (let x = 100; x < 280; x++) b[y * 384 + x] = 60 + ((x + y) % 190);
  return b.toString('base64');
};
const RESULT = {
  proposals: [1, 2, 3].map((r) => ({
    rank: r, lat_deg: -80 - r / 3, lon_deg_east: 40 + r * 10, terrain: 'LOLA 240 m', meets_objectives: r < 3, on_front: r !== 2, name: r === 1 ? 'Luna 23' : null,
    core: { useful_fraction: 0.9 - r / 10, sun_fraction: 0.8 - r / 20, rf_fraction: 0.95, useful_hours: 200, min_soc: 0.6 },
    surrogate: { useful_fraction: { mean: 0.8 - r / 10, half_width: r === 3 ? null : 0.12 } },
    uncertainty: r === 3 ? null : { samples: 12, p_meet: 1 - r / 10, p_low: 0.6, p_high: 1, drivers: [{ parameter: 'array_area_m2', correlation: 0.8 }] },
  })),
  evaluated: 54, not_comparable: 6, rounds: 5, stop: 'budget', interval: '90 % conformal intervals from 54 core evaluations',
  suitability: { layer: 'suitability', size: 384, limit_lat_deg: -75, nodata: 0, encoding: 'uint8-linear', unit: '%', min: 0, max: 100, tag: 'I', kind: 'sequential', data_b64: raster(), source: 'RAVEN site search', note: 'Probability of meeting the stated objectives (tag I).' },
  limits: ['Candidates are evaluated on the 240 m polar terrain product.'], tag: 'I', region: 'polar', order: ['useful_fraction', 'rf_fraction', 'sun_fraction'],
  pareto: [1, 3].map((r) => ({ name: null, lat_deg: -80 - r / 3, lon_deg_east: 40 + r * 10, meets_objectives: true, core: { useful_fraction: 0.9 - r / 10, sun_fraction: 0.8 - r / 20, rf_fraction: 0.95 } })),
  uncertainty_note: 'Probability = share of parameter sets in which the site meets the objectives, with a 90 % Wilson interval.',
  parameter_spreads: [{ group: 'energy', name: 'array_area_m2', kind: 'rel', width: 0.3, why: 'solar array sized for an unspecified lander' }],
};

test('site finder: prompt to brief, search job, results with intervals and the suitability layer on the Moon', async ({ page }) => {
  let polls = 0;
  await page.route('**/api/raven/discover', (route) => route.fulfill({ status: 202, json: { job_id: 'j1', state: 'running' } }));
  await page.route('**/api/raven/discover/j1', (route) => {
    polls += 1;
    return route.fulfill({ json: polls < 2 ? { job_id: 'j1', state: 'running', evaluated: 20, budget: 100, elapsed_s: 8 } : { job_id: 'j1', state: 'done', evaluated: 54, budget: 100, elapsed_s: 46, result: RESULT } });
  });
  await page.route('**/api/raven/discover/j1/summary', (route) => route.fulfill({ json: { facts: { best: { label: 'Luna 23' } }, text: 'Luna 23 is the best site for this request: useful time 80 %.', text_source: 'template', model: null, model_note: 'no_model' } }));
  await page.route('**/api/raven/llm/status', (route) => route.fulfill({ json: { installed: false, running: false, model: null, free_mb: 8000, min_free_mb: 4096, enough_memory: true } }));
  await page.goto('/siti?lang=en');
  const box = page.getByTestId('site-finder');
  await expect(box).toBeVisible({ timeout: 30_000 });
  await page.locator('#finder-prompt').fill('14 days from April 2027, at least 60% sunlight, give me 3 sites near the south pole, with water');
  await box.getByRole('button', { name: 'Read my request' }).click();
  const parsed = page.getByTestId('finder-parsed');
  await expect(parsed).toContainText('Understood', { timeout: 10_000 });
  await expect(parsed).toContainText('water'); // not supported: said, not turned into a variable
  const brief = page.getByTestId('finder-brief');
  await expect(brief.getByLabel('Days')).toHaveValue('14');
  await expect(brief.getByLabel('Minimum Sun (%)')).toHaveValue('60');
  await expect(brief.getByLabel('How many sites')).toHaveValue('3');
  await expect(brief.getByLabel('Start date')).toHaveValue('2027-04-01');
  await brief.getByLabel('Minimum usable radio (%)').fill('70'); // the user edits what was understood
  await expect(page.getByTestId('finder-llm')).toContainText('not installed');
  await expect(page.getByTestId('finder-confirm')).toContainText('Nothing is searched until you confirm');
  await box.getByRole('button', { name: 'Confirm and find sites' }).click();
  await expect(page.getByTestId('finder-progress')).toBeVisible();
  const rows = page.getByTestId('finder-row');
  await expect(rows).toHaveCount(3, { timeout: 20_000 });
  await expect(rows.first()).toContainText('-80.33°');
  await expect(rows.nth(2)).toContainText('Unknown'); // an interval the surrogate cannot give is shown as unknown, not as zero
  await expect(page.getByTestId('finder-results')).toContainText('54 places evaluated by the core, 6 not comparable');
  await expect(rows.first()).toContainText('Luna 23');
  await expect(page.getByTestId('finder-account')).toContainText('Luna 23 is the best site', { timeout: 10_000 });
  await expect(page.getByTestId('finder-account')).toContainText('no model');
  await expect(page.getByTestId('finder-results')).toContainText('Useful → Radio → Sun');
  await page.getByLabel('Show only the Pareto front').check();
  await expect(rows).toHaveCount(2); // the front: two sites that nothing else beats
  await page.getByLabel('Show only the Pareto front').uncheck();
  await expect(rows).toHaveCount(3);
  await expect(page.getByTestId('finder-prob').first()).toContainText('90 % (60 % – 100 %)');
  await expect(page.getByTestId('finder-prob').nth(2)).toContainText('Unknown'); // no probability was computed for it: unknown, not zero
  await page.getByText('Assumed spreads of the illustrative parameters').click();
  await expect(page.getByTestId('finder-results')).toContainText('array_area_m2: ± 30 %');
  // the cloud of the search is a layer of the overlay panel, selected by itself
  const legend = page.getByTestId('overlay-legend');
  await expect(page.getByRole('radio', { name: 'Search result (suitability)' })).toBeChecked();
  await expect(legend).toContainText('Probability of meeting the stated objectives');
  expect((await new AxeBuilder({ page }).include('[data-testid="site-finder"]').analyze()).violations).toEqual([]);
  // a proposed site goes to the Mission Planner as a custom site, the way a site added by hand does
  await rows.first().getByRole('button', { name: 'Use in the planner' }).click();
  await expect(page).toHaveURL(/mission-planner/, { timeout: 15_000 });
  await expect(page).toHaveURL(/site=c-found-1/);
});

test('site finder: a brief without a window cannot be sent, and a busy server says so', async ({ page }) => {
  await page.route('**/api/raven/discover', (route) => route.fulfill({ status: 409, json: { error: 'busy' } }));
  await page.goto('/siti?lang=en');
  const box = page.getByTestId('site-finder');
  await expect(box.getByRole('button', { name: 'Find sites' })).toBeDisabled({ timeout: 30_000 });
  await page.getByTestId('finder-brief').getByLabel('Start date').fill('2027-04-07');
  await page.getByTestId('finder-brief').getByLabel('Days').fill('7');
  await box.getByRole('button', { name: 'Find sites' }).click();
  await expect(page.getByRole('alert').filter({ hasText: 'Another search is running' })).toBeVisible();
});

test('site finder: the model level is optional, asks consent for the online service and says what it filled', async ({ page }) => {
  let sent: Record<string, unknown> | null = null;
  await page.route('**/api/raven/brief/parse', async (route) => {
    sent = route.request().postDataJSON() as Record<string, unknown>;
    try {
      const real = await route.fetch();
      const body = await real.json();
      await route.fulfill({ json: { ...body, level: 'rules+model', model: 'ollama:granite4:1b', filled_by_model: ['priority'], model_available: true, brief: { ...body.brief, priority: 'radio' } } });
    } catch { /* the test ended while the request was in flight */ }
  });
  await page.goto('/siti?lang=en');
  const box = page.getByTestId('site-finder');
  await expect(box).toBeVisible({ timeout: 30_000 });
  await page.locator('#finder-prompt').fill('3 weeks from June 2027, at least 60% Sun, 4 sites, favouring communication');
  await box.getByRole('button', { name: 'Read my request' }).click();
  await expect(page.getByTestId('finder-parsed')).toContainText('Understood');
  expect(sent).toEqual({ text: expect.any(String) }); // by default nothing goes to a model
  await box.getByLabel('Use an assistant model for what the rules do not understand').check();
  await expect(box.getByLabel('Allow sending my text to the configured online service')).not.toBeChecked(); // consent is never implied
  await box.getByRole('button', { name: 'Read my request' }).click();
  await expect(page.getByTestId('finder-parsed')).toContainText('The model (ollama:granite4:1b) filled: priority', { timeout: 10_000 });
  expect(sent).toMatchObject({ use_model: true, allow_external: false });
  await expect(box.getByTestId('finder-brief').getByLabel('Priority')).toHaveValue('radio');
});

test('RAVEN SI: a request to find sites opens the search card, a question goes to the assistant', async ({ page }) => {
  await page.goto('/chat?lang=en');
  await expect(page.locator('#chat-input')).toBeVisible({ timeout: 30_000 });
  await page.locator('#chat-input').fill('find me 4 sites near the south pole, 14 days from April 2027, at least 60% sunlight');
  await page.getByRole('button', { name: /^Send/ }).click();
  const card = page.getByTestId('chat-finder');
  await expect(card).toBeVisible({ timeout: 15_000 });
  await expect(card.getByTestId('finder-parsed')).toContainText('Understood', { timeout: 15_000 }); // the message was read at once
  await expect(card.getByTestId('finder-brief').getByLabel('Days')).toHaveValue('14');
  await expect(card.getByTestId('finder-brief').getByLabel('How many sites')).toHaveValue('4');
  await expect(card.getByRole('button', { name: 'Find sites' })).toBeEnabled();
  await expect(page.locator('#chat-input')).toHaveValue(''); // the message left the composer without being sent to the assistant
  expect((await new AxeBuilder({ page }).include('[data-testid="chat-finder"]').analyze()).violations).toEqual([]);
});

test('mission planner: the Sites step finds sites by itself and assigns them to A and B in place', async ({ page }) => {
  await page.route('**/api/raven/discover', (route) => route.fulfill({ status: 202, json: { job_id: 'j2', state: 'running' } }));
  await page.route('**/api/raven/discover/j2', (route) => route.fulfill({ json: { job_id: 'j2', state: 'done', evaluated: 54, budget: 100, elapsed_s: 46, result: RESULT } }));
  await page.route('**/api/raven/discover/j2/summary', (route) => route.fulfill({ json: { facts: { best: { label: 'Luna 23' } }, text: 'Luna 23 is the best site for this request.', text_source: 'template', model: null, model_note: 'no_model' } }));
  await page.route('**/api/raven/llm/status', (route) => route.fulfill({ json: { installed: false, running: false, model: null, free_mb: 8000, min_free_mb: 4096, enough_memory: true } }));
  await page.goto('/mission-planner?lang=en&mp_step=sites');
  const panel = page.getByTestId('auto-sites');
  await expect(panel).toBeVisible({ timeout: 30_000 });
  await panel.getByText('Find sites automatically').click();
  const box = page.getByTestId('site-finder');
  await expect(box).toBeVisible();
  await expect(box.getByTestId('finder-brief').getByLabel('Days')).not.toHaveValue(''); // the period of the planner prefills the brief
  await box.getByRole('button', { name: 'Find sites' }).click(); // no chat, no typing: the prefilled brief is enough
  await expect(page.getByTestId('finder-row')).toHaveCount(3, { timeout: 20_000 });
  await box.getByTestId('finder-use-top').click();
  await expect(page).toHaveURL(/mission-planner/); // nothing navigated away
  await expect(page.locator('.site-card').filter({ has: page.getByText('Luna 23', { exact: true }) })).toHaveAttribute('aria-pressed', 'true'); // rank 1 became a custom site and is site A
  await expect(page.locator('.site-card', { hasText: 'Found 2' })).toBeVisible(); // rank 2 has no name: it became a custom site, assigned to B
});
