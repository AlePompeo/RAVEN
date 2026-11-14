// SPDX-License-Identifier: Apache-2.0
// Misure di prestazione condivise (non è un file di test): CPU rallentata via CDP, FCP/LCP/TBT stimato,
// ritmo dei requestAnimationFrame e dischi presentati dal renderer Canvas 2D.
import { expect, type Page } from '@playwright/test';
import { mkdirSync, writeFileSync } from 'node:fs';

export async function throttle(page: Page, rate: number): Promise<void> {
  const cdp = await page.context().newCDPSession(page);
  await cdp.send('Emulation.setCPUThrottlingRate', { rate });
}

export async function observe(page: Page): Promise<void> {
  await page.addInitScript(() => {
    const w = window as unknown as { __perf: { lcp: number; long: number[] } };
    w.__perf = { lcp: 0, long: [] };
    new PerformanceObserver((l) => {
      for (const e of l.getEntries()) w.__perf.lcp = Math.max(w.__perf.lcp, e.startTime);
    }).observe({ type: 'largest-contentful-paint', buffered: true });
    new PerformanceObserver((l) => {
      for (const e of l.getEntries()) w.__perf.long.push(e.duration);
    }).observe({ type: 'longtask', buffered: true });
  });
}

export async function vitals(page: Page): Promise<{ fcp: number | null; lcp: number; tbt: number; longTasks: number }> {
  return page.evaluate(() => {
    const w = window as unknown as { __perf: { lcp: number; long: number[] } };
    const fcp = performance.getEntriesByName('first-contentful-paint')[0];
    return {
      fcp: fcp ? Math.round(fcp.startTime) : null,
      lcp: Math.round(w.__perf.lcp),
      tbt: Math.round(w.__perf.long.reduce((a, d) => a + Math.max(0, d - 50), 0)),
      longTasks: w.__perf.long.length,
    };
  });
}

export function rafRate(page: Page, ms = 2000): Promise<number> {
  return page.evaluate(
    (dur) =>
      new Promise<number>((resolve) => {
        let n = 0;
        const start = performance.now();
        const tick = (t: number) => {
          n++;
          if (t - start < dur) requestAnimationFrame(tick);
          else resolve(Math.round((n * 1000) / (t - start)));
        };
        requestAnimationFrame(tick);
      }),
    ms,
  );
}

/** Dischi al secondo presentati dal renderer Canvas 2D durante la rotazione automatica. */
export async function diskFps(page: Page, ms = 3000): Promise<{ fps: number; shadeMs: number }> {
  const stage = page.locator('.stage');
  const a = Number(await stage.getAttribute('data-disks'));
  await page.waitForTimeout(ms);
  const b = Number(await stage.getAttribute('data-disks'));
  return { fps: Math.round(((b - a) * 10000) / ms) / 10, shadeMs: Number(await stage.getAttribute('data-shade-ms')) };
}

export function save(key: string, value: unknown): void {
  // un file per misura: i test girano in parallelo e un file condiviso (leggi-modifica-scrivi) si corrompe
  mkdirSync('test-results/ui/perf', { recursive: true });
  writeFileSync(`test-results/ui/perf/${key}.json`, JSON.stringify(value, null, 2));
  console.log(`perf ${key}:`, JSON.stringify(value));
}

export { expect };
