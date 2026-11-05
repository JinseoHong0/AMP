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
  // BACKEND_TODO: POST /api/posters/parse, FormData key=file; let the browser set multipart headers.
  // Normalize legacy README venue_name_detected here if needed; current API uses extracted.venue_name.
  parsePoster: (_file: File): Promise<PosterExtraction> => unavailable(),
  // BACKEND_TODO: POST /api/events JSON; HTTP 201 remains success when only translation fails.
  createEvent: (_request: CreateEventRequest): Promise<CreatedEvent> => unavailable(),
  // BACKEND_TODO: POST /api/events/{id}/translate, NO body. Never re-create the event on retry.
  retryTranslation: (_id: number): Promise<{ id: number; translation: Translation }> =>
    unavailable(),
};
