import type { ReactNode } from 'react';
import { useApp } from '../lib/context';
import { moods, money } from '../lib/format';
import {
  representativePrice,
  type RegistrationErrors,
  type RegistrationForm,
} from '../lib/registration';
import type { Mood, VenueSummary } from '../types/api';
import { ErrorState, Notice } from './Feedback';

interface Props {
  value: RegistrationForm;
  onChange: (value: RegistrationForm) => void;
  errors: RegistrationErrors;
  needsReview: string[];
  venues: VenueSummary[];
  venueLoading: boolean;
  venueError: unknown;
  onVenueRetry: () => void;
  venueQuery: string;
  onVenueQuery: (query: string) => void;
}
function Field({
  name,
  label,
  children,
  error,
  needsReview = false,
  required = false,
  hint,
}: {
  name: string;
  label: string;
  children: ReactNode;
  error?: string;
  needsReview?: boolean;
  required?: boolean;
  hint?: string;
}) {
  const { t } = useApp();
  return (
    <div className={`field ${error ? 'invalid' : ''} ${needsReview ? 'review-needed' : ''}`}>
      <label htmlFor={`form-${name}`}>
        <span>
          {label}
          {required && <span className="required-mark"> *</span>}
        </span>
        {needsReview && <small className="review-badge">{t('확인 필요', 'Please review')}</small>}
      </label>
      {children}
      {hint && <small>{hint}</small>}
      {error && (
        <span className="field-error" id={`error-${name}`} role="alert">
          {error}
        </span>
      )}
    </div>
  );
}
export function ReviewForm({
  value,
  onChange,
  errors,
  needsReview,
  venues,
  venueLoading,
  venueError,
  onVenueRetry,
  venueQuery,
  onVenueQuery,
}: Props) {
  const { locale, t } = useApp();
  function change<K extends keyof RegistrationForm>(name: K, next: RegistrationForm[K]) {
    // Any edit invalidates prior original-information confirmation.
    onChange({
      ...value,
      [name]: next,
      review_confirmed: name === 'review_confirmed' ? Boolean(next) : false,
    });
  }
  function input(
    name: keyof RegistrationForm,
    label: string,
    type = 'text',
    options: { required?: boolean; hint?: string; maxLength?: number; disabled?: boolean } = {},
  ) {
    return (
      <Field
        name={name}
        label={label}
        error={errors[name]}
        needsReview={needsReview.includes(name)}
        required={options.required}
        hint={options.hint}
      >
        <input
          id={`form-${name}`}
          type={type}
          value={String(value[name])}
          onChange={(e) => change(name, e.target.value as never)}
          aria-invalid={!!errors[name]}
          aria-describedby={errors[name] ? `error-${name}` : undefined}
          maxLength={options.maxLength}
          disabled={options.disabled}
          {...(type === 'number' ? { min: 0, step: 1 } : {})}
        />
      </Field>
    );
  }
  function select(
    name: 'seating_type' | 'seat_assignment' | 'solo_friendly',
    label: string,
    choices: [string, string][],
  ) {
    return (
      <Field name={name} label={label}>
        <select
          id={`form-${name}`}
          value={value[name]}
          onChange={(e) => change(name, e.target.value as never)}
        >
          <option value="">{t('확인 필요', 'Not confirmed')}</option>
          {choices.map(([key, name]) => (
            <option key={key} value={key}>
              {name}
            </option>
          ))}
        </select>
      </Field>
    );
  }
  function textarea(name: 'description_ko' | 'drink_policy' | 'admission_notes_ko', label: string) {
    return (
      <Field name={name} label={label} error={errors[name]}>
        <textarea
          rows={3}
          id={`form-${name}`}
          value={value[name]}
          maxLength={4000}
          onChange={(e) => change(name, e.target.value)}
          aria-invalid={!!errors[name]}
          aria-describedby={errors[name] ? `error-${name}` : undefined}
        />
        <small>{value[name].length} / 4,000</small>
      </Field>
    );
  }
  const splitPrice = value.advance_price_krw !== '' || value.door_price_krw !== '';
  return (
    <>
      <section className="form-section">
        <div className="form-section-heading">
          <span>01</span>
          <div>
            <h2>{t('공연 기본 정보', 'The essentials')}</h2>
            <p>
              {t(
                '포스터의 원문을 확인하고, 틀린 부분을 수정해 주세요.',
                'Check the original information and correct anything that needs attention.',
              )}
            </p>
          </div>
        </div>
        {input('title', t('공연명', 'Original show title'), 'text', {
          required: true,
          maxLength: 120,
        })}
        <div className="venue-picker">
          <label className="field">
            <span>{t('공연장 찾기', 'Find an existing venue')}</span>
            <input
              type="search"
              value={venueQuery}
              onChange={(e) => onVenueQuery(e.target.value)}
              placeholder={t('공연장 이름으로 검색', 'Search by venue name')}
              maxLength={100}
            />
          </label>
          <Field
            name="venue_id"
            label={t('공연장 선택', 'Venue')}
            error={errors.venue_id}
            needsReview={needsReview.includes('venue_id')}
            required
          >
            <select
              id="form-venue_id"
              value={value.venue_id}
              onChange={(e) => change('venue_id', e.target.value)}
              aria-invalid={!!errors.venue_id}
              aria-describedby={errors.venue_id ? 'error-venue_id' : undefined}
            >
              <option value="">
                {venueLoading
                  ? t('공연장을 불러오는 중…', 'Loading venues…')
                  : t('등록된 공연장을 선택해 주세요', 'Select an existing venue')}
                {!venueLoading && !venues.length ? t(' · 목록 없음', ' · no venues available') : ''}
              </option>
              {venues.map((venue) => (
                <option key={venue.id} value={venue.id}>
                  {venue.name} ·{' '}
                  {venue.area === 'sinchon' ? t('신촌', 'Sinchon') : t('홍대', 'Hongdae')}
                </option>
              ))}
            </select>
          </Field>
          {!!venueError && <ErrorState compact error={venueError} onRetry={onVenueRetry} />}
          <p className="helper-text">
            {t(
              '기존 공연장만 선택할 수 있어요. 장소를 찾지 못하면 등록을 완료할 수 없습니다.',
              'Choose an existing venue. Registration requires a valid venue selection.',
            )}
          </p>
        </div>
        <div className="two-columns">
          {input(
            'starts_at_local',
            t('공연 시작 · 한국 시간', 'Showtime · Korea time'),
            'datetime-local',
            { required: true },
          )}
          {input(
            'doors_open_at_local',
            t('입장 시작 · 한국 시간', 'Doors open · Korea time'),
            'datetime-local',
            { hint: t('입장 시간이 없으면 비워 두세요.', 'Leave blank if door time is unknown.') },
          )}
        </div>
        {input(
          'ends_at_local',
          t('공연 종료 · 한국 시간', 'Show ends · Korea time'),
          'datetime-local',
        )}
        <div className="two-columns">
          {input('lineup', t('출연진', 'Lineup'), 'text', {
            hint: t('여러 팀은 쉼표로 구분해 주세요.', 'Separate artists with commas.'),
          })}
          {input('genre', t('장르', 'Genre'))}
        </div>
      </section>
      <section className="form-section">
        <div className="form-section-heading">
          <span>02</span>
          <div>
            <h2>{t('가격과 관람 방식', 'Tickets & seating')}</h2>
            <p>
              {t(
                '미확인 가격은 비워 두세요. 무료가 확인된 경우에만 0을 입력해요.',
                'Leave unknown prices blank. Use 0 only for confirmed free admission.',
              )}
            </p>
          </div>
        </div>
        <div className="two-columns">
          {input('advance_price_krw', t('예매가 · 원', 'Advance price · KRW'), 'number')}
          {input('door_price_krw', t('현장가 · 원', 'Door price · KRW'), 'number')}
        </div>
        {input('price_krw', t('구분 없는 단일 가격 · 원', 'Single price · KRW'), 'number', {
          disabled: splitPrice,
          hint: splitPrice
            ? t(
                '예매가·현장가 중 가장 낮은 금액을 대표 가격으로 보냅니다.',
                'The lower specified ticket price is used as the representative price.',
              )
            : undefined,
        })}
        <div className="price-preview">
          <span>{t('표시될 대표 가격', 'Representative price')}</span>
          <strong>{money(representativePrice(value), locale)}</strong>
        </div>
        <div className="two-columns">
          {select('seating_type', t('관람 방식', 'Seating type'), [
            ['seated', t('좌석', 'Seated')],
            ['standing', t('스탠딩', 'Standing')],
            ['mixed', t('좌석·스탠딩 혼합', 'Mixed')],
          ])}
          {select('seat_assignment', t('좌석 배정', 'Seat assignment'), [
            ['assigned', t('지정석', 'Assigned')],
            ['unassigned', t('비지정석', 'Unassigned')],
          ])}
        </div>
        {select('solo_friendly', t('혼자 관람 적합성', 'Solo-friendly information'), [
          ['true', t('적합함이 확인됨', 'Confirmed suitable')],
          ['false', t('적합하지 않음이 확인됨', 'Confirmed unsuitable')],
        ])}
        <fieldset className="mood-picker">
          <legend>{t('확인한 분위기 태그', 'Confirmed atmosphere tags')}</legend>
          <div className="chips">
            {(Object.keys(moods) as Mood[]).map((mood) => (
              <button
                type="button"
                className="chip"
                aria-pressed={value.mood_tags.includes(mood)}
                key={mood}
                onClick={() =>
                  change(
                    'mood_tags',
                    value.mood_tags.includes(mood)
                      ? value.mood_tags.filter((x) => x !== mood)
                      : [...value.mood_tags, mood],
                  )
                }
              >
                {moods[mood][locale === 'ko' ? 0 : 1]}
              </button>
            ))}
          </div>
        </fieldset>
      </section>
      <section className="form-section">
        <div className="form-section-heading">
          <span>03</span>
          <div>
            <h2>{t('공연 소개와 방문 안내', 'About the show & visiting')}</h2>
            <p>
              {t(
                '한국어 원문을 등록하면 영어 안내는 자동으로 생성됩니다.',
                'English guidance is generated automatically from the original Korean text.',
              )}
            </p>
          </div>
        </div>
        {textarea('description_ko', t('공연 소개 원문', 'Original show description'))}
        {textarea('admission_notes_ko', t('입장·관람 안내 원문', 'Original entry & show guidance'))}
        {textarea('drink_policy', t('드링크 안내 원문', 'Original drink policy'))}
        {input('booking_url', t('예매 링크', 'Ticket link'), 'url', { hint: 'https://' })}
        {input('source_url', t('정보 출처 링크', 'Source link'), 'url', { hint: 'https://' })}
        <Notice>
          {t(
            '영어는 등록 시 자동 번역되며 AI-translated로 표시됩니다. 번역만 실패해도 공연 원문은 등록되고 번역을 다시 요청할 수 있어요.',
            'English is automatically translated and marked AI-translated. If translation fails, the original show is still saved and translation can be retried.',
          )}
        </Notice>
        <p className="helper-text">
          {t(
            '현재 등록 데이터는 시연용(DEMO)으로 구분됩니다.',
            'Shows registered here are marked as demonstration data (DEMO).',
          )}
        </p>
        <label className="confirmation">
          <input
            type="checkbox"
            id="form-review_confirmed"
            checked={value.review_confirmed}
            onChange={(e) => change('review_confirmed', e.target.checked)}
            aria-invalid={!!errors.review_confirmed}
            aria-describedby={errors.review_confirmed ? 'error-review_confirmed' : undefined}
          />
          <span>
            {t(
              '공연 원문과 날짜·가격·공연장을 확인했습니다.',
              'I have checked the original information, date, prices, and venue.',
            )}
          </span>
        </label>
        {errors.review_confirmed && (
          <p className="field-error" role="alert" id="error-review_confirmed">
            {errors.review_confirmed}
          </p>
        )}
      </section>
    </>
  );
}
