import { RotateCcw } from 'lucide-react';
import { useApp } from '../lib/context';
import { emptyFilters, kstDate, moods } from '../lib/format';
import type { Mood, SearchFilters } from '../types/api';

export function Filters({
  value,
  onChange,
  preferences = true,
  disabled = false,
}: {
  value: SearchFilters;
  onChange: (value: SearchFilters) => void;
  preferences?: boolean;
  disabled?: boolean;
}) {
  const { locale, t } = useApp();
  function set<K extends keyof SearchFilters>(key: K, next: SearchFilters[K]) {
    onChange({ ...value, [key]: next });
  }
  return (
    <fieldset className="filter-panel" disabled={disabled}>
      <legend className="sr-only">{t('검색 조건', 'Search filters')}</legend>
      <div className="filter-heading">
        <span>{t('원하는 조건을 골라보세요', 'Make it your kind of night')}</span>
        <button type="button" className="text-button" onClick={() => onChange(emptyFilters())}>
          <RotateCcw size={13} />
          {t('초기화', 'Reset')}
        </button>
      </div>
      <div className="filter-grid">
        <label className="field">
          <span>{t('날짜', 'Date')}</span>
          <input
            type="date"
            value={value.date || ''}
            onChange={(e) => set('date', e.target.value || null)}
          />
        </label>
        <label className="field">
          <span>{t('동네', 'Area')}</span>
          <select
            value={value.area || ''}
            onChange={(e) => set('area', (e.target.value || null) as SearchFilters['area'])}
          >
            <option value="">{t('모든 동네', 'Any area')}</option>
            <option value="sinchon">{t('신촌', 'Sinchon')}</option>
            <option value="hongdae">{t('홍대', 'Hongdae')}</option>
          </select>
        </label>
        <label className="field">
          <span>{t('최대 티켓 가격', 'Maximum ticket price')}</span>
          <input
            type="number"
            min="0"
            step="1"
            placeholder={t('제한 없음', 'No limit')}
            value={value.max_price_krw ?? ''}
            onChange={(e) =>
              set('max_price_krw', e.target.value === '' ? null : Number(e.target.value))
            }
          />
        </label>
        <label className="field">
          <span>{t('필수 관람 방식', 'Required seating')}</span>
          <select
            value={value.seating_requirement || ''}
            onChange={(e) =>
              set(
                'seating_requirement',
                (e.target.value || null) as SearchFilters['seating_requirement'],
              )
            }
          >
            <option value="">{t('상관없음', 'Any')}</option>
            <option value="seated">{t('좌석 공연만', 'Seated only')}</option>
            <option value="standing">{t('스탠딩 공연만', 'Standing only')}</option>
          </select>
        </label>
      </div>
      <div className="chips quick-dates">
        <button
          type="button"
          className="chip"
          aria-pressed={value.date === kstDate()}
          onClick={() => set('date', value.date === kstDate() ? null : kstDate())}
        >
          {t('오늘', 'Today')}
        </button>
        <button
          type="button"
          className="chip"
          aria-pressed={value.date === kstDate(1)}
          onClick={() => set('date', value.date === kstDate(1) ? null : kstDate(1))}
        >
          {t('내일', 'Tomorrow')}
        </button>
        <button
          type="button"
          className="chip"
          aria-pressed={value.max_price_krw === 20000}
          onClick={() => set('max_price_krw', value.max_price_krw === 20000 ? null : 20000)}
        >
          {t('2만 원 이하', 'Under ₩20,000')}
        </button>
      </div>
      {preferences && (
        <div className="preference-panel">
          <p className="eyebrow">
            {t('선호 조건 · 꼭 맞지 않아도 괜찮아요', 'PREFERENCES · NICE TO HAVE')}
          </p>
          <div className="chips">
            {(Object.keys(moods) as Mood[]).map((mood) => (
              <button
                type="button"
                className="chip"
                aria-pressed={value.mood_tags.includes(mood)}
                key={mood}
                onClick={() =>
                  set(
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
            <button
              type="button"
              className="chip"
              aria-pressed={value.solo_friendly === true}
              onClick={() => set('solo_friendly', value.solo_friendly ? null : true)}
            >
              {t('혼자 가기 좋은', 'Solo-friendly')}
            </button>
          </div>
          <label className="field seating-preference">
            <span>{t('선호하는 관람 방식', 'Seating preference')}</span>
            <select
              value={value.seating_preference || ''}
              onChange={(e) =>
                set(
                  'seating_preference',
                  (e.target.value || null) as SearchFilters['seating_preference'],
                )
              }
            >
              <option value="">{t('선호 없음', 'No preference')}</option>
              <option value="seated">{t('좌석이면 좋아요', 'Prefer seated')}</option>
              <option value="standing">{t('스탠딩이면 좋아요', 'Prefer standing')}</option>
            </select>
          </label>
        </div>
      )}
    </fieldset>
  );
}
