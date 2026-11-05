import { useDeferredValue, useEffect, useRef, useState, type FormEvent } from 'react';
import { Link } from 'react-router-dom';
import {
  ArrowLeft,
  ArrowRight,
  CheckCircle2,
  FileImage,
  Languages,
  LoaderCircle,
  UploadCloud,
  X,
} from 'lucide-react';
import { ampApi } from '../api/client';
import { useApp } from '../lib/context';
import { useResource } from '../lib/useResource';
import {
  emptyRegistration,
  fromExtraction,
  registrationPayload,
  validatePoster,
  validateRegistration,
  type RegistrationErrors,
} from '../lib/registration';
import { ReviewForm } from '../components/ReviewForm';
import { ErrorState, Notice } from '../components/Feedback';
import type { CreatedEvent, PosterExtraction, VenueSummary } from '../types/api';

export default function Register() {
  const { t } = useApp();
  const [step, setStep] = useState<'upload' | 'review' | 'done'>('upload');
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState('');
  const [fileError, setFileError] = useState<'type' | 'size' | 'content' | null>(null);
  const [checking, setChecking] = useState(false);
  const [extracting, setExtracting] = useState(false);
  const [extraction, setExtraction] = useState<PosterExtraction | null>(null);
  const [parseError, setParseError] = useState<unknown>(null);
  const [form, setForm] = useState(emptyRegistration);
  const [errors, setErrors] = useState<RegistrationErrors>({});
  const [posting, setPosting] = useState(false);
  const [postError, setPostError] = useState<unknown>(null);
  const [saved, setSaved] = useState<CreatedEvent | null>(null);
  const [translating, setTranslating] = useState(false);
  const [translationError, setTranslationError] = useState<unknown>(null);
  const [venueQuery, setVenueQuery] = useState('');
  const [selectedVenue, setSelectedVenue] = useState<VenueSummary | null>(null);
  const query = useDeferredValue(venueQuery);
  const venues = useResource(`venues:${query}`, () => ampApi.listVenues(query));
  const version = useRef(0);
  const alive = useRef(true);
  const submitLock = useRef(false);
  useEffect(() => {
    alive.current = true;
    return () => {
      alive.current = false;
      version.current++;
    };
  }, []);
  useEffect(() => {
    if (!file) {
      setPreview('');
      return;
    }
    const url = URL.createObjectURL(file);
    setPreview(url);
    return () => URL.revokeObjectURL(url);
  }, [file]);
  const options = [
    ...new Map(
      [
        ...(extraction?.venue_match.candidates || []),
        ...(venues.data?.items || []),
        ...(selectedVenue ? [selectedVenue] : []),
      ].map((venue) => [venue.id, venue]),
    ).values(),
  ];
  async function chooseFile(next: File | undefined) {
    if (!next) return;
    const request = ++version.current;
    setChecking(true);
    setFileError(null);
    setParseError(null);
    setExtraction(null);
    setFile(null);
    setExtracting(false);
    setForm((previous) => ({ ...previous, review_confirmed: false }));
    try {
      const problem = await validatePoster(next);
      if (version.current !== request) return;
      if (problem) setFileError(problem);
      else setFile(next);
    } catch {
      if (version.current === request) setFileError('content');
    } finally {
      if (version.current === request) setChecking(false);
    }
  }
  async function extract() {
    if (!file || extracting || checking) return;
    const request = ++version.current;
    setExtracting(true);
    setParseError(null);
    try {
      const result = await ampApi.parsePoster(file);
      if (version.current !== request) return;
      setExtraction(result);
      setForm(fromExtraction(result));
      setErrors({});
      setPostError(null);
      setStep('review');
    } catch (error) {
      if (version.current === request) setParseError(error);
    } finally {
      if (version.current === request) setExtracting(false);
    }
  }
  function manual() {
    version.current++;
    setExtracting(false);
    setStep('review');
    // A failed parse has no upload_id. Keep manual entry available without pretending to save the image.
  }
  async function submit(event: FormEvent) {
    event.preventDefault();
    if (submitLock.current) return;
    const validation = validateRegistration(form, t);
    setErrors(validation);
    setPostError(null);
    if (Object.keys(validation).length) {
      document.getElementById(`form-${Object.keys(validation)[0]}`)?.focus();
      return;
    }
    submitLock.current = true;
    setPosting(true);
    try {
      const result = await ampApi.createEvent(
        registrationPayload(form, extraction?.upload_id || null),
      );
      if (!alive.current) return;
      setSaved(result);
      setStep('done');
      setExtraction(null);
      // HTTP 201 means saved even if translation.status === 'failed'. Do not submit twice.
      window.scrollTo({ top: 0, behavior: 'smooth' });
    } catch (error) {
      if (alive.current) setPostError(error);
    } finally {
      submitLock.current = false;
      if (alive.current) setPosting(false);
    }
  }
  async function retryTranslation() {
    if (!saved || translating) return;
    setTranslating(true);
    setTranslationError(null);
    try {
      const result = await ampApi.retryTranslation(saved.id);
      if (alive.current)
        setSaved((previous) =>
          previous ? { ...previous, translation: result.translation, warnings: [] } : null,
        );
    } catch (error) {
      if (alive.current) setTranslationError(error);
    } finally {
      if (alive.current) setTranslating(false);
    }
  }
  return (
    <div className="page-width register-page">
      <div className="register-heading">
        <p className="eyebrow">FOR THE PEOPLE ON STAGE</p>
        <h1>
          {t('당신의 무대를,', 'Your stage,')}
          <br />
          <span>{t('더 많은 사람에게.', 'a little louder.')}</span>
        </h1>
        <p>
          {t(
            '포스터 한 장으로 시작해, 공연의 이야기를 전해 보세요.',
            'Start with a poster. Share the story of your show.',
          )}
        </p>
      </div>
      <ol className="stepper" aria-label={t('등록 단계', 'Registration steps')}>
        {[t('포스터 업로드', 'Upload'), t('원문 확인', 'Review'), t('등록 완료', 'Publish')].map(
          (label, index) => (
            <li
              key={label}
              className={index === ['upload', 'review', 'done'].indexOf(step) ? 'current' : ''}
              aria-current={
                index === ['upload', 'review', 'done'].indexOf(step) ? 'step' : undefined
              }
            >
              <span>{String(index + 1).padStart(2, '0')}</span>
              {label}
            </li>
          ),
        )}
      </ol>
      {step === 'upload' && (
        <div className="upload-layout">
          <section className="upload-panel">
            <h2>{t('공연 포스터를 올려주세요.', 'Add your show poster.')}</h2>
            <p className="muted">
              {t(
                '읽어낸 정보는 다음 단계에서 직접 확인하고 수정할 수 있어요.',
                'You can review and edit the extracted information in the next step.',
              )}
            </p>
            <label
              className={`upload-drop ${file ? 'has-file' : ''}`}
              onDragOver={(e) => e.preventDefault()}
              onDrop={(e) => {
                e.preventDefault();
                if (!extracting && !checking) void chooseFile(e.dataTransfer.files[0]);
              }}
            >
              <input
                type="file"
                className="sr-only"
                accept="image/jpeg,image/png,image/webp"
                disabled={extracting || checking}
                aria-label={t('포스터 이미지 선택', 'Choose poster image')}
                onChange={(e) => {
                  void chooseFile(e.target.files?.[0]);
                  e.currentTarget.value = '';
                }}
              />
              {preview ? (
                <img src={preview} alt={t('선택한 포스터 미리보기', 'Selected poster preview')} />
              ) : (
                <>
                  <span className="upload-icon">
                    <UploadCloud size={33} strokeWidth={1.5} />
                  </span>
                  <strong>
                    {checking
                      ? t('이미지 확인 중…', 'Checking image…')
                      : t('클릭하거나 이미지를 끌어 놓으세요', 'Choose an image or drop it here')}
                  </strong>
                  <span>JPG · PNG · WebP / {t('최대 5MB', 'up to 5MB')}</span>
                </>
              )}
            </label>
            {file && (
              <div className="selected-file">
                <FileImage size={17} />
                <span>
                  {file.name}
                  <small>{(file.size / 1024 / 1024).toFixed(2)} MB</small>
                </span>
                <button
                  className="icon-button"
                  type="button"
                  disabled={extracting}
                  aria-label={t('선택한 포스터 제거', 'Remove selected poster')}
                  onClick={() => {
                    version.current++;
                    setFile(null);
                    setExtraction(null);
                    setParseError(null);
                  }}
                >
                  <X size={17} />
                </button>
              </div>
            )}
            {fileError && (
              <p className="field-error" role="alert">
                {fileError === 'size'
                  ? t('5MB 이하 이미지를 선택해 주세요.', 'Choose an image no larger than 5MB.')
                  : fileError === 'type'
                    ? t(
                        'JPG, PNG, WebP 이미지만 사용할 수 있어요.',
                        'Choose a JPG, PNG, or WebP image.',
                      )
                    : t(
                        '올바른 이미지 파일을 읽을 수 없어요. 다른 파일을 선택해 주세요.',
                        'This image cannot be decoded. Choose another file.',
                      )}
              </p>
            )}
            {!!parseError && <ErrorState error={parseError} onRetry={() => void extract()} />}
            <button
              type="button"
              className="button primary full"
              disabled={!file || checking || extracting}
              onClick={() => void extract()}
            >
              {extracting && <LoaderCircle className="spin" size={17} />}
              {extracting
                ? t('포스터 정보를 읽고 있어요…', 'Reading your poster…')
                : t('포스터에서 정보 가져오기', 'Extract poster information')}
              <ArrowRight size={17} />
            </button>
            <button
              type="button"
              className="button text full"
              disabled={checking || extracting}
              onClick={manual}
            >
              {t('포스터 없이 직접 입력하기', 'Enter information manually')}
            </button>
          </section>
          <aside className="upload-aside">
            <span className="aside-number">
              A<br />M<br />
              P.
            </span>
            <div>
              <p className="eyebrow">SMALL INPUT. BIG AMPLITUDE.</p>
              <h2>
                {t('등록은 간단하게.', 'Keep it simple.')}
                <br />
                {t('이야기는 더 멀리.', 'Let it travel further.')}
              </h2>
              <p>
                {t(
                  '공연명, 날짜, 가격, 출연진을 확인해 주세요. 영어 안내는 원문 등록과 함께 자동으로 준비돼요.',
                  'Check the title, date, prices, and lineup. English guidance is generated when you register the original information.',
                )}
              </p>
            </div>
          </aside>
        </div>
      )}
      {step === 'review' && (
        <form onSubmit={submit} noValidate className="review-form">
          <button
            className="back-link"
            type="button"
            disabled={posting}
            onClick={() => setStep('upload')}
          >
            <ArrowLeft size={16} />
            {t('포스터 단계로', 'Back to poster')}
          </button>
          {extraction && (
            <div className="extraction-summary">
              <span className="badge">{t('추출된 원문', 'EXTRACTED ORIGINAL')}</span>
              <p>
                {t('공연장 읽기 결과', 'Detected venue')}:{' '}
                {extraction.extracted.venue_name || t('확인 필요', 'Not confirmed')}
              </p>
              <p>
                {extraction.venue_match.status === 'matched'
                  ? t(
                      '기존 공연장을 찾았어요. 선택된 장소를 확인해 주세요.',
                      'An existing venue matched. Please confirm the selection.',
                    )
                  : t(
                      '공연장을 자동으로 확정하지 못했어요. 아래 목록에서 직접 선택해 주세요.',
                      'The venue could not be confirmed automatically. Select one below.',
                    )}
              </p>
              {extraction.warnings.map((warning, index) => (
                <Notice key={index}>{warning}</Notice>
              ))}
            </div>
          )}
          {!extraction && file && (
            <Notice>
              {t(
                '이미지 추출이 완료되지 않아 포스터 없이 수동 등록됩니다.',
                'The image was not parsed. Manual registration will not attach this poster.',
              )}
            </Notice>
          )}
          <fieldset disabled={posting} className="review-fields">
            <legend className="sr-only">
              {t('공연 원문 확인', 'Review original show information')}
            </legend>
            <ReviewForm
              value={form}
              onChange={(next) => {
                setForm(next);
                setErrors({});
                setPostError(null);
                const venue = options.find((item) => String(item.id) === next.venue_id);
                if (venue) setSelectedVenue(venue);
              }}
              errors={errors}
              needsReview={extraction?.needs_review || []}
              venues={options}
              venueLoading={venues.loading}
              venueError={venues.error}
              onVenueRetry={venues.retry}
              venueQuery={venueQuery}
              onVenueQuery={setVenueQuery}
            />
          </fieldset>
          {!!postError && <ErrorState error={postError} />}
          <div className="registration-submit">
            <p>
              {t(
                '원문을 저장하고 영어 안내를 자동으로 생성합니다.',
                'Save the original and automatically generate English guidance.',
              )}
            </p>
            <button className="button primary" disabled={posting}>
              {posting && <LoaderCircle className="spin" size={17} />}
              {posting
                ? t('공연 등록·영문 준비 중…', 'Saving & preparing English…')
                : t('원문 확인 후 공연 등록', 'Confirm & register show')}
              <ArrowUpRightIcon />
            </button>
          </div>
        </form>
      )}
      {step === 'done' && saved && (
        <section className="registration-success">
          <CheckCircle2 size={44} strokeWidth={1.4} />
          <p className="eyebrow">YOUR STAGE IS READY</p>
          <h2>{t('공연이 등록되었어요.', 'Your show is registered.')}</h2>
          <p>
            {t(
              '공연 목록에서 확인할 수 있어요. 추천 조건에 맞으면 검색 결과에도 포함됩니다.',
              'Find it in the listings. It can appear in recommendations when it matches the requirements.',
            )}
          </p>
          {saved.warnings.map((warning, index) => (
            <Notice key={index}>{warning}</Notice>
          ))}
          {saved.translation.status === 'failed' || saved.translation.status === 'not_requested' ? (
            <div className="translation-retry">
              <Languages size={20} />
              <h3>
                {t('영어 번역은 다시 준비할 수 있어요.', 'English translation can be retried.')}
              </h3>
              <p>
                {t(
                  '공연은 이미 저장됐어요. 다시 등록할 필요가 없습니다.',
                  'The show is already saved. No need to register it again.',
                )}
              </p>
              <button
                type="button"
                className="button secondary"
                disabled={translating}
                onClick={() => void retryTranslation()}
              >
                {translating
                  ? t('번역 준비 중…', 'Preparing translation…')
                  : t('영어 번역 재시도', 'Retry English translation')}
              </button>
              {!!translationError && <ErrorState error={translationError} />}
            </div>
          ) : (
            <p className="translation-success">
              <Languages size={16} />
              {saved.translation.status === 'generated'
                ? t('영어 안내 생성 완료 · AI-translated', 'English ready · AI-translated')
                : t('검수된 영어 안내 준비 완료', 'Reviewed English ready')}
            </p>
          )}
          <div className="success-actions">
            <Link className="button primary" to={`/events/${saved.id}`}>
              {t('등록한 공연 보기', 'View your show')}
              <ArrowRight size={17} />
            </Link>
            <Link className="button secondary" to="/events">
              {t('공연 목록으로', 'Back to listings')}
            </Link>
          </div>
        </section>
      )}
    </div>
  );
}
function ArrowUpRightIcon() {
  return <ArrowRight size={17} aria-hidden="true" />;
}
