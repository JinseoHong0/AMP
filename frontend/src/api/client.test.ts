import { afterEach, describe, expect, it, vi } from 'vitest';
import { API_BASE_URL, ApiError, ampApi } from './client';

afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

function jsonResponse(status: number, body: unknown) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

describe('HTTP layer (shared by every adapter)', () => {
  it('uses VITE_API_BASE_URL or the documented default origin', () => {
    expect(API_BASE_URL).toBe(
      (import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000').replace(/\/+$/, ''),
    );
  });

  it('maps the common error body to ApiError with code, message and HTTP status', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () =>
        jsonResponse(503, { error: { code: 'AI_UNAVAILABLE', message: 'AI 실패', details: {} } }),
      ),
    );
    const error = await ampApi.health().catch((e) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({ code: 'AI_UNAVAILABLE', message: 'AI 실패', status: 503 });
  });

  it('keeps 404 semantics even when the body is not the common shape', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => new Response('not json', { status: 404 })),
    );
    await expect(ampApi.health()).rejects.toMatchObject({ code: 'HTTP_ERROR', status: 404 });
  });

  it('reports network failures and timeouts as retryable errors (status 0)', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => Promise.reject(new TypeError('Failed to fetch'))),
    );
    await expect(ampApi.health()).rejects.toMatchObject({ code: 'NETWORK_ERROR', status: 0 });

    vi.useFakeTimers();
    vi.stubGlobal(
      'fetch',
      vi.fn(
        (_url: string, init: RequestInit) =>
          new Promise((_resolve, reject) =>
            init.signal?.addEventListener('abort', () =>
              reject(new DOMException('aborted', 'AbortError')),
            ),
          ),
      ),
    );
    const pending = ampApi.health().catch((e) => e);
    await vi.advanceTimersByTimeAsync(15_000);
    expect(await pending).toMatchObject({ code: 'TIMEOUT', status: 0 });
  });
});

describe('health adapter', () => {
  it('GETs /api/health and returns the server body', async () => {
    const fetch = vi.fn(async () =>
      jsonResponse(200, { status: 'ok', service: 'amp-api', version: '1.1.0' }),
    );
    vi.stubGlobal('fetch', fetch);
    await expect(ampApi.health()).resolves.toMatchObject({ status: 'ok' });
    expect(fetch).toHaveBeenCalledTimes(1);
    const [url, init] = fetch.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe(`${API_BASE_URL}/api/health`);
    expect(init.method ?? 'GET').toBe('GET');
    expect(init.headers).toMatchObject({ Accept: 'application/json' });
  });
});

describe('listEvents adapter', () => {
  const page = { items: [], total: 0, limit: 20 };

  it('GETs /api/events with only the defined filters (0 kept, undefined dropped)', async () => {
    const fetch = vi.fn(async () => jsonResponse(200, page));
    vi.stubGlobal('fetch', fetch);
    await expect(
      ampApi.listEvents({
        upcoming: true,
        limit: 20,
        locale: 'ko',
        date: '2026-11-07',
        area: 'hongdae',
        max_price_krw: 0,
        seating_type: undefined,
      }),
    ).resolves.toEqual(page);
    const url = new URL((fetch.mock.calls[0] as unknown as [string])[0]);
    expect(url.origin + url.pathname).toBe(`${API_BASE_URL}/api/events`);
    expect(Object.fromEntries(url.searchParams)).toEqual({
      upcoming: 'true',
      limit: '20',
      locale: 'ko',
      date: '2026-11-07',
      area: 'hongdae',
      max_price_krw: '0',
    });
  });

  it('sends no optional filters when none are chosen', async () => {
    const fetch = vi.fn(async () => jsonResponse(200, page));
    vi.stubGlobal('fetch', fetch);
    await ampApi.listEvents({ upcoming: true, limit: 50, locale: 'en' });
    expect((fetch.mock.calls[0] as unknown as [string])[0]).toBe(
      `${API_BASE_URL}/api/events?upcoming=true&limit=50&locale=en`,
    );
  });

  it('surfaces server validation errors as ApiError 422', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () =>
        jsonResponse(422, {
          error: {
            code: 'VALIDATION_ERROR',
            message: '요청 값을 확인해 주세요.',
            details: { field: 'limit' },
          },
        }),
      ),
    );
    await expect(
      ampApi.listEvents({ upcoming: true, limit: 20, locale: 'ko' }),
    ).rejects.toMatchObject({
      code: 'VALIDATION_ERROR',
      status: 422,
    });
  });
});

