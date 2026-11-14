// SPDX-License-Identifier: Apache-2.0
import { describe, it, expect, afterEach } from 'vitest';
import { render, screen, cleanup } from '@testing-library/svelte';
import teamJson from '../../data/team.json';
import MemberCard from './MemberCard.svelte';
import Contacts from './Contacts.svelte';
import { LIMITS, initials, parseMember, parseTeam, safeLinkedin, safePhoto, type TeamMember } from './team';

afterEach(() => {
  cleanup();
  delete (globalThis as { __HB_TEAM__?: unknown }).__HB_TEAM__;
});

const GOOD: TeamMember = { id: 'ada', firstName: 'Ada', lastName: 'Rossi', role: 'Ruolo', bio: 'Breve.' };

describe('team.json spedito', () => {
  it('ha due membri validi con link e foto sicuri', () => {
    expect(Array.isArray(teamJson)).toBe(true);
    expect(teamJson).toHaveLength(2);
    expect(parseTeam(teamJson)).toEqual(teamJson); // nessun campo scartato o troncato
    const ids = new Set(teamJson.map((m) => m.id));
    expect(ids.size).toBe(2);
    for (const m of teamJson as Record<string, string>[]) {
      expect(Array.from(m.firstName!).length).toBeLessThanOrEqual(LIMITS.name);
      expect(Array.from(m.lastName!).length).toBeLessThanOrEqual(LIMITS.name);
      expect(Array.from(m.role!).length).toBeLessThanOrEqual(LIMITS.role);
      expect(Array.from(m.bio!).length).toBeLessThanOrEqual(LIMITS.bio);
      if (m.linkedin !== undefined) expect(safeLinkedin(m.linkedin)).not.toBeNull();
      if (m.photo !== undefined) expect(safePhoto(m.photo)).not.toBeNull();
    }
    expect(teamJson.map((m) => m.role)).toEqual([
      'Electronics, Telecommunications & Power',
      'Embedded Software Engineer, AI, Satellites, Autonomous Systems',
    ]);
  });
});

describe('safeLinkedin', () => {
  it.each([
    'https://www.linkedin.com/in/ada-rossi',
    'https://linkedin.com/in/ada-rossi/',
    'https://www.linkedin.com/company/acme',
    'https://it.linkedin.com/in/x'.replace('it.', 'www.'),
  ])('accetta %s', (u) => expect(safeLinkedin(u)).not.toBeNull());

  it.each([
    'javascript:alert(1)',
    'JaVaScRiPt:alert(1)',
    'data:text/html,<script>alert(1)</script>',
    'http://www.linkedin.com/in/ada',
    'https://linkedin.com.evil.com/in/ada',
    'https://evil.com/linkedin.com/in/ada',
    'https://evil.com/in/ada?u=linkedin.com',
    'https://www.linkedin.com.evil.com/in/ada',
    'https://notlinkedin.com/in/ada',
    'https://evil.com@www.linkedin.com/in/ada',
    'https://user:pw@www.linkedin.com/in/ada',
    'https://www.linkedin.com:8443/in/ada',
    'https://it.linkedin.com/in/ada',
    'https://www.linkedin.com/',
    'https://www.linkedin.com/feed/',
    'https://www.linkedin.com/in/',
    'https://www.linkedin.com/in/a/b',
    ' https://www.linkedin.com/in/ada',
    '//www.linkedin.com/in/ada',
    'www.linkedin.com/in/ada',
    '',
    42,
    null,
    undefined,
  ])('rifiuta %j', (u) => expect(safeLinkedin(u)).toBeNull());
});

describe('safePhoto', () => {
  it.each(['/team/membro-1.webp', '/team/ada.JPG', '/team/ada.jpeg', '/team/a_b.png'])('accetta %s', (p) =>
    expect(safePhoto(p)).toBe(p),
  );
  it.each([
    'https://evil.com/a.webp',
    '//evil.com/team/a.webp',
    'data:image/png;base64,AAAA',
    'javascript:alert(1)',
    '/other/a.webp',
    '/team/../secret.webp',
    '/team/sub/a.webp',
    '/team/a.svg',
    '/team/a.webp?x=1',
    '/team/a.html',
    'team/a.webp',
    '',
    7,
  ])('rifiuta %j', (p) => expect(safePhoto(p)).toBeNull());
});

describe('parseMember / parseTeam', () => {
  it('tronca testi lunghi e scarta link/foto non sicuri', () => {
    const m = parseMember({
      ...GOOD,
      firstName: 'N'.repeat(100),
      bio: 'b'.repeat(500),
      linkedin: 'https://linkedin.com.evil.com/in/x',
      photo: 'https://evil.com/a.png',
    })!;
    expect(Array.from(m.firstName).length).toBeLessThanOrEqual(LIMITS.name);
    expect(Array.from(m.bio).length).toBeLessThanOrEqual(LIMITS.bio);
    expect(m.bio.endsWith('…')).toBe(true);
    expect(m.linkedin).toBeUndefined();
    expect(m.photo).toBeUndefined();
  });
  it('scarta voci non valide, id duplicati e oltre il massimo', () => {
    expect(parseMember(null)).toBeNull();
    expect(parseMember({ ...GOOD, id: '<img>' })).toBeNull();
    expect(parseMember({ ...GOOD, id: 'Maiuscolo' })).toBeNull();
    expect(parseTeam('x')).toEqual([]);
    expect(parseTeam([GOOD, GOOD, 5])).toHaveLength(1);
    const many = Array.from({ length: 30 }, (_, i) => ({ ...GOOD, id: `m${i}` }));
    expect(parseTeam(many)).toHaveLength(LIMITS.members);
  });
  it('ignora campi tipo sbagliato', () => {
    const m = parseMember({ id: 'x', firstName: 5, lastName: {}, role: [], bio: null })!;
    expect(m).toMatchObject({ firstName: '', lastName: '', role: '', bio: '' });
  });
});

