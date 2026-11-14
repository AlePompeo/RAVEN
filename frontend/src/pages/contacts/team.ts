// SPDX-License-Identifier: Apache-2.0
// Dati e validazione della pagina Contatti. Tutto ciò che arriva da team.json (o da un override di test) passa da
// parseTeam: testo troncato ai limiti, collegamenti e foto accettati solo se sicuri; il resto viene scartato.

export interface TeamMember {
  id: string;
  firstName: string;
  lastName: string;
  role: string;
  /** Presentazione breve, solo testo (max 280 caratteri). */
  bio: string;
  /** Percorso same-origin sotto /team/ (es. /team/membro-1.webp). */
  photo?: string;
  /** URL del profilo: https su linkedin.com / www.linkedin.com, percorso /in/... o /company/.... */
  linkedin?: string;
}

export const LIMITS = { name: 40, role: 80, bio: 280, members: 12 } as const;
export const PLACEHOLDER_NAME = { first: 'Nome', last: 'Cognome' } as const;

const ID_RE = /^[a-z0-9][a-z0-9-]{0,39}$/;
const PHOTO_RE = /^\/team\/[A-Za-z0-9][A-Za-z0-9._-]{0,80}\.(?:webp|jpe?g|png|avif)$/i;
const LI_HOSTS = new Set(['linkedin.com', 'www.linkedin.com']);
const LI_PATH_RE = /^\/(?:in|company)\/[^/\s]+\/?$/;

/** URL LinkedIn normalizzato se sicuro, altrimenti null (mai un link). */
export function safeLinkedin(value: unknown): string | null {
  if (typeof value !== 'string' || value.length > 300 || value !== value.trim()) return null;
  let u: URL;
  try {
    u = new URL(value);
  } catch {
    return null;
  }
  if (u.protocol !== 'https:' || !LI_HOSTS.has(u.hostname)) return null;
  if (u.username || u.password || u.port) return null;
  if (!LI_PATH_RE.test(u.pathname)) return null;
  return u.href;
}

/** Percorso foto se è un file immagine locale sotto /team/, altrimenti null (niente URL esterni né data:). */
export function safePhoto(value: unknown): string | null {
  if (typeof value !== 'string' || value.length > 120) return null;
  return PHOTO_RE.test(value) && !value.includes('..') ? value : null;
}

const clamp = (v: unknown, max: number): string => {
  if (typeof v !== 'string') return '';
  const t = v.replace(/[\u0000-\u001f\u007f]+/g, ' ').trim();
  const chars = Array.from(t);
  return chars.length > max ? chars.slice(0, max - 1).join('').trimEnd() + '…' : t;
};

/** Normalizza un elemento; null se non è un oggetto con id valido. */
export function parseMember(raw: unknown): TeamMember | null {
  if (typeof raw !== 'object' || raw === null) return null;
  const r = raw as Record<string, unknown>;
  if (typeof r.id !== 'string' || !ID_RE.test(r.id)) return null;
  const m: TeamMember = {
    id: r.id,
    firstName: clamp(r.firstName, LIMITS.name),
    lastName: clamp(r.lastName, LIMITS.name),
    role: clamp(r.role, LIMITS.role),
    bio: clamp(r.bio, LIMITS.bio),
  };
  const photo = safePhoto(r.photo);
  if (photo) m.photo = photo;
  const li = safeLinkedin(r.linkedin);
  if (li) m.linkedin = li;
  return m;
}

export function parseTeam(raw: unknown): TeamMember[] {
  if (!Array.isArray(raw)) return [];
  const seen = new Set<string>();
  const out: TeamMember[] = [];
  for (const item of raw.slice(0, LIMITS.members)) {
    const m = parseMember(item);
    if (m && !seen.has(m.id)) {
      seen.add(m.id);
      out.push(m);
    }
  }
  return out;
}

/** Nome completo da mostrare (mai vuoto). */
export function fullName(m: Pick<TeamMember, 'firstName' | 'lastName'>): string {
  return [m.firstName, m.lastName].filter(Boolean).join(' ') || 'Membro del team';
}

/** Un profilo è "da completare" finché ha ancora il nome segnaposto del modello. */
export function isPlaceholder(m: Pick<TeamMember, 'firstName' | 'lastName'>): boolean {
  return m.firstName === PLACEHOLDER_NAME.first && m.lastName === PLACEHOLDER_NAME.last;
}

/** Iniziali per l'avatar generato: prima lettera (Unicode) di nome e cognome; emoji e simboli ignorati; '?' se nessuna. */
export function initials(firstName: string, lastName: string): string {
  const first = (s: string) => {
    const w = s.split(/\s+/).find((x) => /\p{L}/u.test(x)) ?? '';
    const c = Array.from(w).find((ch) => /\p{L}/u.test(ch));
    return c ? c.toLocaleUpperCase('it-IT') : '';
  };
  return first(firstName) + first(lastName) || '?';
}