describe('getEvent adapter', () => {
  it('GETs /api/events/{id} without extra parameters', async () => {
    const detail = { id: 7, title: '공연' };
    const fetch = vi.fn(async () => jsonResponse(200, detail));
    vi.stubGlobal('fetch', fetch);
    await expect(ampApi.getEvent(7, 'en')).resolves.toEqual(detail);
    expect((fetch.mock.calls[0] as unknown as [string])[0]).toBe(`${API_BASE_URL}/api/events/7`);
  });

  it('keeps 404 so the page shows "show not found"', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () =>
        jsonResponse(404, {
          error: { code: 'EVENT_NOT_FOUND', message: '공연을 찾을 수 없습니다.', details: {} },
        }),
      ),
    );
    await expect(ampApi.getEvent(999, 'ko')).rejects.toMatchObject({
      code: 'EVENT_NOT_FOUND',
      status: 404,
    });
  });
});

describe('getVenue adapter', () => {
  it('GETs /api/venues/{id}', async () => {
    const venue = { id: 3, name: '공연장', area: 'hongdae' };
    const fetch = vi.fn(async () => jsonResponse(200, venue));
    vi.stubGlobal('fetch', fetch);
    await expect(ampApi.getVenue(3, 'en')).resolves.toEqual(venue);
    expect((fetch.mock.calls[0] as unknown as [string])[0]).toBe(`${API_BASE_URL}/api/venues/3`);
  });

  it('keeps VENUE_NOT_FOUND as 404', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () =>
        jsonResponse(404, {
          error: { code: 'VENUE_NOT_FOUND', message: '공연장을 찾을 수 없습니다.', details: {} },
        }),
      ),
    );
    await expect(ampApi.getVenue(1, 'ko')).rejects.toMatchObject({
      code: 'VENUE_NOT_FOUND',
      status: 404,
    });
  });
});

describe('listVenues adapter', () => {
  it('GETs /api/venues with the trimmed search text and limit=50', async () => {
    const fetch = vi.fn(async () => jsonResponse(200, { items: [], total: 0 }));
    vi.stubGlobal('fetch', fetch);
    await ampApi.listVenues('  라이브 클럽 ');
    const url = new URL((fetch.mock.calls[0] as unknown as [string])[0]);
    expect(url.origin + url.pathname).toBe(`${API_BASE_URL}/api/venues`);
    expect(Object.fromEntries(url.searchParams)).toEqual({ q: '라이브 클럽', limit: '50' });
  });

  it('omits q for an empty or blank search', async () => {
    const fetch = vi.fn(async () => jsonResponse(200, { items: [], total: 0 }));
    vi.stubGlobal('fetch', fetch);
    await ampApi.listVenues('   ');
    expect((fetch.mock.calls[0] as unknown as [string])[0]).toBe(
      `${API_BASE_URL}/api/venues?limit=50`,
    );
  });
});

