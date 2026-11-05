import { AlertCircle, ArrowRight, CircleHelp, Music2, RotateCcw } from 'lucide-react';
import type { ReactNode } from 'react';
import { useApp } from '../lib/context';
import { ApiError } from '../api/client';

export function Loading({ message }: { message?: string }) {
  const { t } = useApp();
  return (
    <div className="loading-state" role="status" aria-live="polite">
      <div className="equalizer" aria-hidden="true">
        <i />
        <i />
        <i />
        <i />
      </div>
      <p>{message || t('공연 정보를 불러오고 있어요.', 'Loading show information.')}</p>
    </div>
  );
}
export function EmptyState({
  title,
  children,
  action,
}: {
  title: string;
  children?: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="empty-state">
      <span className="state-icon">
        <Music2 size={25} />
      </span>
      <h2>{title}</h2>
      <div className="muted">{children}</div>
      {action}
    </div>
  );
}
export function ErrorState({
  error,
  onRetry,
  compact = false,
}: {
  error: unknown;
  onRetry?: () => void;
  compact?: boolean;
}) {
  const { t } = useApp();
  const missing = error instanceof ApiError && error.status === 404;
  const ai = error instanceof ApiError && error.code === 'AI_UNAVAILABLE';
  return (
    <div className={`error-state ${compact ? 'compact' : ''}`} role="alert">
      <AlertCircle size={22} />
      <div>
        <h2>
          {missing
            ? t('공연 정보를 찾을 수 없어요.', 'This show could not be found.')
            : ai
              ? t('AI 요청을 완료하지 못했어요.', 'The AI request could not be completed.')
              : t('지금은 정보를 불러올 수 없어요.', 'Information is temporarily unavailable.')}
        </h2>
        <p>
          {missing
            ? t('공연 목록에서 다른 무대를 만나보세요.', 'Explore another show in the listings.')
            : t(
                '입력한 내용은 유지됩니다. 잠시 후 다시 시도해 주세요.',
                'Your input is kept. Please try again in a moment.',
              )}
        </p>
        {onRetry && !missing && (
          <button className="button small secondary" type="button" onClick={onRetry}>
            <RotateCcw size={14} />
            {t('다시 시도', 'Try again')}
          </button>
        )}
      </div>
    </div>
  );
}
export function Notice({ children }: { children: ReactNode }) {
  return (
    <div className="notice" role="status">
      <CircleHelp size={17} />
      <div>{children}</div>
    </div>
  );
}
export function TextLink({ children }: { children: ReactNode }) {
  return (
    <>
      {children}
      <ArrowRight size={16} aria-hidden="true" />
    </>
  );
}
