import { useState } from 'react';
import { Link, useLocation, useParams } from 'react-router-dom';
import { ArrowLeft, ArrowUpRight, Clock3, Languages, MapPin, Ticket } from 'lucide-react';
import { ampApi } from '../api/client';
import { useApp } from '../lib/context';
import { areaName, formatDate, money, safeLink, seatingName, translatedText } from '../lib/format';
import { useResource } from '../lib/useResource';
import { PosterImage } from '../components/EventCard';
import { EmptyState, ErrorState, Loading, Notice } from '../components/Feedback';
import type { EventDetail as EventData } from '../types/api';

function VenueGuide({ event }: { event: EventData }) {
  const { locale, t } = useApp();
  const resource = useResource(`venue:${event.venue_id}:${locale}`, () =>
    ampApi.getVenue(event.venue_id, locale),
  );
  const venue = resource.data;
  if (resource.loading) return <Loading />;
  if (resource.error) return <ErrorState error={resource.error} onRetry={resource.retry} />;
  if (!venue) return null;
  const hint =
    locale === 'en' ? venue.entrance_hint_en || venue.entrance_hint_ko : venue.entrance_hint_ko;
  const story =
    locale === 'en' ? venue.description_en || venue.description_ko : venue.description_ko;
  return (
    <section className="venue-guide" aria-labelledby="venue-heading">
      <div className="section-heading">
        <div>
          <p className="eyebrow">THE SPACE BEHIND THE SOUND</p>
          <h2 id="venue-heading">{venue.name}</h2>
        </div>
        <span className="badge">{areaName(venue.area, locale)}</span>
      </div>
      <p className="venue-address">
        <MapPin size={17} />
        {venue.address}
      </p>
      <div className="venue-grid">
        <div>
          <PosterImage
            url={venue.entrance_image_url}
            title={t(`${venue.name} 입구`, `Entrance to ${venue.name}`)}
            large
          />
          <p className="helper-text">{t('입구 사진', 'Entrance photo')}</p>
        </div>
        <div className="information-panel">
          <dl className="info-list">
            <div>
              <dt>{t('건물 층수', 'Floor')}</dt>
              <dd>{venue.floor || t('확인 필요', 'Not confirmed')}</dd>
            </div>
            <div>
              <dt>{t('입구·동선', 'Getting inside')}</dt>
              <dd>
                {hint || t('확인 필요', 'Not confirmed')}
                {locale === 'en' && !venue.entrance_hint_en && venue.entrance_hint_ko && (
                  <small>English guidance unavailable · original shown</small>
                )}
              </dd>
            </div>
            {!event.seating_type && venue.default_seating_type && (
              <div>
                <dt>{t('기본 관람 방식', 'Typical seating')}</dt>
                <dd>
                  {seatingName(venue.default_seating_type, locale)}
                  <small>
                    {t(
                      '공연장 기본 정보 · 이 공연은 확인 필요',
                      'Venue default · not confirmed for this show',
                    )}
                  </small>
                </dd>
              </div>
            )}
            {!event.drink_policy && venue.default_drink_policy && (
              <div>
                <dt>{t('기본 드링크 안내', 'Typical drink policy')}</dt>
                <dd>
                  {venue.default_drink_policy}
                  <small>
                    {t(
                      '공연장 기본 정보 · 이 공연은 확인 필요',
                      'Venue default · not confirmed for this show',
                    )}
                  </small>
                </dd>
              </div>
            )}
          </dl>
          {story && (
            <div className="venue-story">
              <h3>{t('이 공간의 이야기', 'About this space')}</h3>
              <p>{story}</p>
              {locale === 'en' && !venue.description_en && (
                <small>Original description · English unavailable</small>
              )}
            </div>
          )}
        </div>
      </div>
      <div className="source-line">
        {venue.data_origin === 'demo' && <span className="badge">DEMO</span>}
        <span>
          {t('공연장 정보 확인', 'Venue information checked')}:{' '}
          {formatDate(venue.verified_at, locale)}
        </span>
        {safeLink(venue.source_url) && (
          <a href={safeLink(venue.source_url)} target="_blank" rel="noopener noreferrer">
            {t('출처 보기', 'View source')}
            <ArrowUpRight size={13} />
          </a>
        )}
      </div>
    </section>
  );
}

