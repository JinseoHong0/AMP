import type { CreateEventRequest, Mood, PosterExtraction, Seating } from '../types/api';

export interface RegistrationForm {
  title: string;
  venue_id: string;
  starts_at_local: string;
  doors_open_at_local: string;
  ends_at_local: string;
  price_krw: string;
  advance_price_krw: string;
  door_price_krw: string;
  lineup: string;
  genre: string;
  mood_tags: Mood[];
  solo_friendly: '' | 'true' | 'false';
  seating_type: '' | Seating;
  seat_assignment: '' | 'assigned' | 'unassigned';
  drink_policy: string;
  description_ko: string;
  admission_notes_ko: string;
  booking_url: string;
  source_url: string;
  review_confirmed: boolean;
}
export const emptyRegistration = (): RegistrationForm => ({
  title: '',
  venue_id: '',
  starts_at_local: '',
  doors_open_at_local: '',
  ends_at_local: '',
  price_krw: '',
  advance_price_krw: '',
  door_price_krw: '',
  lineup: '',
  genre: '',
  mood_tags: [],
  solo_friendly: '',
  seating_type: '',
  seat_assignment: '',
  drink_policy: '',
  description_ko: '',
  admission_notes_ko: '',
  booking_url: '',
  source_url: '',
  review_confirmed: false,
});
export function fromExtraction(result: PosterExtraction): RegistrationForm {
  const item = result.extracted;
  return {
    ...emptyRegistration(),
    title: item.title || '',
    starts_at_local: item.starts_at_local?.slice(0, 16) || '',
    doors_open_at_local: item.doors_open_at_local?.slice(0, 16) || '',
    venue_id:
      result.venue_match.status === 'matched' && result.venue_match.venue_id
        ? String(result.venue_match.venue_id)
        : '',
    price_krw: item.price_krw === null ? '' : String(item.price_krw),
    advance_price_krw: item.advance_price_krw === null ? '' : String(item.advance_price_krw),
    door_price_krw: item.door_price_krw === null ? '' : String(item.door_price_krw),
    lineup: item.lineup.join(', '),
    genre: item.genre || '',
  };
}
const amount = (input: string) => (input.trim() === '' ? null : Number(input));
export function representativePrice(form: RegistrationForm): number | null {
  const prices = [amount(form.advance_price_krw), amount(form.door_price_krw)].filter(
    (value): value is number => value !== null,
  );
  return prices.length ? Math.min(...prices) : amount(form.price_krw);
}
export type RegistrationErrors = Partial<Record<keyof RegistrationForm, string>>;
export function validateRegistration(
  form: RegistrationForm,
  t: (ko: string, en: string) => string,
): RegistrationErrors {
  const errors: RegistrationErrors = {};
  if (!form.title.trim() || form.title.trim().length > 120)
    errors.title = t(
      '공연명을 1~120자로 입력해 주세요.',
      'Enter a title between 1 and 120 characters.',
    );
  if (!/^\d+$/.test(form.venue_id) || Number(form.venue_id) <= 0)
    errors.venue_id = t('기존 공연장을 선택해 주세요.', 'Select an existing venue.');
  const parseTime = (value: string) =>
    /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/.test(value) ? Date.parse(`${value}:00+09:00`) : NaN;
  const start = parseTime(form.starts_at_local);
  if (!Number.isFinite(start))
    errors.starts_at_local = t(
      '공연 시작 일시를 입력해 주세요.',
      'Enter a valid show start date and time.',
    );
  if (
    form.doors_open_at_local &&
    (!Number.isFinite(parseTime(form.doors_open_at_local)) ||
      parseTime(form.doors_open_at_local) > start)
  )
    errors.doors_open_at_local = t(
      '입장은 공연 시작 이전 또는 같은 시각이어야 해요.',
      'Doors must open at or before showtime.',
    );
  if (
    form.ends_at_local &&
    (!Number.isFinite(parseTime(form.ends_at_local)) || parseTime(form.ends_at_local) <= start)
  )
    errors.ends_at_local = t('종료는 공연 시작 이후여야 해요.', 'The end must be after showtime.');
  for (const field of ['price_krw', 'advance_price_krw', 'door_price_krw'] as const) {
    const input = form[field].trim();
    if (input !== '' && (!/^\d+$/.test(input) || !Number.isSafeInteger(Number(input))))
      errors[field] = t(
        '0 이상의 정수로 입력해 주세요. 미확인은 비워 두세요.',
        'Enter a non-negative whole number, or leave unknown prices blank.',
      );
  }
  for (const field of ['booking_url', 'source_url'] as const) {
    if (form[field].trim()) {
      try {
        if (new URL(form[field].trim()).protocol !== 'https:') throw new Error();
      } catch {
        errors[field] = t(
          'https://로 시작하는 올바른 주소를 입력해 주세요.',
          'Enter a valid HTTPS address.',
        );
      }
    }
  }
  for (const field of ['drink_policy', 'description_ko', 'admission_notes_ko'] as const) {
    if (form[field].length > 4000)
      errors[field] = t('4,000자 이내로 입력해 주세요.', 'Use no more than 4,000 characters.');
  }
  if (!form.review_confirmed)
    errors.review_confirmed = t(
      '원문 정보 확인에 체크해 주세요.',
      'Confirm that you reviewed the original information.',
    );
  return errors;
}
export function registrationPayload(
  form: RegistrationForm,
  uploadId: string | null,
): CreateEventRequest {
  const nullable = (value: string) => value.trim() || null;
  const time = (value: string) => (value ? `${value}:00` : null);
  // BACKEND_TODO: Send original fields only. The server revalidates all values and generates English.
  return {
    title: form.title.trim(),
    venue_id: Number(form.venue_id),
    upload_id: uploadId,
    starts_at_local: time(form.starts_at_local)!,
    ends_at_local: time(form.ends_at_local),
    doors_open_at_local: time(form.doors_open_at_local),
    price_krw: representativePrice(form),
    advance_price_krw: amount(form.advance_price_krw),
    door_price_krw: amount(form.door_price_krw),
    lineup: form.lineup
      .split(',')
      .map((name) => name.trim())
      .filter(Boolean),
    genre: nullable(form.genre),
    mood_tags: form.mood_tags,
    solo_friendly: form.solo_friendly === '' ? null : form.solo_friendly === 'true',
    seating_type: form.seating_type || null,
    seat_assignment: form.seat_assignment || null,
    drink_policy: nullable(form.drink_policy),
    description_ko: nullable(form.description_ko),
    admission_notes_ko: nullable(form.admission_notes_ko),
    booking_url: nullable(form.booking_url),
    source_url: nullable(form.source_url),
    data_origin: 'demo',
    review_confirmed: true,
  };
}