describe('initials', () => {
  it.each([
    ['Ada', 'Rossi', 'AR'],
    ['Ada', '', 'A'],
    ['', 'Rossi', 'R'],
    ['élodie', 'ñandú', 'ÉÑ'],
    ['Maria Chiara', 'De Luca', 'MD'],
    ['😀', 'Rossi', 'R'],
    ['😀 Ada', '🚀', 'A'],
    ['', '', '?'],
    ['  ', '123', '?'],
    ['李', '王', '李王'],
  ])('%j %j -> %s', (f, l, out) => expect(initials(f, l)).toBe(out));
});

describe('MemberCard', () => {
  it('segnaposto: avatar con iniziali, "Profilo da completare", nessun link né immagine', () => {
    render(MemberCard, { member: { id: 'membro-1', firstName: 'Nome', lastName: 'Cognome', role: 'Ruolo', bio: 'Aggiungi qui una breve presentazione' } });
    expect(screen.getByRole('heading', { level: 2, name: 'Nome Cognome' })).toBeTruthy();
    expect(screen.getByTestId('todo').textContent).toBe('Profilo da completare');
    expect(screen.getByTestId('avatar').textContent?.trim()).toBe('NC');
    expect(document.querySelector('img')).toBeNull();
    expect(document.querySelector('a')).toBeNull();
  });

  it('compilato: foto lazy con dimensioni e link LinkedIn sicuro', () => {
    render(MemberCard, {
      member: { ...GOOD, photo: '/team/ada.webp', linkedin: 'https://www.linkedin.com/in/ada-rossi' },
    });
    const img = document.querySelector('img')!;
    expect(img.getAttribute('src')).toBe('/team/ada.webp');
    expect(img.getAttribute('loading')).toBe('lazy');
    expect(img.getAttribute('decoding')).toBe('async');
    expect(img.getAttribute('width')).toBe('512');
    expect(img.getAttribute('height')).toBe('512');
    expect(screen.queryByTestId('todo')).toBeNull();
    const a = screen.getByRole('link', { name: 'Profilo LinkedIn di Ada Rossi (si apre in una nuova scheda)' });
    expect(a.getAttribute('href')).toBe('https://www.linkedin.com/in/ada-rossi');
    expect(a.getAttribute('target')).toBe('_blank');
    expect(a.getAttribute('rel')).toBe('noopener noreferrer');
    expect(a.textContent).toContain('LinkedIn');
  });

  it('a runtime rifiuta link e foto non sicuri anche se passati direttamente', () => {
    render(MemberCard, {
      member: { ...GOOD, photo: 'https://evil.com/x.png', linkedin: 'javascript:alert(1)' } as TeamMember,
    });
    expect(document.querySelector('a')).toBeNull();
    expect(document.querySelector('img')).toBeNull();
    expect(screen.getByTestId('avatar')).toBeTruthy();
  });

  it('stringhe XSS sono solo testo', () => {
    const x = '<img src=x onerror=alert(1)><script>alert(2)</script>';
    render(MemberCard, { member: { ...GOOD, firstName: x, lastName: '"><svg onload=alert(3)>', role: x, bio: x } });
    expect(document.querySelector('script')).toBeNull();
    expect(document.querySelector('svg[onload]')).toBeNull();
    expect(document.querySelector('img')).toBeNull();
    expect(document.querySelector('[onerror]')).toBeNull();
    expect(document.body.textContent).toContain('<img src=x onerror=alert(1)>');
  });
});

describe('Contacts', () => {
  it('mostra i due membri del modello senza la nota di personalizzazione rimossa', () => {
    render(Contacts);
    expect(screen.getByRole('heading', { level: 1, name: 'Il team' })).toBeTruthy();
    expect(screen.getAllByTestId('member')).toHaveLength(2);
    expect(screen.getByText('Electronics, Telecommunications & Power')).toBeTruthy();
    expect(screen.getByText('Embedded Software Engineer, AI, Satellites, Autonomous Systems')).toBeTruthy();
    expect(screen.queryByText('Pagina da personalizzare')).toBeNull();
  });

  it('con membri compilati (override di test) niente nota e link attivo', () => {
    (globalThis as { __HB_TEAM__?: unknown }).__HB_TEAM__ = [
      { ...GOOD, linkedin: 'https://www.linkedin.com/in/ada' },
      { ...GOOD, id: 'bo', firstName: 'Bo', linkedin: 'https://evil.com/linkedin.com' },
    ];
    render(Contacts);
    expect(screen.queryByText('Pagina da personalizzare')).toBeNull();
    expect(screen.getAllByRole('link', { name: /Profilo LinkedIn/ })).toHaveLength(1);
  });

  it('non mostra più la sezione di assistenza o il callout dei contatti da completare', () => {
    render(Contacts);
    expect(screen.queryByRole('heading', { name: 'Aiuto e assistenza' })).toBeNull();
    expect(screen.queryByText(/Non sono ancora pubblicati un indirizzo pubblico/)).toBeNull();
    expect(screen.queryByRole('link', { name: 'Guide e lezioni interattive' })).toBeNull();
    expect(screen.queryByRole('heading', { name: 'Informazioni sul team da completare' })).toBeNull();
    expect(document.querySelector('a[href^="mailto:"]')).toBeNull();
    expect(document.querySelector('a[href*="/issues"]')).toBeNull();
  });
});