export default function EventDetail() {
  const { id } = useParams();
  const validId = !!id && /^\d+$/.test(id) && Number.isSafeInteger(Number(id)) && Number(id) > 0;
  return validId ? (
    <LoadedDetail id={Number(id)} />
  ) : (
    <div className="page-width">
      <EmptyState
        title="404"
        action={
          <Link to="/events" className="button secondary">
            공연 둘러보기 / All shows
          </Link>
        }
      />
    </div>
  );
}
function LoadedDetail({ id }: { id: number }) {
  const { locale, t } = useApp();
  const location = useLocation();
  const from = location.state?.from;
  const back =
    typeof from === 'string' && (from === '/' || from === '/events' || from.startsWith('/events?'))
      ? from
      : '/events';
  const [original, setOriginal] = useState(false);
  const resource = useResource(`event:${id}:${locale}`, () => ampApi.getEvent(id, locale));
  const event = resource.data;
  function text(ko: string | null | undefined, en: string | null | undefined) {
    const content = translatedText(ko, en, event?.translation, locale, original);
    return (
      <>
        {content.text}
        {content.missing && (
          <small className="translation-label">
            English translation unavailable · original shown
          </small>
        )}
      </>
    );
  }
  return (
    <div className="page-width detail-page">
      <Link to={back} className="back-link">
        <ArrowLeft size={17} />
        {t('공연 탐색으로', 'Back to discovery')}
      </Link>
      {resource.loading ? (
        <Loading />
      ) : resource.error ? (
        <ErrorState error={resource.error} onRetry={resource.retry} />
      ) : (
        event && (
          <>
            <div className="detail-hero">
              <PosterImage url={event.poster_url} title={event.title} large />
              <div className="detail-intro">
                <p className="eyebrow">A NIGHT TO REMEMBER</p>
                <div className="chips">
                  {event.data_origin === 'demo' && <span className="badge">DEMO</span>}
                  {event.genre && <span className="badge muted-badge">{event.genre}</span>}
                </div>
                <h1>{text(event.title, event.title_en)}</h1>
                <p className="detail-date">
                  {formatDate(event.starts_at, locale)} <span>KST</span>
                </p>
                <p className="lineup">
                  {event.lineup.length
                    ? event.lineup.join(' · ')
                    : t('출연진 확인 필요', 'Lineup not confirmed')}
                </p>
                {locale === 'en' && (
                  <div className="translation-controls">
                    <Languages size={15} />
                    <span>
                      {event.translation?.status === 'generated'
                        ? 'AI-translated'
                        : event.translation?.status === 'reviewed'
                          ? 'Reviewed translation'
                          : 'English translation unavailable'}
                    </span>
                    {(event.translation?.status === 'generated' ||
                      event.translation?.status === 'reviewed') && (
                      <button
                        type="button"
                        className="text-button"
                        aria-pressed={original}
                        onClick={() => setOriginal(!original)}
                      >
                        {original ? 'Show English' : 'View original'}
                      </button>
                    )}
                  </div>
                )}
                {event.description_ko && (
                  <p className="detail-description">
                    {text(event.description_ko, event.description_en)}
                  </p>
                )}
                {safeLink(event.booking_url) && (
                  <>
                    <a
                      className="button primary"
                      href={safeLink(event.booking_url)}
                      target="_blank"
                      rel="noopener noreferrer"
                    >
                      {t('예매처 확인하기', 'Visit ticket provider')}
                      <ArrowUpRight size={17} />
                    </a>
                    <p className="helper-text">
                      {t(
                        '예매 가능 여부와 최종 가격은 예매처에서 확인해 주세요.',
                        'Check ticket availability and final prices with the provider.',
                      )}
                    </p>
                  </>
                )}
              </div>
            </div>
            <section className="visit-section" aria-labelledby="visit-heading">
              <div className="section-heading">
                <div>
                  <p className="eyebrow">BEFORE YOU GO</p>
                  <h2 id="visit-heading">{t('방문 준비 카드', 'Your visit, at a glance')}</h2>
                </div>
                <span className="section-caption">
                  {t('이 공연의 정보', 'Information for this show')}
                </span>
              </div>
              <div className="visit-grid">
                <div className="visit-tile">
                  <Clock3 size={20} />
                  <span>{t('입장 시작', 'Doors open')}</span>
                  <strong>{formatDate(event.doors_open_at, locale, true)}</strong>
                  <small>
                    {t('공연 시작', 'Show starts')} {formatDate(event.starts_at, locale, true)} ·
                    KST
                  </small>
                </div>
                <div className="visit-tile">
                  <Ticket size={20} />
                  <span>{t('티켓 가격', 'Ticket prices')}</span>
                  <strong>{money(event.price_krw, locale)}</strong>
                  <small>
                    {event.price_basis === 'advance'
                      ? t('예매 가격 기준', 'Advance price')
                      : event.price_basis === 'door'
                        ? t('현장 가격 기준', 'Door price')
                        : t('안내 가격 기준', 'Listed price')}
                  </small>
                </div>
                <div className="visit-tile">
                  <span className="tile-number" aria-hidden="true">
                    ↗
                  </span>
                  <span>{t('관람 방식', 'Seating')}</span>
                  <strong>{seatingName(event.seating_type, locale)}</strong>
                  <small>
                    {event.seat_assignment === 'assigned'
                      ? t('지정석', 'Assigned seating')
                      : event.seat_assignment === 'unassigned'
                        ? t('비지정석', 'Unassigned seating')
                        : t('좌석 배정 확인 필요', 'Seat assignment not confirmed')}
                  </small>
                </div>
              </div>
              <dl className="info-list visit-details">
                <div>
                  <dt>{t('예매가 / 현장가', 'Advance / door')}</dt>
                  <dd>
                    {money(event.advance_price_krw, locale)} / {money(event.door_price_krw, locale)}
                  </dd>
                </div>
                <div>
                  <dt>{t('드링크 정책', 'Drink policy')}</dt>
                  <dd>{text(event.drink_policy, event.drink_policy_en)}</dd>
                </div>
                <div>
                  <dt>{t('입장·관람 안내', 'Entry & show guidance')}</dt>
                  <dd>{text(event.admission_notes_ko, event.admission_notes_en)}</dd>
                </div>
              </dl>
              {!event.doors_open_at && (
                <Notice>
                  {t(
                    '입장 시작 시각이 확인되지 않았어요. 방문 전 공연장에 확인해 주세요.',
                    'Door time has not been confirmed. Check with the venue before visiting.',
                  )}
                </Notice>
              )}
            </section>
            <VenueGuide event={event} />
            <div className="source-line">
              <span>
                {t('공연 정보 확인', 'Show information checked')}:{' '}
                {formatDate(event.verified_at, locale)}
              </span>
              {safeLink(event.source_url) && (
                <a href={safeLink(event.source_url)} target="_blank" rel="noopener noreferrer">
                  {t('공연 정보 출처', 'Show source')}
                  <ArrowUpRight size={13} />
                </a>
              )}
            </div>
          </>
        )
      )}
    </div>
  );
}