describe('recommend adapter', () => {
  const filters = {
    date: null,
    area: 'hongdae' as const,
    max_price_krw: 0,
    mood_tags: [],
    solo_friendly: null,
    seating_preference: null,
    seating_requirement: null,
  };

  it('POSTs the raw request as JSON to /api/recommend and returns the server order untouched', async () => {
    const body = { status: 'ok', items: [{ event: { id: 2 } }, { event: { id: 1 } }] };
    const fetch = vi.fn(async () => jsonResponse(200, body));
    vi.stubGlobal('fetch', fetch);
    const request = { query: ' 원문 그대로 ', filters, locale: 'ko' as const };
    await expect(ampApi.recommend(request)).resolves.toEqual(body);
    const [url, init] = fetch.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe(`${API_BASE_URL}/api/recommend`);
    expect(init.method).toBe('POST');
    expect(init.headers).toMatchObject({
      'Content-Type': 'application/json',
      Accept: 'application/json',
    });
    expect(JSON.parse(init.body as string)).toEqual(request);
  });

  it('keeps AI_UNAVAILABLE (503) so the page shows the AI failure state', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () =>
        jsonResponse(503, {
          error: { code: 'AI_UNAVAILABLE', message: 'AI 추천을 사용할 수 없습니다.', details: {} },
        }),
      ),
    );
    await expect(
      ampApi.recommend({ query: '잔잔한 공연', filters, locale: 'ko' }),
    ).rejects.toMatchObject({
      code: 'AI_UNAVAILABLE',
      status: 503,
    });
  });

  it('waits up to 35s (AI budget) instead of the 15s default', async () => {
    vi.useFakeTimers();
    vi.stubGlobal(
      'fetch',
      vi.fn(
        (_url: string, init: RequestInit) =>
          new Promise((_resolve, reject) =>
            init.signal?.addEventListener('abort', () =>
              reject(new DOMException('aborted', 'AbortError')),
            ),
          ),
      ),
    );
    let settled = false;
    const pending = ampApi
      .recommend({ query: 'x', filters, locale: 'ko' })
      .catch((e) => e)
      .finally(() => (settled = true));
    await vi.advanceTimersByTimeAsync(20_000);
    expect(settled).toBe(false);
    await vi.advanceTimersByTimeAsync(15_000);
    expect(await pending).toMatchObject({ code: 'TIMEOUT' });
  });
});

describe('createEvent adapter', () => {
  const payload = {
    upload_id: null,
    venue_id: 1,
    title: '원문 공연',
    starts_at_local: '2026-11-20T19:30:00',
    ends_at_local: null,
    doors_open_at_local: null,
    price_krw: 20000,
    advance_price_krw: null,
    door_price_krw: null,
    booking_url: null,
    lineup: [],
    genre: null,
    mood_tags: [],
    solo_friendly: null,
    seating_type: null,
    seat_assignment: null,
    drink_policy: null,
    description_ko: null,
    admission_notes_ko: null,
    source_url: null,
    data_origin: 'demo' as const,
    review_confirmed: true as const,
  };

  it('POSTs the original-only payload as JSON and returns the 201 body', async () => {
    const created = {
      id: 9,
      status: 'published',
      poster_url: null,
      translation: { status: 'not_requested', generated_at: null },
      warnings: ['공연은 등록되었으나 영어 번역은 아직 준비되지 않았습니다.'],
      message: '공연이 등록되었습니다.',
    };
    const fetch = vi.fn(async () => jsonResponse(201, created));
    vi.stubGlobal('fetch', fetch);
    await expect(ampApi.createEvent(payload)).resolves.toEqual(created);
    const [url, init] = fetch.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe(`${API_BASE_URL}/api/events`);
    expect(init.method).toBe('POST');
    expect(init.headers).toMatchObject({ 'Content-Type': 'application/json' });
    expect(JSON.parse(init.body as string)).toEqual(payload);
  });

  it('surfaces VENUE_REQUIRED / FORBIDDEN without reporting a saved event', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () =>
        jsonResponse(422, {
          error: { code: 'VENUE_REQUIRED', message: '기존 공연장을 선택해 주세요.', details: {} },
        }),
      ),
    );
    await expect(ampApi.createEvent(payload)).rejects.toMatchObject({
      code: 'VENUE_REQUIRED',
      status: 422,
    });
    vi.stubGlobal(
      'fetch',
      vi.fn(async () =>
        jsonResponse(403, { error: { code: 'FORBIDDEN', message: '로컬 전용', details: {} } }),
      ),
    );
    await expect(ampApi.createEvent(payload)).rejects.toMatchObject({
      code: 'FORBIDDEN',
      status: 403,
    });
  });
});

