import type { Locale, SearchFilters, Translation } from '../types/api';

export const emptyFilters = (): SearchFilters => ({
  date: null,
  area: null,
  max_price_krw: null,
  mood_tags: [],
  solo_friendly: null,
  seating_preference: null,
  seating_requirement: null,
});
export const hasFilters = (filters: SearchFilters) =>
  Object.values(filters).some((value) =>
    Array.isArray(value) ? value.length > 0 : value !== null,
  );
export function kstDate(offset = 0): string {
  const day = new Intl.DateTimeFormat('en-CA', {
    timeZone: 'Asia/Seoul',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).format(new Date());
  const date = new Date(`${day}T12:00:00+09:00`);
  date.setUTCDate(date.getUTCDate() + offset);
  return new Intl.DateTimeFormat('en-CA', {
    timeZone: 'Asia/Seoul',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).format(date);
}
export function formatDate(value: string | null, locale: Locale, timeOnly = false): string {
  if (!value || Number.isNaN(Date.parse(value)))
    return locale === 'ko' ? '확인 필요' : 'Not confirmed';
  return new Intl.DateTimeFormat(locale === 'ko' ? 'ko-KR' : 'en-GB', {
    timeZone: 'Asia/Seoul',
    ...(timeOnly ? {} : ({ month: 'long', day: 'numeric', weekday: 'short' } as const)),
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  }).format(new Date(value));
}
export function money(value: number | null, locale: Locale): string {
  if (value === null || !Number.isFinite(value))
    return locale === 'ko' ? '가격 확인 필요' : 'Price not confirmed';
  if (value === 0) return locale === 'ko' ? '무료' : 'Free';
  return locale === 'ko'
    ? `${value.toLocaleString('ko-KR')}원`
    : `₩${value.toLocaleString('en-GB')}`;
}
export function priceLabel(value: number | null, basis: string | null, locale: Locale): string {
  if (value === null || value === 0) return money(value, locale);
  const prefix =
    basis === 'advance'
      ? locale === 'ko'
        ? '예매 '
        : 'Advance '
      : basis === 'door'
        ? locale === 'ko'
          ? '현장 '
          : 'Door '
        : '';
  return prefix + money(value, locale);
}
export function safeLink(value: string | null | undefined): string | undefined {
  if (!value) return undefined;
  try {
    const url = new URL(value);
    return url.protocol === 'https:' ? url.href : undefined;
  } catch {
    return undefined;
  }
}
export function mediaUrl(value: string | null | undefined): string | undefined {
  if (!value) return undefined;
  if (value.startsWith('/media/'))
    return new URL(value, import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000').href;
  return safeLink(value);
}
export function translatedText(
  original: string | null | undefined,
  english: string | null | undefined,
  translation: Translation | undefined,
  locale: Locale,
  showOriginal = false,
) {
  const available =
    !!english?.trim() &&
    (translation?.status === 'generated' || translation?.status === 'reviewed');
  return {
    text:
      locale === 'en' && !showOriginal && available
        ? english!
        : original || (locale === 'ko' ? '확인 필요' : 'Not confirmed'),
    automatic: locale === 'en' && !showOriginal && available && translation?.status === 'generated',
    missing: locale === 'en' && !showOriginal && !!original && !available,
  };
}
export const areaName = (area: string, locale: Locale) =>
  area === 'sinchon'
    ? locale === 'ko'
      ? '신촌'
      : 'Sinchon'
    : locale === 'ko'
      ? '홍대'
      : 'Hongdae';
export const seatingName = (seating: string | null, locale: Locale) => {
  const names: Record<string, [string, string]> = {
    seated: ['좌석', 'Seated'],
    standing: ['스탠딩', 'Standing'],
    mixed: ['좌석·스탠딩 혼합', 'Mixed seating'],
  };
  return seating && names[seating]
    ? names[seating][locale === 'ko' ? 0 : 1]
    : locale === 'ko'
      ? '확인 필요'
      : 'Not confirmed';
};
export const moods = {
  calm: ['잔잔한', 'Calm'],
  energetic: ['신나는', 'Energetic'],
  romantic: ['로맨틱', 'Romantic'],
  acoustic: ['어쿠스틱', 'Acoustic'],
} as const;
