// SPDX-License-Identifier: Apache-2.0
import { expect, test } from '@playwright/test';

const proxy = `http://127.0.0.1:${process.env.E2E_PROXY_PORT ?? 8001}`;
for (const { base, lang } of [{ base: '', lang: 'en' }, { base: `${proxy}/app`, lang: 'it' }]) {
  test(`demo video plays in ${lang} at ${base || '/'}`, async ({ page }) => {
    await page.goto(`${base}/demo?lang=${lang}`);
    const video = page.locator('video');
    await expect(video).toHaveAttribute('aria-label', lang === 'en' ? 'RAVEN demonstration video' : 'Video dimostrativo di RAVEN');
    await expect(video.locator('source')).toHaveAttribute('src', base ? '/app/raven-demo.mp4' : '/raven-demo.mp4');
    const link = page.getByRole('link', { name: lang === 'en' ? 'Open or download the demo video (MP4)' : 'Apri o scarica il video della demo (MP4)' });
    await expect(link).toHaveAttribute('href', base ? '/app/raven-demo.mp4' : '/raven-demo.mp4');
    await expect.poll(() => video.evaluate((v) => v.readyState)).toBeGreaterThanOrEqual(1);
    const metadata = await video.evaluate((v) => ({ duration: v.duration, width: v.videoWidth, height: v.videoHeight }));
    expect(metadata.duration).toBeGreaterThan(30);
    expect(metadata.duration).toBeLessThan(35);
    expect(metadata.width).toBeGreaterThan(0);
    expect(metadata.height).toBeGreaterThan(0);
    await video.evaluate((v) => v.play());
    await expect.poll(() => video.evaluate((v) => v.currentTime)).toBeGreaterThan(.1);
    await video.evaluate((v) => v.pause());
  });
}
