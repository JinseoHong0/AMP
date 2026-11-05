/** Wire contracts follow README behavior and docs/API.md JSON field names. */
export type Locale = 'ko' | 'en';
export type Area = 'sinchon' | 'hongdae';
export type Seating = 'standing' | 'seated' | 'mixed';
export type Mood = 'calm' | 'energetic' | 'romantic' | 'acoustic';
export type TranslationStatus = 'not_requested' | 'generated' | 'failed' | 'reviewed';
export interface Translation {
  status: TranslationStatus;
  generated_at: string | null;
}
export interface VenueSummary {
  id: number;
  name: string;
  area: Area;
}
export interface EventSummary {
  id: number;
  title: string;
  title_en?: string | null;
  translation?: Translation;
  starts_at: string;
  price_krw: number | null;
  price_basis: 'advance' | 'door' | 'general' | null;
  advance_price_krw: number | null;
  door_price_krw: number | null;
  genre: string | null;
  mood_tags: Mood[];
  seating_type: Seating | null;
  poster_url: string | null;
  venue: VenueSummary;
  data_origin: 'demo' | 'verified';
}
export interface EventDetail extends Omit<EventSummary, 'venue'> {
  venue_id: number;
  ends_at: string | null;
  doors_open_at: string | null;
  booking_url: string | null;
  lineup: string[];
  solo_friendly: boolean | null;
  seat_assignment: 'assigned' | 'unassigned' | null;
  drink_policy: string | null;
  drink_policy_en?: string | null;
  description_ko: string | null;
  description_en: string | null;
  admission_notes_ko: string | null;
  admission_notes_en: string | null;
  status: 'published';
  source_url: string | null;
  verified_at: string | null;
}
export interface Venue extends VenueSummary {
  address: string;
  floor: string | null;
  entrance_image_url: string | null;
  default_seating_type: Seating | null;
  default_drink_policy: string | null;
  entrance_hint_ko: string | null;
  entrance_hint_en: string | null;
  description_ko: string | null;
  description_en: string | null;
  source_url: string | null;
  verified_at: string | null;
  data_origin: 'demo' | 'verified';
}
export interface SearchFilters {
  date: string | null;
  area: Area | null;
  max_price_krw: number | null;
  mood_tags: Mood[];
  solo_friendly: boolean | null;
  seating_preference: 'seated' | 'standing' | null;
  seating_requirement: 'seated' | 'standing' | null;
}
export interface EventListParams {
  date?: string;
  area?: Area;
  max_price_krw?: number;
  seating_type?: Seating;
  upcoming: boolean;
  limit: number;
  locale: Locale;
}
export interface EventList {
  items: EventSummary[];
  total: number;
  limit: number;
}
export interface VenueList {
  items: VenueSummary[];
  total: number;
}
export interface RecommendRequest {
  query: string;
  filters: SearchFilters;
  locale: Locale;
}
export type QueryCondition =
  | { field: string; op: string; value?: unknown }
  | { all: QueryCondition[] }
  | { any: QueryCondition[] }
  | { not: QueryCondition };
export interface Recommendations {
  status: 'ok' | 'needs_clarification';
  applied_filters: SearchFilters;
  applied_conditions: QueryCondition | null;
  preferences: string[];
  total_matches: number | null;
  items: { event: EventSummary; matched_tags: Mood[]; reason: string }[];
  notice: string | null;
  used_fallback: boolean;
  search_limited: boolean;
  clarification: string | null;
}
export interface PosterExtraction {
  upload_id: string;
  extracted: {
    title: string | null;
    starts_at_local: string | null;
    doors_open_at_local: string | null;
    venue_name: string | null;
    price_krw: number | null;
    advance_price_krw: number | null;
    door_price_krw: number | null;
    lineup: string[];
    genre: string | null;
  };
  venue_match: {
    status: 'matched' | 'ambiguous' | 'not_found' | 'no_name';
    venue_id: number | null;
    candidates: VenueSummary[];
  };
  needs_review: string[];
  warnings: string[];
}
export interface CreateEventRequest {
  upload_id: string | null;
  venue_id: number;
  title: string;
  starts_at_local: string;
  ends_at_local: string | null;
  doors_open_at_local: string | null;
  price_krw: number | null;
  advance_price_krw: number | null;
  door_price_krw: number | null;
  booking_url: string | null;
  lineup: string[];
  genre: string | null;
  mood_tags: Mood[];
  solo_friendly: boolean | null;
  seating_type: Seating | null;
  seat_assignment: 'assigned' | 'unassigned' | null;
  drink_policy: string | null;
  description_ko: string | null;
  admission_notes_ko: string | null;
  source_url: string | null;
  data_origin: 'demo';
  review_confirmed: true;
  // English text, price_basis and translation metadata are server-owned: never submit them.
}
export interface CreatedEvent {
  id: number;
  status: 'published';
  poster_url: string | null;
  translation: Translation;
  warnings: string[];
  message: string;
}