export async function validatePoster(file: File): Promise<'type' | 'size' | 'content' | null> {
  if (!['image/jpeg', 'image/png', 'image/webp'].includes(file.type)) return 'type';
  if (file.size > 5 * 1024 * 1024) return 'size';
  if (file.size === 0) return 'content';
  const bytes = new Uint8Array(await file.slice(0, 12).arrayBuffer());
  const png =
    bytes[0] === 137 &&
    bytes[1] === 80 &&
    bytes[2] === 78 &&
    bytes[3] === 71 &&
    bytes[4] === 13 &&
    bytes[5] === 10 &&
    bytes[6] === 26 &&
    bytes[7] === 10;
  const jpg = bytes[0] === 255 && bytes[1] === 216 && bytes[2] === 255;
  const webp =
    String.fromCharCode(...bytes.slice(0, 4)) === 'RIFF' &&
    String.fromCharCode(...bytes.slice(8, 12)) === 'WEBP';
  if (!(
    (file.type === 'image/png' && png) ||
    (file.type === 'image/jpeg' && jpg) ||
    (file.type === 'image/webp' && webp)
  ))
    return 'content';
  // Browser decoding checks corrupt files; the backend must independently validate uploaded bytes.
  try {
    const bitmap = await createImageBitmap(file);
    bitmap.close();
    return null;
  } catch {
    return 'content';
  }
}
