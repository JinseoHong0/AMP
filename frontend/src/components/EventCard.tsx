import { useState } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { ArrowUpRight, MapPin, Music2 } from 'lucide-react';
import { useApp } from '../lib/context';
import {
  areaName,
  formatDate,
  mediaUrl,
  moods,
  priceLabel,
  seatingName,
  translatedText,
} from '../lib/format';
import type { EventSummary } from '../types/api';

export function PosterImage({
  url,
  title,
  large = false,
}: {
  url: string | null;
  title: string;
  large?: boolean;
}) {
  const { t } = useApp();
  const [failedUrl, setFailedUrl] = useState<string | null>(null);
  const src = mediaUrl(url);
  return (
    <div className={`poster-image ${large ? 'large' : ''}`}>
      {src && failedUrl !== src ? (
        <img src={src} alt={title} loading="lazy" onError={() => setFailedUrl(src)} />
      ) : (
        <div className="poster-placeholder">
          <Music2 size={large ? 40 : 28} strokeWidth={1.2} />
          <span>{t('포스터 준비 중', 'Poster unavailable')}</span>
          <b aria-hidden="true">AMP.</b>
        </div>
      )}
    </div>
  );
}
export function EventCard({
  event,
  reason,
  index,
}: {
  event: EventSummary;
  reason?: string;
  index?: number;
}) {
  const { locale, t } = useApp();
  const location = useLocation();
  const title = translatedText(event.title, event.title_en, event.translation, locale);
  return (
    <article className="event-card">
      <Link
        className="event-card-link"
        to={`/events/${event.id}`}
        state={{ from: location.pathname + location.search }}
      >
        <PosterImage url={event.poster_url} title={title.text} />
        <div className="event-card-body">
          <div className="card-topline">
            <span>{formatDate(event.starts_at, locale)}</span>
            {event.data_origin === 'demo' && <span className="badge">DEMO</span>}
          </div>
          <h3>
            {index !== undefined && <span className="card-index">0{index + 1}</span>}
            {title.text}
            <ArrowUpRight size={19} />
          </h3>
          {title.automatic && <span className="translation-label">AI-translated</span>}
          {title.missing && (
            <span className="translation-label">English translation unavailable</span>
          )}
          <p className="card-location">
            <MapPin size={13} />
            {areaName(event.venue.area, locale)} · {event.venue.name}
          </p>
          <p className="card-price">{priceLabel(event.price_krw, event.price_basis, locale)}</p>
          <div className="chips">
            <span className="badge muted-badge">{seatingName(event.seating_type, locale)}</span>
            {event.genre && <span className="badge muted-badge">{event.genre}</span>}
            {event.mood_tags.map((mood) => (
              <span className="badge muted-badge" key={mood}>
                {moods[mood]?.[locale === 'ko' ? 0 : 1] || mood}
              </span>
            ))}
          </div>
        </div>
      </Link>
      {reason && (
        <div className="recommendation-reason">
          <span className="eyebrow">{t('이 공연을 추천하는 이유', 'WHY THIS SHOW')}</span>
          <p>{reason}</p>
        </div>
      )}
      {title.automatic && (
        <details className="card-original">
          <summary>{t('원문 보기', 'View original')}</summary>
          <p lang="ko">{event.title}</p>
        </details>
      )}
    </article>
  );
}
