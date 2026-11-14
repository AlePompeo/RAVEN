// SPDX-License-Identifier: Apache-2.0
import type { DocumentPages } from './reportPlanning';

export interface SimulatedCertificate {
  status: 'simulation_only_not_broadcast'; network: null; broadcast: false;
  issuer: 'RAVEN'; hash_algorithm: 'SHA-256'; payload_format: 'raven-json-sorted-keys-v1';
  payload_sha256: string; simulated_transaction_id: string; cryptographic_signature: null;
}

export async function simulatedCertificate(payload: unknown): Promise<SimulatedCertificate> {
  const canonical = JSON.stringify(payload, (_key, value: unknown) =>
    value && typeof value === 'object' && !Array.isArray(value)
      ? Object.fromEntries(Object.entries(value).sort(([a], [b]) => a < b ? -1 : a > b ? 1 : 0)) : value);
  const digest = async (value: string) => Array.from(
    new Uint8Array(await crypto.subtle.digest('SHA-256', new TextEncoder().encode(value))),
    (byte) => byte.toString(16).padStart(2, '0')).join('');
  const hash = await digest(canonical);
  return {
    status: 'simulation_only_not_broadcast', network: null, broadcast: false, issuer: 'RAVEN',
    hash_algorithm: 'SHA-256', payload_format: 'raven-json-sorted-keys-v1', payload_sha256: hash,
    simulated_transaction_id: `DEMO-${await digest(`RAVEN-DEMO-TRANSACTION\n${hash}`)}`,
    cryptographic_signature: null,
  };
}

function layoutPages(node: HTMLElement, compact: boolean): number {
  const clone = node.cloneNode(true) as HTMLElement;
  clone.classList.toggle('compact-report', compact);
  clone.classList.add('report-measure');
  clone.setAttribute('aria-hidden', 'true');
  clone.inert = true;
  clone.style.cssText = 'position:fixed;left:-10000px;top:0;width:190mm;max-width:none;visibility:hidden;pointer-events:none;margin:0;padding:0;border:0';
  clone.querySelectorAll('[id]').forEach((el) => el.removeAttribute('id'));
  document.body.append(clone);
  try {
    const height = 272 * 96 / 25.4;
    const origin = clone.getBoundingClientRect().top;
    const elements = Array.from(clone.querySelectorAll<HTMLElement>('.pending > div, .candidate, .chart, tr, .signature, .document-environment'));
    const bounds = new Map(elements.map((el) => [el, el.getBoundingClientRect()]));
    const boxes = elements.filter((el) => {
      for (let parent = el.parentElement; parent && parent !== clone; parent = parent.parentElement) {
        const outer = bounds.get(parent);
        if (outer && outer.height <= height) return false;
      }
      return true;
    }).map((el) => bounds.get(el)!).sort((a, b) => a.top - b.top);
    let gaps = 0;
    for (const box of boxes) {
      const top = box.top - origin + gaps;
      const remainder = height - top % height;
      if (box.height <= height && box.height > remainder) gaps += remainder;
    }
    return Math.max(1, Math.ceil((clone.getBoundingClientRect().height + gaps) / height));
  } finally { clone.remove(); }
}

export function reportLayout(node: HTMLElement, options: { ready: boolean; onpages: (pages: DocumentPages) => void }) {
  let timer: ReturnType<typeof setTimeout>;
  let alive = true;
  const printMedia = window.matchMedia('print');
  const schedule = () => {
    clearTimeout(timer);
    if (printMedia.matches) return;
    timer = setTimeout(() => {
      if (alive && !printMedia.matches && options.ready) options.onpages({ compact: layoutPages(node, true), reference: layoutPages(node, false) });
    }, 200);
  };
  printMedia.addEventListener('change', schedule);
  const observer = new ResizeObserver(schedule);
  observer.observe(node);
  void document.fonts.ready.then(() => { if (alive) schedule(); });
  schedule();
  return {
    update(next: typeof options) { options = next; schedule(); },
    destroy() { alive = false; clearTimeout(timer); observer.disconnect(); printMedia.removeEventListener('change', schedule); },
  };
}
