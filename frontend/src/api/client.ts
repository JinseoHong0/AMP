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
    public details: Record<string, unknown> = {},
  ) {
    super(message);
  }
}

/**
 * Poster parsing uses the real backend. Other adapters remain explicit integration boundaries.
 * No runtime fake records or simulated success are provided.
 * BACKEND_TODO: Add authenticated HTTP calls for the remaining endpoints.
 * Read README first: AI chooses recommendation order; English is generated only at registration.
 */
function unavailable<T>(): Promise<T> {
  return Promise.reject(new ApiError('NOT_CONNECTED', 'The service is not connected yet.'));
}

async function parsePoster(file: File): Promise<PosterExtraction> {
  const origin = (import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000').replace(/\/$/, '');
  const body = new FormData();
  body.append('file', file);
  const controller = new AbortController();
  // Allows the backend's configurable <=60s model timeout plus image upload/validation.
  const timeout = setTimeout(() => controller.abort(), 75_000);
  try {
    const response = await fetch(`${origin}/api/posters/parse`, {
      method: 'POST',
      body,
      signal: controller.signal,
      // The browser supplies Content-Type with the multipart boundary. No API key is sent.
    });
    const payload = await response.json().catch(() => null);
    if (!response.ok) {
      throw new ApiError(
        payload?.error?.code || 'HTTP_ERROR',
        payload?.error?.message || 'Poster extraction failed.',
        response.status,
        payload?.error?.details || {},
      );
    }
    if (!payload?.upload_id || !payload.extracted || !payload.venue_match) {
      throw new ApiError('INVALID_RESPONSE', 'The extraction response is incomplete.');
    }
    return payload as PosterExtraction;
  } catch (error) {
    if (error instanceof ApiError) throw error;
    throw new ApiError(
      controller.signal.aborted ? 'REQUEST_TIMEOUT' : 'NETWORK_ERROR',
      controller.signal.aborted ? 'Poster extraction timed out.' : 'Cannot reach the backend.',
    );
  } finally {
    clearTimeout(timeout);
  }
}

export const ampApi = {
  // BACKEND_TODO: GET /api/health. Health alone does not verify AI readiness.
  health: (): Promise<{ status: string }> => unavailable(),
  // BACKEND_TODO: GET /api/events with params. items are direct EventSummary objects.
  listEvents: (_params: EventListParams): Promise<EventList> => unavailable(),
  // BACKEND_TODO: GET /api/events/{id}; cancelled/unpublished records are 404.
  getEvent: (_id: number, _locale: Locale): Promise<EventDetail> => unavailable(),
  // BACKEND_TODO: GET /api/venues?q=...&limit=50. Select an existing ID, never create a venue.
  listVenues: (_query: string): Promise<VenueList> => unavailable(),
  // BACKEND_TODO: GET /api/venues/{id}. Keep venue defaults distinct from event policies.
  getVenue: (_id: number, _locale: Locale): Promise<Venue> => unavailable(),
  // BACKEND_TODO: POST /api/recommend JSON. Keep AI order, clarification and search limits.
  recommend: (_request: RecommendRequest): Promise<Recommendations> => unavailable(),
  // POST /api/posters/parse. Existing-venue matching happens on the server; this does not save an event.
  parsePoster,
  // BACKEND_TODO: POST /api/events JSON; HTTP 201 remains success when only translation fails.
  createEvent: (_request: CreateEventRequest): Promise<CreatedEvent> => unavailable(),
  // BACKEND_TODO: POST /api/events/{id}/translate, NO body. Never re-create the event on retry.
  retryTranslation: (_id: number): Promise<{ id: number; translation: Translation }> =>
    unavailable(),
};
