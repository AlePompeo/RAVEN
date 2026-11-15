// SPDX-License-Identifier: Apache-2.0
import { afterEach, expect, it } from 'vitest';
import { cleanup, render, screen } from '@testing-library/svelte';
import Demo from './Demo.svelte';

afterEach(cleanup);

it('provides a labelled video and an accessible link to the same local file', () => {
  const { container } = render(Demo);
  const video = container.querySelector('video');
  expect(video?.getAttribute('aria-label')).toBeTruthy();
  expect(video?.hasAttribute('controls')).toBe(true);
  expect(video?.querySelector('source')?.getAttribute('src')).toBe('/raven-demo.mp4');
  expect(screen.getByRole('link').getAttribute('href')).toBe('/raven-demo.mp4');
});
