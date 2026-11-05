import { useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { ArrowUpRight, SlidersHorizontal } from 'lucide-react';
import { ampApi } from '../api/client';
import { useApp } from '../lib/context';
import { emptyFilters } from '../lib/format';
import { useResource } from '../lib/useResource';
import { Filters } from '../components/Filters';
import { EventCard } from '../components/EventCard';
import { EmptyState, ErrorState, Loading, Notice } from '../components/Feedback';
import type { Area, SearchFilters } from '../types/api';

export default function EventList() {
  const { locale, t } = useApp();
  const [params, setParams] = useSearchParams();
  const [expanded, setExpanded] = useState(false);
  const area = ['sinchon', 'hongdae'].includes(params.get('area') || '')
    ? (params.get('area') as Area)
    : null;
  const rawPrice = params.get('max_price_krw');
  const price =
    rawPrice !== null && /^\d+$/.test(rawPrice) && Number.isSafeInteger(Number(rawPrice))
      ? Number(rawPrice)
      : null;
  const seat = params.get('seating_type');
  const filters: SearchFilters = {
    ...emptyFilters(),
    area,
    date: /^\d{4}-\d{2}-\d{2}$/.test(params.get('date') || '') ? params.get('date') : null,
    max_price_krw: price,
    seating_requirement: seat === 'seated' || seat === 'standing' ? seat : null,
  };
  const limit = params.get('limit') === '50' ? 50 : 20;
  const resource = useResource(`events:${params.toString()}:${locale}`, () =>
    ampApi.listEvents({
      upcoming: true,
      limit,
      locale,
      date: filters.date || undefined,
      area: filters.area || undefined,
      max_price_krw: filters.max_price_krw ?? undefined,
      seating_type: filters.seating_requirement || undefined,
    }),
  );
  function changeFilters(next: SearchFilters) {
    const query = new URLSearchParams();
    if (next.date) query.set('date', next.date);
    if (next.area) query.set('area', next.area);
    if (next.max_price_krw !== null) query.set('max_price_krw', String(next.max_price_krw));
    if (next.seating_requirement) query.set('seating_type', next.seating_requirement);
    setParams(query, { replace: true });
  }
  return (
    <div className="page-width list-page">
      <div className="page-intro">
        <p className="eyebrow">THE LOCAL LINEUP</p>
        <h1>
          {t('작은 무대,', 'Small stages,')}
          <br />
          <span>{t('새로운 발견.', 'new discoveries.')}</span>
        </h1>
        <p>
          {t(
            '신촌과 홍대에서 곧 시작될 공연을 둘러보세요.',
            'Explore upcoming shows in Sinchon and Hongdae.',
          )}
        </p>
        <ArrowUpRight className="intro-arrow" size={68} strokeWidth={1} aria-hidden="true" />
      </div>
      <div className="list-toolbar">
        <div className="chips">
          {(['', 'sinchon', 'hongdae'] as const).map((value) => (
            <button
              key={value}
              type="button"
              className="chip"
              aria-pressed={(filters.area || '') === value}
              onClick={() => changeFilters({ ...filters, area: value || null })}
            >
              {value === ''
                ? t('모든 동네', 'All areas')
                : value === 'sinchon'
                  ? t('신촌', 'Sinchon')
                  : t('홍대', 'Hongdae')}
            </button>
          ))}
        </div>
        <button
          className="text-button"
          type="button"
          aria-expanded={expanded}
          aria-controls="list-filters"
          onClick={() => setExpanded(!expanded)}
        >
          <SlidersHorizontal size={16} />
          {t('상세 필터', 'Filters')}
        </button>
      </div>
      <div id="list-filters" hidden={!expanded}>
        <Filters preferences={false} value={filters} onChange={changeFilters} />
      </div>
      {resource.loading ? (
        <Loading />
      ) : resource.error ? (
        <ErrorState error={resource.error} onRetry={resource.retry} />
      ) : (
        resource.data && (
          <>
            <div className="section-heading result-heading">
              <h2>{t('다가오는 공연', 'Upcoming shows')}</h2>
              <span className="section-caption">
                {t(
                  `총 ${resource.data.total}개 · ${resource.data.items.length}개 표시`,
                  `${resource.data.items.length} of ${resource.data.total} shows`,
                )}
              </span>
            </div>
            {resource.data.items.length > 0 ? (
              <div className="event-grid">
                {resource.data.items.map((event) => (
                  <EventCard key={event.id} event={event} />
                ))}
              </div>
            ) : (
              <EmptyState
                title={t('아직 표시할 공연이 없어요.', 'No shows to display yet.')}
                action={
                  <button
                    className="button secondary small"
                    onClick={() => changeFilters(emptyFilters())}
                  >
                    {t('필터 초기화', 'Reset filters')}
                  </button>
                }
              >
                <p>{t('다른 날짜나 동네로 찾아보세요.', 'Try another date or area.')}</p>
              </EmptyState>
            )}
            {resource.data.total > resource.data.items.length &&
              (limit < 50 ? (
                <button
                  className="button secondary load-more"
                  onClick={() => {
                    const next = new URLSearchParams(params);
                    next.set('limit', '50');
                    setParams(next, { replace: true });
                  }}
                >
                  {t('공연 더 보기', 'Show more')}
                </button>
              ) : (
                <Notice>
                  {t(
                    '최대 50개를 보고 있어요. 날짜나 동네를 선택하면 범위를 좁힐 수 있어요.',
                    'Showing up to 50 shows. Narrow the date or area to explore more precisely.',
                  )}
                </Notice>
              ))}
          </>
        )
      )}
    </div>
  );
}
