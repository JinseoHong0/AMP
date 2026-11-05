import { useEffect, useRef, useState, type FormEvent } from 'react';
import { Link } from 'react-router-dom';
import {
  ArrowDown,
  ArrowRight,
  ArrowUpRight,
  Search,
  SlidersHorizontal,
  Sparkles,
} from 'lucide-react';
import { ampApi } from '../api/client';
import { useApp } from '../lib/context';
import { hasFilters } from '../lib/format';
import { Filters } from '../components/Filters';
import { EventCard } from '../components/EventCard';
import { AppliedConditions } from '../components/AppliedConditions';
import { EmptyState, ErrorState, Loading, Notice } from '../components/Feedback';

export default function Home() {
  const { locale, t, search, setSearch } = useApp();
  const [openFilters, setOpenFilters] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const input = useRef<HTMLTextAreaElement>(null);
  const sequence = useRef(0);
  useEffect(() => {
    setError(null);
    setLoading(false);
    return () => {
      sequence.current++;
    };
  }, [locale]);
  const valid = search.query.trim().length > 0 || hasFilters(search.filters);
  const result = search.resultLocale === locale ? search.result : null;
  async function submit(event?: FormEvent) {
    event?.preventDefault();
    if (!valid || loading) return;
    const request = ++sequence.current;
    setLoading(true);
    setError(null);
    setSearch((previous) => ({ ...previous, result: null }));
    try {
      // BACKEND_TODO: This boundary sends raw natural language; never parse/rank in the browser.
      const response = await ampApi.recommend({
        query: search.query.trim(),
        filters: search.filters,
        locale,
      });
      if (request === sequence.current)
        setSearch((previous) => ({ ...previous, result: response, resultLocale: locale }));
    } catch (failure) {
      if (request === sequence.current) setError(failure);
    } finally {
      if (request === sequence.current) setLoading(false);
    }
  }
  const examples =
    locale === 'ko'
      ? ['오늘 홍대에서 2만 원 이하, 좌석 공연만', '내일 신촌에서 혼자 듣기 좋은 잔잔한 공연']
      : [
          'Seated shows in Hongdae today, under ₩20,000',
          'A calm show for a solo visit in Sinchon tomorrow',
        ];
  return (
    <div className="home-page page-width">
      <section className="hero-section">
        <div className="hero-copy">
          <p className="eyebrow">
            <span className="tiny-dot" />
            SEOUL, SMALL STAGES. BIG FEELINGS.
          </p>
          <h1>
            {t('오늘의 나에게,', 'Your kind of night.')}
            <br />
            <span>{t('딱 맞는 무대.', 'Your kind of stage.')}</span>
          </h1>
          <p className="hero-description">
            {t(
              '신촌과 홍대의 작은 공연부터 시작해 보세요.',
              'Start with the small stages of Sinchon and Hongdae.',
            )}
            <br />
            {t(
              '취향을 말하면, 나에게 맞는 공연을 함께 찾아요.',
              'Tell us what you like. Discover a show that feels like you.',
            )}
          </p>
          <a href="#search" className="hero-jump">
            {t('나의 공연 찾기', 'Find my show')}
            <ArrowDown size={16} />
          </a>
        </div>
        <div className="brand-art" aria-hidden="true">
          <div className="art-caption">
            <span>LOCAL TO GLOBAL</span>
            <ArrowUpRight size={24} />
          </div>
          <div className="vinyl">
            <div className="vinyl-center">
              amp<span>SEOUL / LIVE</span>
            </div>
          </div>
          <div className="art-bottom">
            <span>
              SMALL STAGE.
              <br />
              LOUD HEART.
            </span>
            <span className="art-star">✳</span>
          </div>
        </div>
      </section>
      <section id="search" className="search-section" aria-labelledby="search-heading">
        <div className="section-heading">
          <div>
            <p className="eyebrow">01 / DISCOVER</p>
            <h2 id="search-heading">
              {t('어떤 공연을 찾고 있나요?', 'What are you in the mood for?')}
            </h2>
          </div>
          <span className="section-caption">
            {t('나의 조건으로, 최대 3개의 추천', 'Up to 3 picks, on your terms')}
          </span>
        </div>
        <form onSubmit={submit} className="search-form">
          <div className="search-box">
            <Search size={23} aria-hidden="true" />
            <div className="search-input-wrap">
              <label className="sr-only" htmlFor="show-query">
                {t('원하는 공연 설명', 'Describe your ideal show')}
              </label>
              <textarea
                id="show-query"
                ref={input}
                rows={2}
                maxLength={500}
                value={search.query}
                disabled={loading}
                placeholder={t(
                  '날짜, 동네, 예산, 좋아하는 분위기를 편하게 적어 주세요.',
                  'Tell us the date, area, budget, and music you love.',
                )}
                onChange={(e) =>
                  setSearch((previous) => ({ ...previous, query: e.target.value, result: null }))
                }
              />
              <span className="character-count">{search.query.length} / 500</span>
            </div>
            <button className="button primary search-submit" disabled={!valid || loading}>
              <span>{loading ? t('찾는 중', 'Finding') : t('공연 추천받기', 'Find my show')}</span>
              <ArrowUpRight size={19} />
            </button>
          </div>
          <div className="search-tools">
            <button
              type="button"
              className="text-button"
              aria-expanded={openFilters}
              aria-controls="search-filters"
              onClick={() => setOpenFilters(!openFilters)}
            >
              <SlidersHorizontal size={15} />
              {t('직접 조건 선택', 'Choose filters')}
              {hasFilters(search.filters) && <span className="tiny-dot" />}
            </button>
            <span>
              {t(
                '입력한 필터가 문장 속 조건보다 우선해요.',
                'Your selected filters take priority.',
              )}
            </span>
          </div>
          <div id="search-filters" hidden={!openFilters}>
            <Filters
              value={search.filters}
              disabled={loading}
              onChange={(filters) =>
                setSearch((previous) => ({ ...previous, filters, result: null }))
              }
            />
          </div>
        </form>
        {!result && !loading && !error && (
          <div className="example-queries">
            <span>{t('이렇게 물어보세요', 'TRY ASKING')}</span>
            {examples.map((example) => (
              <button
                type="button"
                key={example}
                onClick={() => {
                  setSearch((previous) => ({ ...previous, query: example, result: null }));
                  input.current?.focus();
                }}
              >
                {example}
                <ArrowUpRight size={14} />
              </button>
            ))}
          </div>
        )}
        <div className="search-results" aria-live="polite" aria-busy={loading}>
          {loading && (
            <Loading
              message={t(
                '조건에 맞는 공연을 살펴보고 있어요.',
                'Exploring shows that fit your request.',
              )}
            />
          )}
          {!!error && (
            <>
              <ErrorState error={error} onRetry={() => void submit()} />
              <p className="helper-text">
                {t(
                  '문장을 지우고 직접 필터만 선택해 다시 검색할 수도 있어요.',
                  'You can also clear the text and search using only your selected filters.',
                )}
              </p>
            </>
          )}
          {search.result && search.resultLocale !== locale && (
            <Notice>
              {t(
                '한국어 추천 이유를 보려면 다시 검색해 주세요.',
                'Search again to receive recommendation reasons in English.',
              )}
            </Notice>
          )}
          {result && (
            <>
              <AppliedConditions condition={result.applied_conditions} />
              {result.preferences.length > 0 && (
                <div className="chips preference-summary">
                  {result.preferences.map((preference, index) => (
                    <span className="badge muted-badge" key={index}>
                      {preference}
                    </span>
                  ))}
                </div>
              )}
              {result.notice && <Notice>{result.notice}</Notice>}
              {result.search_limited && (
                <Notice>
                  {t(
                    '모든 후보를 살펴보지는 못했어요. 현재 확인한 범위의 결과입니다.',
                    'These results cover the shows explored so far, not every matching candidate.',
                  )}
                </Notice>
              )}
              {result.used_fallback && (
                <p className="helper-text">
                  {t(
                    '일부 추천 안내는 확인된 정보에 기반한 기본 방식으로 제공됩니다.',
                    'Some recommendation guidance uses a fallback based on confirmed information.',
                  )}
                </p>
              )}
              {result.status === 'needs_clarification' ? (
                <div className="clarification">
                  <Sparkles size={22} />
                  <h3>{t('조금만 더 알려주세요.', 'Tell us a little more.')}</h3>
                  <p>{result.clarification}</p>
                  <button className="button secondary small" onClick={() => input.current?.focus()}>
                    {t('검색 조건 수정하기', 'Refine my request')}
                  </button>
                </div>
              ) : result.items.length ? (
                <>
                  <div className="section-heading result-heading">
                    <h2>
                      {t('당신을 위한', 'Picked for you:')} {Math.min(result.items.length, 3)}
                      {t('개의 무대', ' shows')}
                    </h2>
                    {result.total_matches !== null && (
                      <span className="section-caption">
                        {t(
                          `필수 조건에 맞는 공연 ${result.total_matches}개`,
                          `${result.total_matches} shows match your requirements`,
                        )}
                      </span>
                    )}
                  </div>
                  <div className="event-grid">
                    {result.items.slice(0, 3).map((item, index) => (
                      <EventCard
                        event={item.event}
                        reason={item.reason}
                        index={index}
                        key={item.event.id}
                      />
                    ))}
                  </div>
                </>
              ) : (
                <EmptyState
                  title={
                    result.total_matches === 0
                      ? t('조건에 맞는 공연이 아직 없어요.', 'No shows match these requirements.')
                      : t('추천할 공연을 아직 고르지 못했어요.', 'No recommendation is ready yet.')
                  }
                  action={
                    <Link className="button secondary small" to="/events">
                      {t('공연 둘러보기', 'Browse shows')}
                      <ArrowRight size={15} />
                    </Link>
                  }
                >
                  <p>
                    {t(
                      '날짜나 조건을 바꾸거나, 등록된 공연을 직접 둘러보세요.',
                      'Try another date or explore the listings yourself.',
                    )}
                  </p>
                </EmptyState>
              )}
            </>
          )}
        </div>
      </section>
      <section className="browse-banner">
        <div>
          <p className="eyebrow">NO PLANS? JUST EXPLORE.</p>
          <h2>{t('우연히 만나는 음악도 좋으니까.', 'Leave room for a little discovery.')}</h2>
          <p>
            {t(
              '검색 없이, 등록된 공연을 천천히 둘러보세요.',
              'Browse the stages. Find something unexpected.',
            )}
          </p>
        </div>
        <Link to="/events" className="button secondary">
          {t('모든 공연 둘러보기', 'Explore all shows')}
          <ArrowUpRight size={18} />
        </Link>
      </section>
      <section className="journey" aria-label={t('AMP 이용 방법', 'How AMP works')}>
        {[
          [
            '01',
            'DISCOVER',
            t('나의 취향으로 발견하기', 'Find your kind of music'),
            t('날짜와 예산, 취향을 편하게 이야기해요.', 'Start with your date, budget, and mood.'),
          ],
          [
            '02',
            'DECIDE',
            t('이유를 알고 선택하기', 'Choose with confidence'),
            t(
              '실제 공연 정보에 근거한 추천을 살펴봐요.',
              'See recommendations grounded in show details.',
            ),
          ],
          [
            '03',
            'VISIT',
            t('처음 가는 무대도 편하게', 'Arrive a little more ready'),
            t('입장 시간부터 현장 안내까지 확인해요.', 'Check entry times and venue guidance.'),
          ],
        ].map(([number, label, title, body]) => (
          <div key={number}>
            <span className="journey-number">{number}</span>
            <p className="eyebrow">{label}</p>
            <h3>{title}</h3>
            <p>{body}</p>
          </div>
        ))}
      </section>
    </div>
  );
}
