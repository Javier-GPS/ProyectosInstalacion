import React, { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react';
import type { GisLanguage } from './types';
import type { TranslationMap } from './types';
import { gisTranslations } from './gis';

export type { GisLanguage };

interface I18nContextValue {
  language: GisLanguage;
  setLanguage: (lang: GisLanguage) => void;
  t: (key: string, params?: Record<string, string | number>) => string;
}

const I18nContext = createContext<I18nContextValue | null>(null);
const LANG_KEY = 'gis-language';

export const GisI18nProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [language, setLanguageState] = useState<GisLanguage>(() => {
    const saved = typeof localStorage !== 'undefined' ? localStorage.getItem(LANG_KEY) : null;
    return (saved as GisLanguage) || 'es';
  });

  const setLanguage = useCallback((lang: GisLanguage) => {
    localStorage.setItem(LANG_KEY, lang);
    setLanguageState(lang);
  }, []);

  const value = useMemo<I18nContextValue>(() => ({
    language,
    setLanguage,
    t: (key, params) => {
      const entry = gisTranslations[language]?.[key] ?? gisTranslations.en[key];
      if (typeof entry === 'function') return entry(params ?? {});
      return entry ?? key;
    },
  }), [language, setLanguage]);

  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
};

export const useI18n = () => {
  const ctx = useContext(I18nContext);
  if (!ctx) throw new Error('useI18n must be used within GisI18nProvider');
  return ctx;
};
