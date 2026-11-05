import { useEffect, useRef } from 'react';
import { Link, NavLink, Outlet, useLocation } from 'react-router-dom';
import { ArrowUpRight, CalendarDays, Plus, Search } from 'lucide-react';
import { useApp } from '../lib/context';

export default function Layout() {
  const { locale, setLocale, t } = useApp();
  const location = useLocation();
  const main = useRef<HTMLElement>(null);
  useEffect(() => {
    const title =
      location.pathname === '/'
        ? t('AI 추천', 'AI picks')
        : location.pathname === '/events'
          ? t('공연 둘러보기', 'All shows')
          : location.pathname === '/admin/register'
            ? t('공연 등록', 'List a show')
            : t('공연 정보', 'Show details');
    document.title = `${title} · AMP`;
  }, [location.pathname, t]);
  useEffect(() => {
    window.scrollTo(0, 0);
    main.current?.focus({ preventScroll: true });
  }, [location.pathname]);
  const links = [
    { to: '/', label: t('AI 추천', 'AI picks'), icon: Search },
    { to: '/events', label: t('공연 둘러보기', 'All shows'), icon: CalendarDays },
    { to: '/admin/register', label: t('공연 등록', 'List a show'), icon: Plus },
  ];
  return (
    <div className="app-shell">
      <a className="skip-link" href="#main">
        {t('본문으로 바로가기', 'Skip to content')}
      </a>
      <header className="site-header">
        <div className="header-inner">
          <Link to="/" className="wordmark" aria-label="AMP home">
            AMP
            <span className="logo-dot" />
          </Link>
          <nav className="desktop-nav" aria-label={t('주 메뉴', 'Main navigation')}>
            {links.map(({ to, label }) => (
              <NavLink key={to} to={to} end={to === '/'}>
                {label}
              </NavLink>
            ))}
          </nav>
          <div
            className="language-switch"
            role="group"
            aria-label={t('언어 선택', 'Choose language')}
          >
            {(['ko', 'en'] as const).map((lang) => (
              <button
                key={lang}
                type="button"
                aria-pressed={locale === lang}
                onClick={() => setLocale(lang)}
              >
                {lang.toUpperCase()}
              </button>
            ))}
          </div>
        </div>
      </header>
      <main ref={main} tabIndex={-1} id="main" className="main-content">
        <Outlet />
      </main>
      <footer className="site-footer">
        <div>
          <span className="footer-logo">AMP.</span>
          <span>Amplify Local Stages.</span>
        </div>
        <p>
          {t(
            '작은 무대를 발견하고, 나의 취향을 넓히세요.',
            'Small stages. A wider world of music.',
          )}
          <ArrowUpRight size={14} />
        </p>
        <span className="footer-note">SINCHON · HONGDAE / SEOUL</span>
      </footer>
      <nav className="mobile-nav" aria-label={t('하단 메뉴', 'Mobile navigation')}>
        {links.map(({ to, label, icon: Icon }) => (
          <NavLink key={to} to={to} end={to === '/'}>
            <Icon size={20} />
            <span>{label}</span>
          </NavLink>
        ))}
      </nav>
    </div>
  );
}
