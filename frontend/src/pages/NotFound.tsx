import { Link } from 'react-router-dom';
import { useApp } from '../lib/context';
import { EmptyState } from '../components/Feedback';

export default function NotFound() {
  const { t } = useApp();
  return (
    <div className="page-width">
      <EmptyState
        title={t('찾고 있는 페이지가 없어요.', 'This page could not be found.')}
        action={
          <Link to="/" className="button primary">
            {t('처음으로', 'Back to home')}
          </Link>
        }
      >
        <p>{t('새로운 공연을 찾으러 가볼까요?', 'Let’s find your next show.')}</p>
      </EmptyState>
    </div>
  );
}
