import { createContext, useContext, useEffect, useState, type ReactNode } from 'react';
import type { Locale, Recommendations, SearchFilters } from '../types/api';
import { emptyFilters } from './format';

interface SearchDraft {
  query: string;
  filters: SearchFilters;
  result: Recommendations | null;
  resultLocale: Locale;
}
interface AppState {
  locale: Locale;
  setLocale: (locale: Locale) => void;
  t: (ko: string, en: string) => string;
  search: SearchDraft;
  setSearch: React.Dispatch<React.SetStateAction<SearchDraft>>;
}
const Context = createContext<AppState | null>(null);
export function AppProvider({ children }: { children: ReactNode }) {
  const [locale, setLocale] = useState<Locale>(() => {
    try {
      return localStorage.getItem('amp-locale') === 'en' ? 'en' : 'ko';
    } catch {
      return 'ko';
    }
  });
  const [search, setSearch] = useState<SearchDraft>({
    query: '',
    filters: emptyFilters(),
    result: null,
    resultLocale: locale,
  });
  useEffect(() => {
    document.documentElement.lang = locale;
    try {
      localStorage.setItem('amp-locale', locale);
    } catch {
      /* Storage is optional. */
    }
  }, [locale]);
  return (
    <Context.Provider
      value={{ locale, setLocale, t: (ko, en) => (locale === 'ko' ? ko : en), search, setSearch }}
    >
      {children}
    </Context.Provider>
  );
}
export function useApp() {
  const context = useContext(Context);
  if (!context) throw new Error('AppProvider is required');
  return context;
}
