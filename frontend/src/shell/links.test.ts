// SPDX-License-Identifier: Apache-2.0
import { describe, it, expect, beforeEach } from 'vitest';
import { linkTarget } from './links';

function click(html: string, init: MouseEventInit = {}): MouseEvent {
  document.body.innerHTML = html;
  const a = document.querySelector('a')!;
  const ev = new MouseEvent('click', { bubbles: true, cancelable: true, button: 0, ...init });
  Object.defineProperty(ev, 'target', { value: a });
  return ev;
}

beforeEach(() => history.replaceState({}, '', '/'));

describe('linkTarget', () => {
  it('intercetta un link interno', () => {
    expect(linkTarget(click('<a href="/telemetry?x=1">t</a>'), location)).toBe('/telemetry?x=1');
  });
  it('lascia al browser i link che differiscono solo per hash (skip link)', () => {
    expect(linkTarget(click('<a href="#main">salta</a>'), location)).toBeNull();
  });
  it('lascia al browser origini diverse, target, download, rel=external, modificatori', () => {
    for (const html of [
      '<a href="https://example.org/x">x</a>',
      '<a href="/x" target="_blank">x</a>',
      '<a href="/x" download>x</a>',
      '<a href="/x" rel="noopener external">x</a>',
    ]) {
      expect(linkTarget(click(html), location)).toBeNull();
    }
    expect(linkTarget(click('<a href="/x">x</a>', { ctrlKey: true }), location)).toBeNull();
  });
  it('intercetta target="_self"', () => {
    expect(linkTarget(click('<a href="/x" target="_self">x</a>'), location)).toBe('/x');
  });
});
