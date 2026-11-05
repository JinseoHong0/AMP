import type {
  CreatedEvent,
  CreateEventRequest,
  EventDetail,
  EventList,
  EventListParams,
  Locale,
  PosterExtraction,
  Recommendations,
  RecommendRequest,
  Translation,
  Venue,
  VenueList,
} from '../types/api';

export class ApiError extends Error {
  constructor(
    public code: string,
    message: string,
    public status = 0,
  ) {
    super(message);
  }
}

/**
 * BACKEND_TODO: Replace only these adapters with authenticated HTTP calls in the next phase.
 * No fetch, fake records, local ranking, image recognition or simulated success is provided here.
 * Map { error: { code, message, details } } to ApiError; preserve 404/422/503 semantics.
 * Use VITE_API_BASE_URL, AbortSignal/timeouts and backend-provided admin credentials when wired.
 * Read README first: AI chooses recommendation order; English is generated only at registration.
 */
function unavailable<T>(): Promise<T> {
  return Promise.reject(new ApiError('NOT_CONNECTED', 'The service is not connected yet.'));
}

/** Same origin source as `format.ts` media URLs. Trailing slashes are trimmed. */
export const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000').replace(
  /\/+$/,
  '',
);
const DEFAULT_TIMEOUT_MS = 15_000;

interface RequestOptions extends Omit<RequestInit, 'signal'> {
  timeoutMs?: number;
}

/**
 * fetch wrapper: JSON response, timeout via AbortController, and the common
 * `{ error: { code, message, details } }` body mapped to ApiError(code, message, HTTP status).
 * Network failures become NETWORK_ERROR and timeouts TIMEOUT (status 0) so the UI shows a retry state.
 */
async function request<T>(
  path: string,
  { timeoutMs = DEFAULT_TIMEOUT_MS, ...init }: RequestOptions = {},
): Promise<T> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      ...init,
      headers: { Accept: 'application/json', ...init.headers },
      signal: controller.signal,
    });
  } catch {
    throw controller.signal.aborted
      ? new ApiError('TIMEOUT', 'The request timed out.')
      : new ApiError('NETWORK_ERROR', 'The server could not be reached.');
  } finally {
    clearTimeout(timer);
  }
  const body: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    const error = (body as { error?: { code?: unknown; message?: unknown } } | null)?.error;
    throw new ApiError(
      typeof error?.code === 'string' ? error.code : 'HTTP_ERROR',
      typeof error?.message === 'string' ? error.message : `Request failed (${response.status}).`,
      response.status,
    );
  }
  return body as T;
}

/** `?a=1&b=2` from defined values only. 0 and false are kept (e.g. max_price_krw=0 means free only). */
function queryString(params: Record<string, string | number | boolean | null | undefined>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== '') search.set(key, String(value));
  }
  const text = search.toString();
  return text ? `?${text}` : '';
}

export const ampApi = {
  // GET /api/health. Health alone does not verify AI readiness.
  health: (): Promise<{ status: string }> => request('/api/health'),
  // GET /api/events with params. items are direct EventSummary objects (not capped at 3).
  listEvents: (params: EventListParams): Promise<EventList> =>
    request(`/api/events${queryString({ ...params })}`),
  // GET /api/events/{id}; cancelled/unpublished records are 404 (EVENT_NOT_FOUND).
  // The endpoint has no locale parameter: original and English fields come together; locale only keys the cache.
  getEvent: (id: number, _locale: Locale): Promise<EventDetail> =>
    request(`/api/events/${encodeURIComponent(String(id))}`),
  // GET /api/venues?q=...&limit=50. Select an existing ID, never create a venue. Empty search → all venues.
  listVenues: (query: string): Promise<VenueList> =>
    request(`/api/venues${queryString({ q: query.trim() || undefined, limit: 50 })}`),
  // GET /api/venues/{id}. Venue defaults stay distinct from event policies; 404 is VENUE_NOT_FOUND.
  // Like getEvent there is no locale parameter: ko/en fields come together and locale only keys the cache.
  getVenue: (id: number, _locale: Locale): Promise<Venue> =>
    request(`/api/venues/${encodeURIComponent(String(id))}`),
  // POST /api/recommend JSON. The raw query is sent as typed; the server/AI decides order (no client re-ranking).
  // AI processing may take up to 30s (docs/AI.md), so this call allows longer than the default timeout.
  recommend: (body: RecommendRequest): Promise<Recommendations> =>
    request('/api/recommend', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
      timeoutMs: 35_000,
    }),
  // BACKEND_TODO: POST /api/posters/parse, FormData key=file; let the browser set multipart headers.
  // Normalize legacy README venue_name_detected here if needed; current API uses extracted.venue_name.
  parsePoster: (_file: File): Promise<PosterExtraction> => unavailable(),
  // POST /api/events JSON (admin; local backend allows loopback without a key — never ship an admin key in VITE_*).
  // HTTP 201 remains success when only translation fails/is pending: the UI must not submit twice.
  createEvent: (body: CreateEventRequest): Promise<CreatedEvent> =>
    request('/api/events', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }),
  // BACKEND_TODO: POST /api/events/{id}/translate, NO body. Never re-create the event on retry.
  retryTranslation: (_id: number): Promise<{ id: number; translation: Translation }> =>
    unavailable(),
};
