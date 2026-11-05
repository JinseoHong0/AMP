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
  const messages: Record<string, [string, string]> = {
    FILE_TOO_LARGE: [
      '포스터는 최대 5MB까지 업로드할 수 있어요.',
      'Upload a poster no larger than 5MB.',
    ],
    UNSUPPORTED_FILE_TYPE: [
      'JPG, PNG, WebP 이미지를 선택해 주세요.',
      'Choose a JPG, PNG or WebP image.',
    ],
    INVALID_IMAGE: [
      '이미지를 읽을 수 없어요. 정상적인 정지 이미지로 다시 올려주세요.',
      'Upload a valid, undamaged still image.',
    ],
    VENUE_DB_UNAVAILABLE: [
      '공연장 DB가 준비되지 않았어요. 서버 설정을 확인해 주세요.',
      'The venue database is not ready. Check the backend setup.',
    ],
    NETWORK_ERROR: [
      '백엔드에 연결할 수 없어요. 서버 실행 상태를 확인해 주세요.',
      'Cannot reach the backend. Check that the server is running.',
    ],
    REQUEST_TIMEOUT: [
      '추출 시간이 초과됐어요. 재시도하거나 직접 입력해 주세요.',
      'Extraction timed out. Try again or enter information manually.',
    ],
    FORBIDDEN: [
      '현재 포스터 추출 접근이 허용되지 않았어요. 로컬 데모 설정을 확인해 주세요.',
      'Poster extraction is not enabled for this connection. Check local demo settings.',
    ],
    AI_UNAVAILABLE: [
      'AI 추출·추천을 완료하지 못했어요. 잠시 후 재시도하거나 수동 입력·검색을 이용해 주세요.',
      'The AI request failed. Try again later or use manual entry/search.',
    ],
  };
  const specific = error instanceof ApiError ? messages[error.code] : undefined;
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
            : specific
              ? t(...specific)
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
