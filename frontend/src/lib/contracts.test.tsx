import { readFileSync } from 'node:fs';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { MemoryRouter } from 'react-router-dom';
import { EventCard } from '../components/EventCard';
import { AppProvider } from './context';
import { ampApi } from '../api/client';
import {
  formatDate,
  hasFilters,
  emptyFilters,
  priceLabel,
  safeLink,
  translatedText,
} from './format';
import {
  emptyRegistration,
  fromExtraction,
  registrationPayload,
  validateRegistration,
} from './registration';
import type { EventList, PosterExtraction } from '../types/api';

// Read existing specification examples for contract tests; no runtime fixture/seed data is added.
const markdown = readFileSync(new URL('../../../docs/API.md', import.meta.url), 'utf8');
const examples = Array.from(markdown.matchAll(/```json\n([\s\S]*?)\n```/g), (match) =>
  JSON.parse(match[1]),
);
const list = examples.find(
  (item) => Array.isArray(item.items) && typeof item.limit === 'number',
) as EventList;
const extraction = examples.find((item) => item.upload_id && item.extracted) as PosterExtraction;
const t = (ko: string) => ko;
afterEach(() => vi.unstubAllGlobals());

describe('README-aligned display contracts', () => {
  it('distinguishes free, unknown and advance prices', () => {
    expect(priceLabel(0, 'general', 'ko')).toBe('무료');
    expect(priceLabel(null, null, 'ko')).toBe('가격 확인 필요');
    expect(priceLabel(20000, 'advance', 'ko')).toBe('예매 20,000원');
    expect(hasFilters({ ...emptyFilters(), max_price_krw: 0 })).toBe(true);
  });
  it('formats UTC as Korea time and never invents a missing door time', () => {
    expect(formatDate('2026-11-07T10:00:00Z', 'en', true)).toBe('19:00');
    expect(formatDate(null, 'en')).toBe('Not confirmed');
  });
  it('only shows valid stored translations and identifies automatic English', () => {
    const generated = { status: 'generated' as const, generated_at: null };
    expect(translatedText('원문', 'English', generated, 'en')).toMatchObject({
      text: 'English',
      automatic: true,
      missing: false,
    });
    expect(translatedText('원문', 'English', generated, 'en', true).text).toBe('원문');
    expect(
      translatedText('원문', 'Stale', { status: 'failed', generated_at: null }, 'en'),
    ).toMatchObject({ text: '원문', automatic: false, missing: true });
  });
  it('renders a specified event without fabricated recommendation reasons', () => {
    vi.stubGlobal('localStorage', { getItem: () => 'en' });
    const html = renderToStaticMarkup(
      <MemoryRouter>
        <AppProvider>
          <EventCard event={list.items[0]} />
        </AppProvider>
      </MemoryRouter>,
    );
    expect(html).toContain('AI-translated');
    expect(html).toContain('View original');
    expect(html).toContain(list.items[0].title);
    expect(html).not.toContain('WHY THIS SHOW');
  });
  it('rejects unsafe external URLs', () => {
    expect(safeLink('javascript:alert(1)')).toBeUndefined();
    expect(safeLink('data:text/html,test')).toBeUndefined();
    expect(safeLink('https://example.com/show')).toBe('https://example.com/show');
  });
});

describe('original-only registration', () => {
  it('requires a venue and human original confirmation even after extraction', () => {
    const form = fromExtraction({
      ...extraction,
      venue_match: {
        status: 'ambiguous',
        venue_id: null,
        candidates: extraction.venue_match.candidates,
      },
    });
    const errors = validateRegistration(form, t);
    expect(errors.venue_id).toBeDefined();
    expect(errors.review_confirmed).toBeDefined();
  });
  it('rejects wrong time ordering and fractional/negative ticket prices', () => {
    const form = {
      ...emptyRegistration(),
      title: '원문',
      venue_id: '1',
      review_confirmed: true,
      starts_at_local: '2026-11-07T19:00',
      doors_open_at_local: '2026-11-07T20:00',
      ends_at_local: '2026-11-07T18:00',
      price_krw: '-1',
      door_price_krw: '1.5',
    };
    expect(Object.keys(validateRegistration(form, t))).toEqual(
      expect.arrayContaining([
        'doors_open_at_local',
        'ends_at_local',
        'price_krw',
        'door_price_krw',
      ]),
    );
  });
  it('computes the representative ticket price and excludes all server-owned fields', () => {
    const form = { ...fromExtraction(extraction), price_krw: '99999', review_confirmed: true };
    const payload = registrationPayload(form, extraction.upload_id);
    expect(payload.price_krw).toBe(
      Math.min(extraction.extracted.advance_price_krw!, extraction.extracted.door_price_krw!),
    );
    expect(payload.starts_at_local).toMatch(/:00$/);
    for (const forbidden of [
      'price_basis',
      'title_en',
      'description_en',
      'drink_policy_en',
      'admission_notes_en',
      'translation',
    ])
      expect(payload).not.toHaveProperty(forbidden);
  });
  it('preserves manual registration with unknown price and no poster', () => {
    const payload = registrationPayload(emptyRegistration(), null);
    expect(payload.price_krw).toBeNull();
    expect(payload.upload_id).toBeNull();
    expect(payload.lineup).toEqual([]);
  });
});

describe('frontend-only API boundary', () => {
  it('does not report a saved event or fabricate records before integration', async () => {
    const fetch = vi.fn();
    vi.stubGlobal('fetch', fetch);
    await expect(
      ampApi.listEvents({ upcoming: true, limit: 20, locale: 'ko' }),
    ).rejects.toMatchObject({ code: 'NOT_CONNECTED' });
    await expect(
      ampApi.createEvent(registrationPayload(emptyRegistration(), null)),
    ).rejects.toMatchObject({ code: 'NOT_CONNECTED' });
    expect(fetch).not.toHaveBeenCalled();
  });
});