// Live check against a running backend: AMP_LIVE_API=1 npx vitest run src/api/client.test.ts
describe.skipIf(!process.env.AMP_LIVE_API)('live backend', () => {
  it('health reaches the real FastAPI server', async () => {
    await expect(ampApi.health()).resolves.toEqual({
      status: 'ok',
      service: 'amp-api',
      version: '1.1.0',
    });
  });

  it('listEvents returns real upcoming shows and applies filters on the server', async () => {
    const all = await ampApi.listEvents({ upcoming: true, limit: 50, locale: 'ko' });
    expect(all.total).toBeGreaterThan(0);
    expect(all.limit).toBe(50);
    expect(all.items.length).toBe(Math.min(50, all.total));
    for (const item of all.items) {
      expect(item).toMatchObject({ id: expect.any(Number), title: expect.any(String) });
      expect(['sinchon', 'hongdae']).toContain(item.venue.area);
      expect(Date.parse(item.starts_at)).not.toBeNaN();
    }
    const starts = all.items.map((item) => item.starts_at);
    expect([...starts].sort()).toEqual(starts); // 시간순

    const sinchon = await ampApi.listEvents({
      upcoming: true,
      limit: 50,
      locale: 'ko',
      area: 'sinchon',
    });
    expect(sinchon.items.every((item) => item.venue.area === 'sinchon')).toBe(true);
    expect(sinchon.total).toBeLessThan(all.total);

    const free = await ampApi.listEvents({
      upcoming: true,
      limit: 50,
      locale: 'ko',
      max_price_krw: 0,
    });
    expect(free.items.every((item) => item.price_krw === 0)).toBe(true);

    await expect(
      ampApi.listEvents({ upcoming: true, limit: 999, locale: 'ko' }),
    ).rejects.toMatchObject({ code: 'VALIDATION_ERROR', status: 422 });
  });

  it('getEvent returns the full visit-ready detail of a listed show, and 404 for unknown ids', async () => {
    const list = await ampApi.listEvents({ upcoming: true, limit: 20, locale: 'ko' });
    const summary = list.items[0];
    const detail = await ampApi.getEvent(summary.id, 'ko');
    expect(detail).toMatchObject({
      id: summary.id,
      title: summary.title,
      venue_id: summary.venue.id,
      starts_at: summary.starts_at,
      price_krw: summary.price_krw,
      price_basis: summary.price_basis,
      status: 'published',
    });
    for (const key of [
      'doors_open_at',
      'ends_at',
      'lineup',
      'seat_assignment',
      'admission_notes_ko',
      'admission_notes_en',
      'booking_url',
      'source_url',
      'verified_at',
      'data_origin',
    ])
      expect(detail).toHaveProperty(key);
    expect(Array.isArray(detail.lineup)).toBe(true);
    await expect(ampApi.getEvent(99_999_999, 'ko')).rejects.toMatchObject({
      code: 'EVENT_NOT_FOUND',
      status: 404,
    });
  });

  it('getVenue returns the venue guide of a listed show, and 404 for unknown ids', async () => {
    const list = await ampApi.listEvents({ upcoming: true, limit: 20, locale: 'ko' });
    const event = list.items[0];
    const venue = await ampApi.getVenue(event.venue.id, 'ko');
    expect(venue).toMatchObject({
      id: event.venue.id,
      name: event.venue.name,
      area: event.venue.area,
    });
    for (const key of [
      'address',
      'floor',
      'entrance_image_url',
      'default_seating_type',
      'default_drink_policy',
      'entrance_hint_ko',
      'entrance_hint_en',
      'description_ko',
      'description_en',
      'source_url',
      'verified_at',
      'data_origin',
    ])
      expect(venue).toHaveProperty(key);
    await expect(ampApi.getVenue(99_999_999, 'ko')).rejects.toMatchObject({
      code: 'VENUE_NOT_FOUND',
      status: 404,
    });
  });

  it('listVenues lists every existing venue and searches by normalized name', async () => {
    const all = await ampApi.listVenues('');
    expect(all.total).toBeGreaterThan(0);
    expect(all.items.length).toBe(Math.min(50, all.total));
    for (const venue of all.items) expect(['sinchon', 'hongdae']).toContain(venue.area);
    const found = await ampApi.listVenues('클럽 에반스'); // 공백 차이 무시
    expect(found.items.map((venue) => venue.name)).toEqual(['클럽에반스']);
    const none = await ampApi.listVenues('존재하지않는공연장');
    expect(none).toEqual({ items: [], total: 0 });
    expect((await ampApi.listVenues('')).total).toBe(all.total); // 검색해도 새 공연장이 생기지 않음
  });

  it('recommend (filters only) returns the documented response shape without scores', async () => {
    const result = await ampApi.recommend({
      query: '',
      filters: {
        date: null,
        area: 'hongdae',
        max_price_krw: 40000,
        mood_tags: [],
        solo_friendly: null,
        seating_preference: null,
        seating_requirement: null,
      },
      locale: 'ko',
    });
    expect(result.status).toBe('ok');
    expect(result.clarification).toBeNull();
    expect(result.applied_conditions).toEqual({
      all: [
        { field: 'area', op: 'eq', value: 'hongdae' },
        { field: 'price_krw', op: 'lte', value: 40000 },
      ],
    });
    expect(result.items.length).toBeGreaterThan(0);
    expect(result.items.length).toBeLessThanOrEqual(3);
    for (const item of result.items) {
      expect(item).not.toHaveProperty('score');
      expect(item.event.venue.area).toBe('hongdae');
      expect(item.event.price_krw).not.toBeNull();
      expect(item.event.price_krw!).toBeLessThanOrEqual(40000);
      expect(item.reason.length).toBeGreaterThan(0);
    }
    expect(result.total_matches!).toBeGreaterThanOrEqual(result.items.length);
    expect(result.search_limited).toBe(result.total_matches! > result.items.length);
    expect(result.used_fallback).toBe(true); // AI 순위 미적용 (검색어 없음)

    // 검색어가 있으면 AI(Gemini) 경로: 성공하면 AI 순서·검증된 카드, 공급자 장애면 503 (필터 결과로 대체 금지)
    const filters = { ...result.applied_filters, area: null, max_price_krw: null, mood_tags: [] };
    try {
      const ai = await ampApi.recommend({ query: '잔잔한 공연', filters, locale: 'ko' });
      expect(['ok', 'needs_clarification']).toContain(ai.status);
      expect(ai.items.length).toBeLessThanOrEqual(3);
      for (const item of ai.items) expect(item).not.toHaveProperty('score');
      if (ai.status === 'needs_clarification') expect(ai.clarification).toBeTruthy();
    } catch (error) {
      expect(error).toMatchObject({ code: 'AI_UNAVAILABLE', status: 503 });
    }
  }, 40_000);

  it('createEvent registers a show that is then readable and listed (writes to the local DB)', async () => {
    const venues = await ampApi.listVenues('클럽에반스');
    const title = `라이브 테스트 등록 ${Date.now()}`;
    const created = await ampApi.createEvent({
      upload_id: null,
      venue_id: venues.items[0].id,
      title,
      starts_at_local: '2026-12-24T20:00:00',
      ends_at_local: null,
      doors_open_at_local: '2026-12-24T19:00:00',
      price_krw: null,
      advance_price_krw: 30000,
      door_price_krw: 35000,
      booking_url: null,
      lineup: ['Test Band'],
      genre: null,
      mood_tags: ['calm'],
      solo_friendly: null,
      seating_type: null,
      seat_assignment: null,
      drink_policy: null,
      description_ko: '원문 소개',
      admission_notes_ko: null,
      source_url: null,
      data_origin: 'demo',
      review_confirmed: true,
    });
    expect(created).toMatchObject({ status: 'published', poster_url: null });
    // 영문은 저장 전에 서버가 자동 생성. 번역만 실패해도 201 등록 성공 + failed (재시도 가능)
    expect(['generated', 'failed']).toContain(created.translation.status);
    const detail = await ampApi.getEvent(created.id, 'ko');
    expect(detail.translation).toEqual(created.translation);
    if (created.translation.status === 'generated') {
      expect(detail.title_en).toBeTruthy();
      expect(detail.description_en).toBeTruthy();
      expect(detail.admission_notes_en).toBeNull(); // 원문 null → 영문 null
    } else {
      expect(detail.title_en).toBeNull();
    }
    expect(detail).toMatchObject({
      title,
      starts_at: '2026-12-24T11:00:00Z',
      doors_open_at: '2026-12-24T10:00:00Z',
      price_krw: 30000,
      price_basis: 'advance',
      data_origin: 'demo',
      lineup: ['Test Band'],
    });
    const listed = await ampApi.listEvents({
      upcoming: true,
      limit: 50,
      locale: 'ko',
      date: '2026-12-24',
    });
    expect(listed.items.map((item) => item.id)).toContain(created.id);
    await expect(
      ampApi.createEvent({ ...(detail as unknown as object), review_confirmed: true } as never),
    ).rejects.toMatchObject({ status: 422 }); // 서버 전용 필드(price_basis 등) 포함 → 거절
  }, 40_000);
});
